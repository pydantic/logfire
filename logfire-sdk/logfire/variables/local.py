from __future__ import annotations as _annotations

import threading
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel

from logfire.variables.abstract import (
    ResolvedVariable,
    VariableAlreadyExistsError,
    VariableNotFoundError,
    VariableProvider,
)
from logfire.variables.config import VariableConfig, VariablesConfig

__all__ = ('LocalVariableProvider',)


def _stage_config_structure(value: Any) -> Any:
    """Copy mutable configuration containers without deep-copying opaque payloads.

    A condition's Any value or a schema entry may contain a non-copyable object
    whose identity matters to matching. Only Logfire configuration models and
    built-in containers are copied; other values remain shared.
    """
    if isinstance(value, BaseModel) and any(
        cls.__module__ == VariableConfig.__module__ for cls in type(value).__mro__
    ):
        copied = value.model_copy(
            update={
                name: _stage_config_structure(getattr(value, name))
                for name in type(value).model_fields
            }
        )
        # Do not carry cached lookups that may reference the original graph.
        for name in set(copied.__dict__) - set(type(value).model_fields):
            copied.__dict__.pop(name, None)
        return copied
    if isinstance(value, dict):
        return {key: _stage_config_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stage_config_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_stage_config_structure(item) for item in value)
    if isinstance(value, set):
        return {_stage_config_structure(item) for item in value}
    return value



class LocalVariableProvider(VariableProvider):
    """Variable provider that resolves values from a local in-memory configuration.

    This provider stores a mutable `VariablesConfig` and supports both read and write operations.
    """

    def __init__(self, config: VariablesConfig):
        """Create a new local variable provider.

        Args:
            config: A VariablesConfig instance to use for variable resolution and mutation.
        """
        self._config = config
        self._lock = threading.RLock()

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Resolve a variable's serialized value from the local configuration.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
                If not provided and there is an active trace, its trace ID is used to ensure
                the same value is used across a trace.
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
        """
        with self._lock:
            return self._config.resolve_serialized_value(variable_name, targeting_key, attributes)

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Retrieve the full configuration for a variable.

        This method supports alias-based lookup, so you can pass either the
        variable's current name or any of its configured aliases.

        Args:
            name: The name (or alias) of the variable.

        Returns:
            The VariableConfig if found, or None if the variable doesn't exist.
        """
        with self._lock:
            return self._config._get_variable_config(name)  # pyright: ignore[reportPrivateUsage]

    def get_all_variables_config(self) -> VariablesConfig:
        """Retrieve all variable configurations.

        Returns:
            A VariablesConfig containing all variable configurations.
        """
        with self._lock:
            # Return a deep copy under the lock so callers (push diff / validation iterate
            # `variables.items()`) get a stable snapshot. Without this, a concurrent
            # create/update/delete_variable mutating `self._config.variables` in place can raise
            # "dictionary changed size during iteration".
            return self._config.model_copy(deep=True)

    def create_variable(self, config: VariableConfig) -> VariableConfig:
        """Create a new variable configuration.

        Args:
            config: The configuration for the new variable.

        Returns:
            The created VariableConfig.

        Raises:
            VariableAlreadyExistsError: If a variable with this name already exists.
        """
        with self._lock:
            if config.name in self._config.variables:
                raise VariableAlreadyExistsError(f"Variable '{config.name}' already exists")
            self._config.variables[config.name] = config
            self._config._invalidate_alias_map()  # pyright: ignore[reportPrivateUsage]
        return config

    def update_variable(self, name: str, config: VariableConfig) -> VariableConfig:
        """Update an existing variable configuration.

        Args:
            name: The name of the variable to update.
            config: The new configuration for the variable.

        Returns:
            The updated VariableConfig.

        Raises:
            VariableNotFoundError: If the variable does not exist.
        """
        with self._lock:
            if name not in self._config.variables:
                raise VariableNotFoundError(f"Variable '{name}' not found")
            self._config.variables[name] = config
            self._config._invalidate_alias_map()  # pyright: ignore[reportPrivateUsage]
        return config

    def delete_variable(self, name: str) -> None:
        """Delete a variable configuration.

        Args:
            name: The name of the variable to delete.

        Raises:
            VariableNotFoundError: If the variable does not exist.
        """
        with self._lock:
            if name not in self._config.variables:
                raise VariableNotFoundError(f"Variable '{name}' not found")
            del self._config.variables[name]
            self._config._invalidate_alias_map()  # pyright: ignore[reportPrivateUsage]

    def batch_update(self, updates: dict[str, VariableConfig | None]) -> None:
        """Apply a batch atomically to the local configuration.

        If any operation fails, the configuration is left unchanged. Readers and
        other writes cannot observe or interleave with a partially applied batch.
        """
        if not updates:
            return

        with self._lock:
            # Run subclass overrides against an isolated model graph, while keeping
            # opaque values (e.g. objects in condition.value) identity-stable.
            original_config = self._config
            staged_config = _stage_config_structure(original_config)
            self._config = staged_config
            try:
                VariableProvider.batch_update(self, updates)
                # A batch must not replace unrelated objects returned earlier by
                # get_variable_config(). Only explicitly updated entries are staged.
                original_config.variables = {
                    name: staged_value if name in updates else original_config.variables.get(name, staged_value)
                    for name, staged_value in staged_config.variables.items()
                }
                original_config._invalidate_alias_map()  # pyright: ignore[reportPrivateUsage]
            finally:
                self._config = original_config
