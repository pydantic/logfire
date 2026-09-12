"""Experimental code-first feature flags backed by Logfire managed variables.

This API may change while its evaluation context and telemetry contracts are refined.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, cast, overload

from typing_extensions import TypeForm

from logfire.variables import ensure_variables_dependencies

try:
    from openfeature.evaluation_context import EvaluationContext
    from openfeature.exception import ErrorCode
    from openfeature.flag_evaluation import FlagEvaluationDetails, FlagResolutionDetails, FlagValueType, Reason
    from openfeature.provider import AbstractProvider, Metadata
except ModuleNotFoundError as e:  # pragma: no cover
    if e.name is None or (e.name != 'openfeature' and not e.name.startswith('openfeature.')):
        raise
    raise ImportError(
        'Using feature flags requires the `openfeature-sdk`, `pydantic_handlebars`, and `pydantic` packages.\n'
        'You can install these with:\n'
        "    pip install 'logfire[feature-flags]'"
    ) from e

if TYPE_CHECKING:
    from logfire import Logfire

__all__ = (
    'ErrorCode',
    'FeatureFlag',
    'Flag',
    'FlagEvaluationDetails',
    'LogfireProvider',
    'Reason',
    'feature_context',
    'feature_flag',
    'flag',
)


T = TypeVar('T')


class _FlagAdapter(Protocol[T]):
    """Private compatibility boundary implemented by the current variables engine."""

    name: str
    value_type: Any
    description: str | None
    type_adapter: Any

    def evaluate_flag(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagResolutionDetails[T]: ...  # pragma: no cover

    def override_for_testing(self, value: T) -> AbstractContextManager[None]: ...  # pragma: no cover


class Flag(Generic[T]):
    """A typed feature flag with a safe code default.

    Values are validated with Pydantic before they are returned. Parameterized containers and
    nullable types need an explicit ``type=`` because Python cannot recover their element type from
    a runtime default such as ``[]`` or ``None``.
    """

    __slots__ = ('_adapter',)

    @overload
    def __init__(
        self,
        name: str,
        *,
        default: T,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        name: str,
        *,
        type: TypeForm[T],
        default: T,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ) -> None: ...

    def __init__(
        self,
        name: str,
        *,
        default: T,
        type: Any | None = None,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ):
        """Define a typed feature flag backed by the configured Logfire provider."""
        ensure_variables_dependencies()
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        # Registration errors should be stable even when type inference would also fail.
        logfire_instance._validate_variable_registration(name)  # pyright: ignore[reportPrivateUsage]
        if type is None:
            type = _infer_flag_type(default)
        self._adapter: _FlagAdapter[T] = logfire_instance._flag(  # pyright: ignore[reportPrivateUsage]
            name, type=type, default=default, description=description
        )

    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
        return self._adapter.name

    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
        return self._adapter.description

    def value(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> T:
        """Return the flag value for the evaluation context."""
        return self.details(targeting_key, attributes).value

    def details(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails[T]:
        """Evaluate the flag and return standard OpenFeature evaluation details."""
        resolution = self._adapter.evaluate_flag(targeting_key, attributes)
        return FlagEvaluationDetails(
            flag_key=self.name,
            value=resolution.value,
            variant=resolution.variant,
            reason=resolution.reason,
            error_code=resolution.error_code,
            error_message=resolution.error_message,
            flag_metadata=resolution.flag_metadata,
        )

    def evaluate(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails[T]:
        """Alias for :meth:`details`, retained for the initial boolean API."""
        return self.details(targeting_key, attributes)

    def override_for_testing(self, value: T) -> AbstractContextManager[None]:
        """Temporarily replace the flag value in the current context."""
        validated_value: T = self._adapter.type_adapter.validate_python(value)
        return self._adapter.override_for_testing(validated_value)


class FeatureFlag(Flag[bool]):
    """A boolean feature flag with a safe code default."""

    def __init__(
        self,
        name: str,
        *,
        default: bool,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ):
        """Define a boolean feature flag backed by the configured Logfire provider."""
        ensure_variables_dependencies()
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        logfire_instance._validate_variable_registration(name)  # pyright: ignore[reportPrivateUsage]
        if not isinstance(cast(Any, default), bool):
            raise TypeError('Feature flag defaults must be boolean.')
        super().__init__(name, default=default, description=description, logfire_instance=logfire_instance)

    def is_enabled(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the feature is enabled for the evaluation context."""
        return self.value(targeting_key, attributes)


