from _typeshed import Incomplete
from collections.abc import Mapping
from logfire.variables.abstract import VariableProvider, VariableResolutionDetails
from logfire.variables.config import VariablesConfig
from typing import Any, Callable

__all__ = ['LocalVariableProvider']

class LocalVariableProvider(VariableProvider):
    """Variable provider that resolves values from a local in-memory configuration."""
    get_config: Incomplete
    def __init__(self, config: VariablesConfig | Callable[[], VariablesConfig]) -> None:
        """Create a new local variable provider.

        Args:
            config: Either a VariablesConfig instance, or a callable that returns one.
                Using a callable allows for dynamic configuration reloading.
        """
    def get_serialized_value(self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> VariableResolutionDetails[str | None]:
        """Resolve a variable's serialized value from the local configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails containing the serialized value (or None if not found).
        """
