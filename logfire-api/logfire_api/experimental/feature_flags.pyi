from collections.abc import Mapping
from contextlib import AbstractContextManager
from logfire import Logfire
from logfire.variables.abstract import ResolvedVariable
from typing import Any, Protocol

__all__ = ['FeatureFlag', 'feature_context', 'feature_flag']

class FeatureFlag(Protocol):
    """The intentionally small public interface for an experimental boolean feature flag."""
    name: str
    description: str | None
    def is_enabled(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> bool:
        """Return whether the feature is enabled for the evaluation context."""
    def evaluate(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> ResolvedVariable[bool]:
        """Evaluate the flag and return its value and resolution details."""
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
