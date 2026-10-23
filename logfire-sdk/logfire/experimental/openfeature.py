"""Optional OpenFeature adapter for Logfire's experimental feature flags."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import replace
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar, cast

from typing_extensions import TypeIs

from logfire.experimental.feature_flags import (
    FlagErrorCode,
    FlagEvaluationDetails,
    FlagEvaluationReason,
)
from logfire.variables import ensure_variables_dependencies

try:
    from openfeature.evaluation_context import EvaluationContext
    from openfeature.event import ProviderEventDetails
    from openfeature.exception import ErrorCode, GeneralError, ProviderFatalError, ProviderNotReadyError
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
    from logfire.variables.abstract import VariableProvider, VariableProviderEvaluationState
    from logfire.variables.variable import _ManagedVariableFlagAdapter  # pyright: ignore[reportPrivateUsage]

__all__ = ('LogfireProvider',)

T = TypeVar('T')

# OpenFeature allows provider-specific reasons. `CONTEXT_OVERRIDE` reports `Flag.override()` values.
_REASONS: dict[FlagEvaluationReason, Reason | str] = {
    'cached': Reason.CACHED,
    'context_override': 'CONTEXT_OVERRIDE',
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
    """OpenFeature provider backed by Logfire's shared flag configuration.

    Register this provider explicitly with OpenFeature. Constructing a Logfire flag never changes
    OpenFeature's process-global provider registry.
    """

    def __init__(self, logfire_instance: Logfire | None = None):
        ensure_variables_dependencies('openfeature')
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        self._logfire = logfire_instance
        self._state_lock = threading.RLock()
        self._pid = os.getpid()
        self._unsubscribe: Callable[[], None] | None = None
        self._provider: VariableProvider | None = None
        self._last_state: VariableProviderEvaluationState | None = None
        self._last_configuration: object | None = None

    def initialize(self, evaluation_context: EvaluationContext) -> None:
        """Load initial configuration and observe the shared provider without owning it."""
        self.shutdown()
        provider = self._logfire.config.get_variable_provider()
        self._provider = provider
        self._unsubscribe = provider._subscribe_evaluation_state(self._state_changed)  # pyright: ignore[reportPrivateUsage]
        self._last_state = provider.get_evaluation_state()
        self._last_configuration = provider.get_all_variables_config()
        if self._last_state != 'ready':
            provider.refresh(force=True)
        state = provider.get_evaluation_state()
        if state == 'not_ready':
            raise ProviderNotReadyError('Logfire has not loaded feature flag configuration.')
        if state in ('error', 'stale'):
            raise GeneralError('Logfire could not load fresh feature flag configuration.')
        if state == 'fatal':
            raise ProviderFatalError('The Logfire feature flag provider is unavailable.')

    def shutdown(self) -> None:
        """Unsubscribe without stopping resources also used by native Logfire flags."""
        # OpenFeature may replace or re-register this adapter. Only Logfire owns the underlying
        # provider, its polling thread, and its streaming connection.
        self._reset_state_lock_after_fork()
        with self._state_lock:
            unsubscribe, self._unsubscribe = self._unsubscribe, None
            self._provider = None
            self._last_state = None
            self._last_configuration = None
        if unsubscribe is not None:
            unsubscribe()

    def _reset_state_lock_after_fork(self) -> None:
        pid = os.getpid()
        if self._pid != pid:
            self._state_lock = threading.RLock()
            self._pid = pid

    def _state_changed(self, state: VariableProviderEvaluationState) -> None:
        self._reset_state_lock_after_fork()
        with self._state_lock:
            if self._provider is None:
                return
            # Notifications can race or be re-entrant. Read current health rather than publishing
            # an older notification over a newer refresh or shutdown result.
            state = self._provider.get_evaluation_state()
            configuration = self._provider.get_all_variables_config()
            if state == self._last_state:
                if state == 'ready' and configuration is not self._last_configuration:
                    self._last_configuration = configuration
                    self.emit_provider_configuration_changed(ProviderEventDetails())
                return
            self._last_state = state
            self._last_configuration = configuration
            if state == 'ready':
                self.emit_provider_ready(ProviderEventDetails())
            elif state == 'stale':
                self.emit_provider_stale(ProviderEventDetails())
            else:
                error = {'not_ready': ErrorCode.PROVIDER_NOT_READY, 'fatal': ErrorCode.PROVIDER_FATAL}.get(
                    state, ErrorCode.GENERAL
                )
                self.emit_provider_error(
                    ProviderEventDetails(error_code=error, message='Logfire configuration is unavailable.')
                )

    def get_metadata(self) -> Metadata:
        """Return the provider metadata exposed through OpenFeature."""
        return Metadata(name='Logfire')

    def resolve_boolean_details(
        self, flag_key: str, default_value: bool, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag."""
        return self._evaluate(flag_key, default_value, bool, evaluation_context)

    def resolve_string_details(
        self, flag_key: str, default_value: str, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[str]:
        """Resolve a string flag."""
        return self._evaluate(flag_key, default_value, str, evaluation_context)

    def resolve_integer_details(
        self, flag_key: str, default_value: int, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[int]:
        """Resolve an integer flag."""
        return self._evaluate(flag_key, default_value, int, evaluation_context)

    def resolve_float_details(
        self, flag_key: str, default_value: float, evaluation_context: EvaluationContext | None = None
    ) -> FlagResolutionDetails[float]:
        """Resolve a floating-point flag."""
        return self._evaluate(flag_key, default_value, float, evaluation_context)

    def resolve_object_details(
        self,
        flag_key: str,
        default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType],
        evaluation_context: EvaluationContext | None = None,
    ) -> FlagResolutionDetails[Sequence[FlagValueType] | Mapping[str, FlagValueType]]:
        """Resolve an object flag as JSON-compatible data."""
        return self._evaluate(flag_key, default_value, None, evaluation_context)

    def _evaluate(
        self, flag_key: str, default_value: T, expected_type: type[Any] | None, context: EvaluationContext | None
    ) -> FlagResolutionDetails[T]:
        # The bridge owns this span: native resolution happens before OpenFeature applies its
        # caller default and serializes the result. Recording there would report the wrong value.
        from logfire.variables.variable import (
            _SUPPRESS_FEATURE_FLAG_TELEMETRY,  # pyright: ignore[reportPrivateUsage]
            _get_variables_instrument,  # pyright: ignore[reportPrivateUsage]
            _include_targeting_key_in_telemetry,  # pyright: ignore[reportPrivateUsage]
            _scrub_feature_flag_result,  # pyright: ignore[reportPrivateUsage]
        )

        with ExitStack() as stack:
            span = None
            adapter = self._get_adapter(flag_key)
            if _get_variables_instrument(self._logfire.config.variables):
                span = stack.enter_context(self._logfire.span('feature_flag.evaluation', name=flag_key))
                if adapter is not None:
                    adapter._emit_declaration_once(span)  # pyright: ignore[reportPrivateUsage]
            token = _SUPPRESS_FEATURE_FLAG_TELEMETRY.set(_SUPPRESS_FEATURE_FLAG_TELEMETRY.get() | {adapter})
            used_caller_default = False
            try:
                if adapter is None:
                    result, used_caller_default = self._resolve_remote(flag_key, default_value, expected_type, context)
                elif expected_type is None:
                    result = cast(FlagResolutionDetails[T], self._resolve_object(adapter, default_value, context))
                else:
                    result = self._resolve(adapter, default_value, expected_type, context)
            except Exception:
                result = FlagResolutionDetails(
                    value=default_value,
                    reason=Reason.ERROR,
                    error_code=ErrorCode.GENERAL,
                    error_message='Feature flag evaluation failed.',
                )
            finally:
                _SUPPRESS_FEATURE_FLAG_TELEMETRY.reset(token)
            if span is not None:
                telemetry = _evaluation_telemetry(flag_key, result, record_value=not used_caller_default)
                if 'feature_flag.result.value' in telemetry:
                    telemetry = _scrub_feature_flag_result(telemetry, flag_key, result.value, self._logfire)
                targeting_key = context.targeting_key if context is not None else None
                if targeting_key and _include_targeting_key_in_telemetry(self._logfire.config.variables):
                    telemetry['feature_flag.context.id'] = targeting_key
                span.set_attributes(telemetry)
            return result

    def _resolve_object(
        self,
        adapter: _ManagedVariableFlagAdapter[Any],
        default_value: Any,
        evaluation_context: EvaluationContext | None,
    ) -> FlagResolutionDetails[Any]:
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

    def _get_adapter(self, flag_key: str) -> _ManagedVariableFlagAdapter[Any] | None:
        from logfire.variables.variable import _ManagedVariableFlagAdapter  # pyright: ignore[reportPrivateUsage]

        candidate = self._logfire._variables.get(flag_key)  # pyright: ignore[reportPrivateUsage]
        return candidate if isinstance(candidate, _ManagedVariableFlagAdapter) else None

    def _resolve(
        self,
        adapter: _ManagedVariableFlagAdapter[Any],
        default_value: T,
        expected_type: type[Any],
        evaluation_context: EvaluationContext | None,
    ) -> FlagResolutionDetails[T]:
        if not _matches_openfeature_scalar_type(adapter, expected_type):
            return _type_mismatch(
                default_value, f"Flag '{adapter.name}' is not registered as {expected_type.__name__}."
            )

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

    def _resolve_remote(
        self,
        flag_key: str,
        default_value: T,
        expected_type: type[Any] | None,
        evaluation_context: EvaluationContext | None,
    ) -> tuple[FlagResolutionDetails[T], bool]:
        from logfire.variables.variable import (
            _SUPPRESS_FEATURE_FLAG_TELEMETRY,  # pyright: ignore[reportPrivateUsage]
            _feature_flag_evaluation_details,  # pyright: ignore[reportPrivateUsage]
            _ManagedVariableFlagAdapter,  # pyright: ignore[reportPrivateUsage]
            _ResolvedFeatureFlag,  # pyright: ignore[reportPrivateUsage]
        )

        # Reuse composition, targeting and health handling without registering a declaration.
        # The placeholder default never leaves this method; the caller's fallback is untouched.
        adapter = _ManagedVariableFlagAdapter(
            flag_key,
            type=expected_type or object,
            default=expected_type() if expected_type is not None else None,
            logfire_instance=self._logfire,
        )
        context = evaluation_context or EvaluationContext()
        token = _SUPPRESS_FEATURE_FLAG_TELEMETRY.set(_SUPPRESS_FEATURE_FLAG_TELEMETRY.get() | {adapter})
        try:
            # The adapter finalizes both its return value and telemetry into this result type.
            resolved = adapter.get(targeting_key=context.targeting_key, attributes=context.attributes)
            # A type-only assertion; changing cast's type argument cannot affect behavior.
            result = cast(_ResolvedFeatureFlag[object], resolved)  # pragma: no mutate
        finally:
            _SUPPRESS_FEATURE_FLAG_TELEMETRY.reset(token)
        used_caller_default = result.reason == 'code_default'
        resolution = _to_openfeature_details(
            _feature_flag_evaluation_details(result, result.provider_state), default_value
        )
        if resolution.error_code is not None:
            return resolution, used_caller_default
        if used_caller_default:
            return replace(resolution, value=default_value), used_caller_default
        value = resolution.value
        if expected_type is None:
            if not isinstance(value, (Mapping, Sequence)) or isinstance(value, (str, bytes, bytearray)):
                return (
                    _type_mismatch(default_value, 'The configured flag does not resolve to an object value.'),
                    used_caller_default,
                )
        return resolution, used_caller_default

    @staticmethod
    def _resolve_native(
        adapter: _ManagedVariableFlagAdapter[Any],
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


def _evaluation_telemetry(
    flag_key: str,
    result: FlagResolutionDetails[Any],
    *,
    record_value: bool = True,
) -> dict[str, Any]:
    """Describe the final, JSON-compatible outcome seen by an OpenFeature caller."""
    telemetry: dict[str, Any] = {
        'feature_flag.key': flag_key,
        'feature_flag.provider.name': 'logfire',
        'feature_flag.result.reason': (result.reason or Reason.UNKNOWN).lower(),
    }
    if result.error_code is not None:
        # Caller defaults may not match the registered type or pass through its serializers.
        # Return them unchanged to OpenFeature, but never export them as flag values.
        telemetry['error.type'] = result.error_code.value.lower()
        telemetry['feature_flag.error.message'] = result.error_message
        telemetry['logfire.feature_flag.result.value_status'] = 'error_fallback'
        return telemetry
    if not record_value:
        telemetry['logfire.feature_flag.result.value_status'] = 'caller_default'
        return telemetry
    try:
        value = result.value
        telemetry['feature_flag.result.value'] = (
            value if isinstance(value, (bool, str, int, float)) else json.dumps(value, separators=(',', ':'))
        )
    except (ValueError, TypeError, RuntimeError):
        telemetry['logfire.feature_flag.result.value_status'] = 'serialization_error'
    if result.variant is not None:
        telemetry['feature_flag.result.variant'] = result.variant
    if result.flag_metadata and (version := result.flag_metadata.get('logfire.value_version')) is not None:
        telemetry['logfire.feature_flag.value_version'] = version
    return telemetry


def _to_openfeature_details(details: FlagEvaluationDetails[Any], default_value: T) -> FlagResolutionDetails[T]:
    error_code = _ERROR_CODES.get(details.error_code, ErrorCode.GENERAL) if details.error_code is not None else None
    return FlagResolutionDetails(
        value=default_value if error_code is not None else details.value,
        variant=details.variant,
        reason=_REASONS.get(details.reason, Reason.UNKNOWN),
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


def _matches_openfeature_scalar_type(adapter: _ManagedVariableFlagAdapter[Any], expected_type: type[Any]) -> bool:
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
        elif schema_type == 'model' and schema.get('root_model') is True:
            pass
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
