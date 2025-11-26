from __future__ import annotations as _annotations

from collections.abc import Callable, Mapping
from typing import Any

from logfire.variables.config import VariablesConfig

__all__ = ['LogfireLocalProvider']

from logfire.variables.providers.abstract import VariableProvider, VariableResolutionDetails


class LogfireLocalProvider(VariableProvider):
    """Variable provider that resolves values from a local in-memory configuration."""

    def __init__(
        self,
        config: VariablesConfig | Callable[[], VariablesConfig],
    ):
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
    ) -> VariableResolutionDetails[str | None]:
        """Resolve a variable's serialized value from the local configuration."""
        variables_config = self.get_config()

        variable_config = variables_config.variables.get(variable_name)
        if variable_config is None:
            return VariableResolutionDetails(value=None, _reason='missing_config')

        variant = variable_config.resolve_variant(targeting_key, attributes)
        if variant is None:
            return VariableResolutionDetails(value=None, _reason='resolved')
        else:
            return VariableResolutionDetails(value=variant.serialized_value, variant=variant.key, _reason='resolved')
