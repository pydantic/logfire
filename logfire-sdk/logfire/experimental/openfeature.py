"""Optional OpenFeature adapter for Logfire's experimental feature flags."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar, cast

from typing_extensions import TypeIs

from logfire.experimental.feature_flags import (
    FlagErrorCode,
    FlagEvaluationDetails,
    FlagEvaluationReason,
    _FlagAdapter,  # pyright: ignore[reportPrivateUsage]
)
from logfire.variables import ensure_variables_dependencies

try:
    from openfeature.evaluation_context import EvaluationContext
    from openfeature.exception import ErrorCode
    from openfeature.flag_evaluation import FlagResolutionDetails, FlagValueType, Reason
    from openfeature.provider import AbstractProvider, Metadata
except ModuleNotFoundError as e:  # pragma: no cover
    if e.name is None or (e.name != 'openfeature' and not e.name.startswith('openfeature.')):
        raise
    raise ImportError(
        'Using the OpenFeature adapter requires the `openfeature-sdk`, `pydantic_handlebars`, and `pydantic` packages.\n'
        'You can install these with:\n'
        "    pip install 'logfire[openfeature]'"
    ) from e

if TYPE_CHECKING:
    from logfire import Logfire

__all__ = ('LogfireProvider',)

T = TypeVar('T')

_REASONS: dict[FlagEvaluationReason, Reason] = {
    'cached': Reason.CACHED,
    'default': Reason.DEFAULT,
    'disabled': Reason.DISABLED,
    'error': Reason.ERROR,
    'stale': Reason.STALE,
    'static': Reason.STATIC,
    'split': Reason.SPLIT,
    'targeting_match': Reason.TARGETING_MATCH,
    'unknown': Reason.UNKNOWN,
}
_ERROR_CODES: dict[FlagErrorCode, ErrorCode] = {
    'flag_not_found': ErrorCode.FLAG_NOT_FOUND,
    'general': ErrorCode.GENERAL,
    'invalid_context': ErrorCode.INVALID_CONTEXT,
    'parse_error': ErrorCode.PARSE_ERROR,
    'provider_fatal': ErrorCode.PROVIDER_FATAL,
    'provider_not_ready': ErrorCode.PROVIDER_NOT_READY,
    'targeting_key_missing': ErrorCode.TARGETING_KEY_MISSING,
    'type_mismatch': ErrorCode.TYPE_MISMATCH,
}


class LogfireProvider(AbstractProvider):
    """OpenFeature provider backed by flags declared through Logfire.

    Register this provider explicitly with OpenFeature. Constructing a Logfire flag never changes
    OpenFeature's process-global provider registry.
    """

    def __init__(self, logfire_instance: Logfire | None = None):
        ensure_variables_dependencies()
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        self._logfire = logfire_instance

    def get_metadata(self) -> Metadata:
        """Return the provider metadata exposed through OpenFeature."""
        return Metadata(name='Logfire')

    def resolve_boolean_details(
        self, flag_key: str, default_value: bool, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag."""
        return self._resolve(flag_key, default_value, bool, evaluation_context)

    def resolve_string_details(
        self, flag_key: str, default_value: str, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[str]:
        """Resolve a string flag."""
        return self._resolve(flag_key, default_value, str, evaluation_context)

    def resolve_integer_details(
        self, flag_key: str, default_value: int, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[int]:
        """Resolve an integer flag."""
        return self._resolve(flag_key, default_value, int, evaluation_context)

    def resolve_float_details(
        self, flag_key: str, default_value: float, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[float]:
        """Resolve a floating-point flag."""
        return self._resolve(flag_key, default_value, float, evaluation_context)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType],
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[Sequence[FlagValueType] | Mapping[str, FlagValueType]]:
        """Resolve an object flag as JSON-compatible data."""
        adapter = self._get_adapter(flag_key)
        if adapter is None:
            return _flag_not_found(flag_key, default_value)
        if _is_exclusively_openfeature_scalar_schema(adapter.type_adapter.core_schema):
            return _type_mismatch(default_value, 'The registered flag does not resolve to an object value.')
        resolution = self._resolve_native(adapter, default_value, evaluation_context)
        if resolution.error_code is not None:
            return resolution
        try:
            value = cast(FlagValueType, adapter.type_adapter.dump_python(resolution.value, mode='json'))
        except Exception:  # OpenFeature providers return errors rather than raising.
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message='Feature flag result serialization failed.',
            )
        if not isinstance(value, (Mapping, Sequence)) or isinstance(value, (str, bytes, bytearray)):
            return _type_mismatch(default_value, 'The registered flag does not resolve to an object value.')
        return FlagResolutionDetails(
            value=cast(Sequence[FlagValueType] | Mapping[str, FlagValueType], value),
            variant=resolution.variant,
            reason=resolution.reason,
            flag_metadata=resolution.flag_metadata,
        )

    def _get_adapter(self, flag_key: str) -> _FlagAdapter[Any] | None:
        candidate = self._logfire._variables.get(flag_key)  # pyright: ignore[reportPrivateUsage]
        if getattr(candidate, 'kind', None) != 'feature_flag':
            return None
        return cast(_FlagAdapter[Any], candidate)

    def _resolve(
        self,
        flag_key: str,
        default_value: T,
        expected_type: type[Any],
        evaluation_context: EvaluationContext | None,
    ) -> FlagResolutionDetails[T]:
        adapter = self._get_adapter(flag_key)
        if adapter is None:
            return _flag_not_found(flag_key, default_value)
        if not _matches_openfeature_scalar_type(adapter, expected_type):
            return _type_mismatch(default_value, f"Flag '{flag_key}' is not registered as {expected_type.__name__}.")

        resolution = self._resolve_native(adapter, default_value, evaluation_context)
        if resolution.error_code is not None:
            return resolution
        try:
            value = adapter.type_adapter.dump_python(resolution.value, mode='json')
        except Exception:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message='Feature flag result serialization failed.',
            )
        if type(value) is not expected_type:
            return _type_mismatch(default_value, 'The registered flag did not resolve to the expected scalar type.')
        return FlagResolutionDetails(
            value=cast(T, value),
            variant=resolution.variant,
            reason=resolution.reason,
            flag_metadata=resolution.flag_metadata,
        )

    @staticmethod
    def _resolve_native(
        adapter: _FlagAdapter[Any],
        default_value: T,
        evaluation_context: EvaluationContext | None,
    ) -> FlagResolutionDetails[T]:
        context = evaluation_context or EvaluationContext()
        try:
            details = adapter.evaluate_flag(targeting_key=context.targeting_key, attributes=context.attributes)
        except Exception:
            return FlagResolutionDetails(
                value=default_value,
                reason=Reason.ERROR,
                error_code=ErrorCode.GENERAL,
                error_message='Feature flag evaluation failed.',
            )
        return _to_openfeature_details(details, default_value)


