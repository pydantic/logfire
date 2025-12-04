from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

__all__ = ['VariableResolutionDetails', 'VariableProvider', 'NoOpVariableProvider']

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)

@dataclass(kw_only=True)
class VariableResolutionDetails(Generic[T_co]):
    """Details about a variable resolution including value, variant, and any errors."""
    value: T_co
    variant: str | None = ...
    exception: Exception | None = ...

class VariableProvider(ABC):
    """Abstract base class for variable value providers."""
    @abstractmethod
    def get_serialized_value(self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> VariableResolutionDetails[str | None]:
        """Retrieve the serialized value for a variable.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails containing the serialized value (or None if not found).
        """
    def refresh(self, force: bool = False):
        """Refresh the value provider.

        Only relevant to remote providers where initial retrieval may be asynchronous.
        Calling this method is intended to block until an initial retrieval happens, but is not guaranteed
        to eagerly retrieve any updates if the provider implements some kind of caching; the `force` argument
        is provided as a way to ignore any caching.

        Args:
            force: Whether to force refresh. If using a provider with caching, setting this to `True` triggers a refresh
            ignoring the cache.
        """
    def shutdown(self) -> None:
        """Clean up any resources used by the provider."""

@dataclass
class NoOpVariableProvider(VariableProvider):
    """A variable provider that always returns None, used when no provider is configured."""
    def get_serialized_value(self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> VariableResolutionDetails[str | None]:
        """Return None for all variable lookups.

        Args:
            variable_name: The name of the variable to resolve (ignored).
            targeting_key: Optional key for deterministic variant selection (ignored).
            attributes: Optional attributes for condition-based targeting rules (ignored).

        Returns:
            A VariableResolutionDetails with value=None.
        """
