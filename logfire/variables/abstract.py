from __future__ import annotations as _annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

__all__ = ('VariableResolutionDetails', 'VariableProvider', 'NoOpVariableProvider')

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


@dataclass(kw_only=True)
class VariableResolutionDetails(Generic[T_co]):
    """Details about a variable resolution including value, variant, and any errors."""

    value: T_co
    """The resolved value of the variable."""
    variant: str | None = None
    """The key of the selected variant, if any."""
    exception: Exception | None = None
    """Any exception that occurred during resolution."""
    _reason: Literal[
        'resolved',
        'context_override',
        'missing_config',
        'unrecognized_variable',
        'validation_error',
        'other_error',
        'no_provider',
    ]  # we might eventually make this public, but I didn't want to yet
    """Internal field indicating how the value was resolved."""


class VariableProvider(ABC):
    """Abstract base class for variable value providers."""

    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        """Retrieve the serialized value for a variable.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails containing the serialized value (or None if not found).
        """
        raise NotImplementedError

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
        pass

    def shutdown(self):
        """Clean up any resources used by the provider."""
        pass


@dataclass
class NoOpVariableProvider(VariableProvider):
    """A variable provider that always returns None, used when no provider is configured."""

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        """Return None for all variable lookups.

        Args:
            variable_name: The name of the variable to resolve (ignored).
            targeting_key: Optional key for deterministic variant selection (ignored).
            attributes: Optional attributes for condition-based targeting rules (ignored).

        Returns:
            A VariableResolutionDetails with value=None.
        """
        return VariableResolutionDetails(value=None, _reason='no_provider')
