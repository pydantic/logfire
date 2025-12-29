from __future__ import annotations as _annotations

from collections.abc import Mapping
from typing import Any, Callable

from logfire.variables.abstract import ResolvedVariable, VariableProvider
from logfire.variables.config import VariablesConfig

__all__ = ('LocalVariableProvider',)


class LocalVariableProvider(VariableProvider):
    """Variable provider that resolves values from a local in-memory configuration."""

    def __init__(
        self,
        config: VariablesConfig | Callable[[], VariablesConfig],
    ):
        """Create a new local variable provider.

        Args:
            config: Either a VariablesConfig instance, or a callable that returns one.
                Using a callable allows for dynamic configuration reloading.
        """
        super().__init__()
        if isinstance(config, VariablesConfig):

            def get_config() -> VariablesConfig:
                return config
        else:
            get_config = config

        self.get_config = get_config

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Resolve a variable's serialized value from the local configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
                If not provided and there is an active trace, its trace ID is used to ensure
                the same value is used across a trace.
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
        """
        return self.get_config().resolve_serialized_value(variable_name, targeting_key, attributes)
