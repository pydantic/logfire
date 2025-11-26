from __future__ import annotations as _annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, TypeVar

from logfire.variables.variable import VariableResolutionDetails

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


class VariableProvider(ABC):
    """Abstract base class for variable value providers."""

    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        """Retrieve the serialized value for a variable."""
        raise NotImplementedError

    def shutdown(self):
        """Clean up any resources used by the provider."""
        pass


class NoOpVariableProvider(VariableProvider):
    """A variable provider that always returns None, used when no provider is configured."""

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> VariableResolutionDetails[str | None]:
        """Return None for all variable lookups."""
        return VariableResolutionDetails(value=None, _reason='resolved')
