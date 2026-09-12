from _typeshed import Incomplete
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from logfire import Logfire
from typing import Any, Protocol

__all__ = ['FeatureFlag', 'FlagEvaluationDetails', 'FlagEvaluationReason', 'feature_context', 'feature_flag']

FlagEvaluationReason: Incomplete

@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails:
    """The result of evaluating a feature flag."""
    flag_key: str
    value: bool
    variant: str | None = ...
    reason: FlagEvaluationReason = ...
    error_code: str | None = ...

class _FeatureFlagAdapter(Protocol):
    """Private compatibility boundary implemented by the current variables engine."""
    name: str
    description: str | None
    def evaluate_flag(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails: ...
    def override_for_testing(self, value: bool) -> AbstractContextManager[None]: ...

class FeatureFlag:
    """A boolean feature flag with a safe code default."""
    def __init__(self, name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> None:
        """Define a feature flag backed by the configured Logfire provider."""
    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
    def is_enabled(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> bool:
        """Return whether the feature is enabled for the evaluation context."""
    def evaluate(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> FlagEvaluationDetails:
        """Evaluate the flag and return feature-flag-specific resolution details."""
    def override_for_testing(self, value: bool) -> AbstractContextManager[None]:
        """Temporarily replace the flag value in the current context."""

def feature_flag(name: str, *, default: bool, description: str | None = None, logfire_instance: Logfire | None = None) -> FeatureFlag:
    """Define a boolean feature flag with a safe code default.

    Args:
        name: Unique identifier for the flag. Must match the name configured in Logfire.
        default: Value used before the flag is configured or when configuration is unavailable.
        description: Optional human-readable description of what the flag controls.
        logfire_instance: Optional configured Logfire instance. The default global instance is used
            when this is omitted.
    """
def feature_context(targeting_key: str, *, attributes: Mapping[str, Any] | None = None) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for managed-variable evaluations."""