def _to_openfeature_details(details: FlagEvaluationDetails[Any], default_value: T) -> FlagResolutionDetails[T]:
    error_code = _ERROR_CODES.get(details.error_code) if details.error_code is not None else None
    return FlagResolutionDetails(
        value=default_value if error_code is not None else cast(T, details.value),
        variant=details.variant,
        reason=_REASONS[details.reason],
        error_code=error_code,
        error_message=details.error_message,
        flag_metadata=dict(details.flag_metadata or {}),
    )


def _type_mismatch(default_value: T, message: str) -> FlagResolutionDetails[T]:
    return FlagResolutionDetails(
        value=default_value,
        reason=Reason.ERROR,
        error_code=ErrorCode.TYPE_MISMATCH,
        error_message=message,
    )


def _flag_not_found(flag_key: str, default_value: T) -> FlagResolutionDetails[T]:
    return FlagResolutionDetails(
        value=default_value,
        reason=Reason.ERROR,
        error_code=ErrorCode.FLAG_NOT_FOUND,
        error_message=f"Flag '{flag_key}' has not been declared with logfire.experimental.feature_flags.flag().",
    )


def _matches_openfeature_scalar_type(adapter: _FlagAdapter[Any], expected_type: type[Any]) -> bool:
    """Match Pydantic constrained scalar types to their OpenFeature primitive type."""
    expected_schema_type = {bool: 'bool', str: 'str', int: 'int', float: 'float'}[expected_type]
    return _matches_openfeature_scalar_schema(adapter.type_adapter.core_schema, expected_type, expected_schema_type)


