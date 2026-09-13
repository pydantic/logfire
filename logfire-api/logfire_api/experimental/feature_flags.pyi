from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from enum import Enum
from logfire import Logfire
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode as ErrorCode
from openfeature.flag_evaluation import FlagEvaluationDetails as FlagEvaluationDetails, FlagResolutionDetails, FlagValueType, Reason as Reason
from openfeature.provider import AbstractProvider, Metadata
from pydantic import BaseModel
from typing import Any, Generic, Protocol, TypeVar, overload
from typing_extensions import TypeForm

T = TypeVar('T')
InferableFlagValue = bool | str | int | float | Enum | BaseModel
InferableFlagT = TypeVar('InferableFlagT', bound=InferableFlagValue)

__all__ = ['ErrorCode', 'FeatureFlag', 'Flag', 'FlagEvaluationDetails', 'LogfireProvider', 'Reason', 'feature_context', 'feature_flag', 'flag']

class _FlagAdapter(Protocol[T]):
    """Private compatibility boundary implemented by the current variables engine."""
    name: str
    value_type: Any
    description: str | None
    type_adapter: Any
    def evaluate_flag(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagResolutionDetails[T]: ...
    def override_for_testing(self, value: T) -> AbstractContextManager[None]: ...

class Flag(Generic[T]):
    """A typed feature flag with a safe code default.

    Values are validated with Pydantic before they are returned. Parameterized containers and
    nullable types need an explicit ``type=`` because Python cannot recover their element type from
    a runtime default such as ``[]`` or ``None``.
    """
    @overload
    def __init__(self, name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> None: ...
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
        """Evaluate the flag and return standard OpenFeature evaluation details."""
    def evaluate(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails[T]:
        """Alias for :meth:`details`, retained for the initial boolean API."""
    def override_for_testing(self, value: T) -> AbstractContextManager[None]:
        """Temporarily replace the flag value in the current context."""

class FeatureFlag(Flag[bool]):
    """A boolean feature flag with a safe code default."""
    def __init__(self, name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> None:
        """Define a boolean feature flag backed by the configured Logfire provider."""
    def is_enabled(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> bool:
        """Return whether the feature is enabled for the evaluation context."""

class LogfireProvider(AbstractProvider):
    """OpenFeature provider backed by flags declared through Logfire.

    Register this provider explicitly with OpenFeature. Constructing a :class:`Flag` never changes
    OpenFeature's process-global provider registry.
    """
    def __init__(self, logfire_instance: Logfire | None = None) -> None: ...
    def get_metadata(self) -> Metadata:
        """Return the provider metadata exposed through OpenFeature."""
    def resolve_boolean_details(self, flag_key: str, default_value: bool, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[bool]:
        """Resolve a boolean flag."""
    def resolve_string_details(self, flag_key: str, default_value: str, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[str]:
        """Resolve a string flag."""
    def resolve_integer_details(self, flag_key: str, default_value: int, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[int]:
        """Resolve an integer flag."""
    def resolve_float_details(self, flag_key: str, default_value: float, evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[float]:
        """Resolve a floating-point flag."""
    def resolve_object_details(self, flag_key: str, default_value: Sequence[FlagValueType] | Mapping[str, FlagValueType], evaluation_context: EvaluationContext | None = None) -> FlagResolutionDetails[Sequence[FlagValueType] | Mapping[str, FlagValueType]]:
        """Resolve an object flag as JSON-compatible data."""

@overload
def flag(name: str, *, default: InferableFlagT, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[InferableFlagT]: ...
@overload
def flag(name: str, *, type: TypeForm[T], default: T, description: str | None = None, logfire_instance: Logfire | None = None) -> Flag[T]: ...
def feature_flag(name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> FeatureFlag:
    """Define a boolean feature flag with a safe code default."""
def feature_context(targeting_key: str, *, attributes: Mapping[str, Any] | None = None) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for feature-flag evaluations."""