class LogfireProvider(AbstractProvider):
    """OpenFeature provider backed by flags declared through Logfire.

    Register this provider explicitly with OpenFeature. Constructing a :class:`Flag` never changes
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
        resolution = self._resolve(flag_key, default_value, None, evaluation_context)
        adapter = self._get_adapter(flag_key)
        if adapter is None:
            return resolution
        try:
            value = cast(FlagValueType, adapter.type_adapter.dump_python(resolution.value, mode='json'))
        except Exception as e:  # OpenFeature providers return errors rather than raising.
            return FlagResolutionDetails(
                value=default_value,
                reason='ERROR',
                error_code=ErrorCode.GENERAL,
                error_message=str(e),
            )
        if not isinstance(value, (Mapping, Sequence)) or isinstance(value, (str, bytes, bytearray)):
            return _type_mismatch(default_value, 'The registered flag does not resolve to an object value.')
        return FlagResolutionDetails(
            value=cast(Sequence[FlagValueType] | Mapping[str, FlagValueType], value),
            variant=resolution.variant,
            reason=resolution.reason,
            error_code=resolution.error_code,
            error_message=resolution.error_message,
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
        expected_type: type[Any] | None,
        evaluation_context: EvaluationContext | None,
    ) -> FlagResolutionDetails[T]:
        adapter = self._get_adapter(flag_key)
        if adapter is None:
            return FlagResolutionDetails(
                value=default_value,
                reason='ERROR',
                error_code=ErrorCode.FLAG_NOT_FOUND,
                error_message=f"Flag '{flag_key}' has not been declared with logfire.experimental.feature_flags.flag().",
            )
        if expected_type is not None and not _matches_openfeature_scalar_type(adapter, expected_type):
            return _type_mismatch(default_value, f"Flag '{flag_key}' is not registered as {expected_type.__name__}.")

        context = evaluation_context or EvaluationContext()
        return cast(
            FlagResolutionDetails[T],
            adapter.evaluate_flag(targeting_key=context.targeting_key, attributes=context.attributes),
        )


def _type_mismatch(default_value: T, message: str) -> FlagResolutionDetails[T]:
    return FlagResolutionDetails(
        value=default_value,
        reason='ERROR',
        error_code=ErrorCode.TYPE_MISMATCH,
        error_message=message,
    )


def _matches_openfeature_scalar_type(adapter: _FlagAdapter[Any], expected_type: type[Any]) -> bool:
    """Match Pydantic constrained scalar types to their OpenFeature primitive type."""
    expected_schema_type = {bool: 'bool', str: 'str', int: 'int', float: 'float'}[expected_type]
    return adapter.type_adapter.core_schema.get('type') == expected_schema_type


def _infer_flag_type(default: Any) -> type[Any]:
    if default is None or isinstance(default, (list, dict, set, tuple)):
        raise TypeError(
            'Pass type=... for nullable or parameterized feature flags; their type cannot be inferred safely.'
        )
    return cast(type[Any], type(default))


@overload
def flag(
    name: str,
    *,
    default: T,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[T]: ...


@overload
def flag(
    name: str,
    *,
    type: TypeForm[T],
    default: T,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[T]: ...


def flag(
    name: str,
    *,
    default: T,
    type: Any | None = None,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[T]:
    """Define a Pydantic-validated feature flag with a safe code default."""
    if type is None:
        return Flag(name, default=default, description=description, logfire_instance=logfire_instance)
    return Flag(name, type=type, default=default, description=description, logfire_instance=logfire_instance)


def feature_flag(
    name: str,
    *,
    default: bool,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> FeatureFlag:
    """Define a boolean feature flag with a safe code default."""
    return FeatureFlag(name, default=default, description=description, logfire_instance=logfire_instance)


def feature_context(
    targeting_key: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for feature-flag evaluations."""
    ensure_variables_dependencies()
    from logfire.variables.variable import feature_context as _feature_context

    return _feature_context(targeting_key, attributes=attributes)