def _matches_openfeature_scalar_schema(
    schema: Mapping[Any, Any],
    expected_type: type[Any],
    expected_schema_type: str,
    definitions: Mapping[str, Mapping[Any, Any]] | None = None,
    visited_refs: frozenset[str] = frozenset(),
) -> bool:
    schema, definitions, visited_refs = _unwrap_schema_context(schema, definitions, visited_refs)
    schema_type = schema.get('type')
    if schema_type == 'nullable':
        inner_schema = schema.get('schema')
        return _is_schema_mapping(inner_schema) and _matches_openfeature_scalar_schema(
            inner_schema, expected_type, expected_schema_type, definitions, visited_refs
        )
    if schema_type == 'union':
        choices = schema.get('choices')
        return (
            _is_schema_list(choices)
            and bool(choices)
            and all(
                _is_schema_mapping(choice)
                and _matches_openfeature_scalar_schema(
                    choice, expected_type, expected_schema_type, definitions, visited_refs
                )
                for choice in choices
            )
        )
    if schema_type == expected_schema_type:
        return True
    if schema_type == 'literal':
        expected = schema.get('expected')
        return _is_schema_list(expected) and bool(expected) and all(type(value) is expected_type for value in expected)
    if schema_type == 'enum':
        members = schema.get('members')
        if not _is_schema_list(members) or not members:
            return False
        values = tuple(member.value for member in members)
    elif schema_type == 'lax-or-strict':
        try:
            enum_type = schema['strict_schema']['python_schema']['cls']
        except (KeyError, TypeError):
            return False
        if not isinstance(enum_type, type) or not issubclass(enum_type, Enum):
            return False
        values = tuple(member.value for member in enum_type)
    else:
        return False
    return bool(values) and all(type(value) is expected_type for value in values)


def _is_exclusively_openfeature_scalar_schema(schema: Mapping[Any, Any]) -> bool:
    """Return whether every value admitted by a Pydantic schema is an OpenFeature scalar."""
    return _schema_is_exclusively_openfeature_scalar(schema, None, frozenset())


def _schema_is_exclusively_openfeature_scalar(
    schema: Mapping[Any, Any],
    definitions: Mapping[str, Mapping[Any, Any]] | None,
    visited_refs: frozenset[str],
) -> bool:
    schema, definitions, visited_refs = _unwrap_schema_context(schema, definitions, visited_refs)
    schema_type = schema.get('type')
    if schema_type in {'bool', 'str', 'int', 'float', 'literal'}:
        return True
    if schema_type == 'enum':
        members = schema.get('members')
        if not _is_schema_list(members) or not members:
            return False
        return all(type(member.value) in (bool, str, int, float) for member in members)
    if schema_type == 'lax-or-strict':
        try:
            enum_type = schema['strict_schema']['python_schema']['cls']
        except (KeyError, TypeError):
            return False
        return (
            isinstance(enum_type, type)
            and issubclass(enum_type, Enum)
            and all(type(member.value) in (bool, str, int, float) for member in enum_type)
        )
    if schema_type == 'nullable':
        inner_schema = schema.get('schema')
        return _is_schema_mapping(inner_schema) and _schema_is_exclusively_openfeature_scalar(
            inner_schema, definitions, visited_refs
        )
    if schema_type == 'union':
        choices = schema.get('choices')
        if not _is_schema_list(choices):
            return False
        return bool(choices) and all(
            _is_schema_mapping(choice) and _schema_is_exclusively_openfeature_scalar(choice, definitions, visited_refs)
            for choice in choices
        )
    return False


def _unwrap_transparent_schema(  # pyright: ignore[reportUnusedFunction]
    schema: Mapping[Any, Any],
) -> Mapping[Any, Any]:
    """Unwrap Pydantic schemas that retain the declared value's underlying shape."""
    return _unwrap_schema_context(schema, None, frozenset())[0]


def _unwrap_schema_context(
    schema: Mapping[Any, Any],
    definitions: Mapping[str, Mapping[Any, Any]] | None,
    visited_refs: frozenset[str],
) -> tuple[Mapping[Any, Any], Mapping[str, Mapping[Any, Any]], frozenset[str]]:
    """Unwrap a schema while retaining definitions needed by nested unions and nullable schemas."""
    definitions = dict(definitions or {})
    while True:
        schema_type = schema.get('type')
        if schema_type == 'definitions':
            raw_definitions = schema.get('definitions')
            if _is_schema_list(raw_definitions):
                definitions.update(
                    (ref, definition)
                    for definition in raw_definitions
                    if _is_schema_mapping(definition) and isinstance((ref := definition.get('ref')), str)
                )
        elif schema_type == 'definition-ref':
            schema_ref = schema.get('schema_ref')
            if not isinstance(schema_ref, str) or schema_ref in visited_refs:
                break
            referenced_schema = definitions.get(schema_ref)
            if referenced_schema is None:
                break
            visited_refs |= {schema_ref}
            schema = referenced_schema
            continue
        elif schema_type not in {'function-after', 'function-before', 'function-wrap', 'default'}:
            break
        inner_schema = schema.get('schema')
        if not _is_schema_mapping(inner_schema):
            break
        schema = inner_schema
    return schema, definitions, visited_refs


def _is_schema_mapping(value: object) -> TypeIs[Mapping[Any, Any]]:
    return isinstance(value, Mapping)


def _is_schema_list(value: object) -> TypeIs[list[Any]]:
    return isinstance(value, list)
