"""Experimental code-first feature flags backed by Logfire managed variables.

This API may change while its evaluation context and telemetry contracts are refined.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar, cast, overload

from typing_extensions import TypeForm

from logfire.variables import ensure_variables_dependencies

if TYPE_CHECKING:
    from pydantic import BaseModel

    from logfire import Logfire

    InferableFlagValue = bool | str | int | float | Enum | BaseModel
else:
    InferableFlagValue = Any

__all__ = (
    'FeatureFlag',
    'Flag',
    'FlagErrorCode',
    'FlagEvaluationDetails',
    'FlagEvaluationReason',
    'feature_context',
    'feature_flag',
    'flag',
)


T = TypeVar('T')
InferableFlagT = TypeVar('InferableFlagT', bound=InferableFlagValue)

FlagEvaluationReason = Literal['default', 'static', 'split', 'targeting_match', 'error']
"""Why a feature-flag evaluation returned its value."""

FlagErrorCode = Literal['type_mismatch', 'general']
"""A stable classification for a native Logfire feature-flag evaluation error."""


@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails(Generic[T]):
    """The result of evaluating a Logfire feature flag."""

    flag_key: str
    value: T
    variant: str | None = None
    reason: FlagEvaluationReason = 'default'
    error_code: FlagErrorCode | None = None
    error_message: str | None = None
    flag_metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])


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
    ) -> FlagEvaluationDetails[T]: ...  # pragma: no cover

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
        self: Flag[InferableFlagT],
        name: str,
        *,
        default: InferableFlagT,
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
        """Evaluate the flag and return native Logfire evaluation details."""
        return self._adapter.evaluate_flag(targeting_key, attributes)

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

    def evaluate(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails[bool]:
        """Alias for :meth:`details`, retained for the initial boolean API."""
        return self.details(targeting_key, attributes)


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
    default: InferableFlagT,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> Flag[InferableFlagT]: ...


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
        return cast(
            Flag[T],
            Flag(
                name,
                default=cast(InferableFlagValue, default),
                description=description,
                logfire_instance=logfire_instance,
            ),
        )
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
