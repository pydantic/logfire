from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from enum import Enum
from logfire import Logfire
from pydantic import BaseModel
from typing import Literal, Any, Generic, Protocol, TypeVar, overload
from typing_extensions import TypeForm

__all__ = ['FeatureFlag', 'Flag', 'FlagErrorCode', 'FlagEvaluationDetails', 'FlagEvaluationReason', 'feature_context', 'feature_flag', 'flag']

InferableFlagValue = bool | str | int | float | Enum | BaseModel
T = TypeVar('T')
InferableFlagT = TypeVar('InferableFlagT', bound=InferableFlagValue)
FlagEvaluationReason = Literal['default', 'static', 'split', 'targeting_match', 'error']
FlagErrorCode = Literal['type_mismatch', 'general']

@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails(Generic[T]):
    """The result of evaluating a Logfire feature flag."""
    flag_key: str
    value: T
    variant: str | None = ...
    reason: FlagEvaluationReason = ...
    error_code: FlagErrorCode | None = ...
    error_message: str | None = ...
    flag_metadata: Mapping[str, Any] = field(default_factory=dict[str, Any])

class _FlagAdapter(Protocol[T]):
    """Private compatibility boundary implemented by the current variables engine."""
    name: str
    value_type: Any
    description: str | None
    type_adapter: Any
    def evaluate_flag(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails[T]: ...
    def override_for_testing(self, value: T) -> AbstractContextManager[None]: ...

class Flag(Generic[T]):
    """A typed feature flag with a safe code default.

    Values are validated with Pydantic before they are returned. Parameterized containers and
    nullable types need an explicit ``type=`` because Python cannot recover their element type from
    a runtime default such as ``[]`` or ``None``.
    """
    @overload
    def __init__(self: Flag[InferableFlagT], name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> None: ...
    @overload
    def __init__(self, name: str, *, type: TypeForm[T], default: T, description: str | None = None, logfire_instance: Logfire | None = None) -> None: ...
    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
    def value(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> T:
        """Return the flag value for the evaluation context."""
    def details(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails[T]:
        """Evaluate the flag and return native Logfire evaluation details."""
    def override_for_testing(self, value: T) -> AbstractContextManager[None]:
        """Temporarily replace the flag value in the current context."""

class FeatureFlag(Flag[bool]):
    """A boolean feature flag with a safe code default."""
    def __init__(self, name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> None:
        """Define a boolean feature flag backed by the configured Logfire provider."""
    def is_enabled(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> bool:
        """Return whether the feature is enabled for the evaluation context."""
    def evaluate(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails[bool]:
        """Alias for :meth:`details`, retained for the initial boolean API."""

@overload
def flag(name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[InferableFlagT]: ...
@overload
def flag(name: str, *, type: TypeForm[T], default: T, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[T]: ...
def feature_flag(name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> FeatureFlag:
    """Define a boolean feature flag with a safe code default."""
def feature_context(targeting_key: str, *, attributes: Mapping[str, Any] | None = None) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for feature-flag evaluations."""
