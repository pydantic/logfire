from __future__ import annotations as _annotations

import json
import threading
from collections.abc import Mapping
from typing import Any

from logfire.variables._prompt import prompt_variable_name
from logfire.variables.abstract import (
    ResolvedVariable,
    VariableAlreadyExistsError,
    VariableNotFoundError,
    VariableProvider,
)
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

__all__ = ('LocalVariableProvider',)


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
        self._lock = threading.Lock()

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

    def create_prompt(
        self,
        *,
        slug: str,
        name: str,
        description: str | None = None,
        template: str | None = None,
        template_inputs_schema: dict[str, Any] | None = None,
    ) -> None:
        """Create a prompt in the local configuration.

        Mirrors the platform shape: a `prompt__<slug>` variable with no JSON schema; when
        `template` is given, a first version is stored and served via the implicit `latest`
        label (matching a fresh platform prompt's default rollout).

        Args:
            slug: The prompt slug, e.g. `support-agent`.
            name: Human-readable prompt name (not represented in the local config model).
            description: Optional prompt description.
            template: When set, stored as version 1 and served as `latest`.
            template_inputs_schema: JSON Schema for `{{field}}` template inputs.

        Raises:
            VariableAlreadyExistsError: If a prompt with this slug already exists.
        """
        variable_name = prompt_variable_name(slug)
        labels: dict[str, LabeledValue | LabelRef] = {}
        rollout = Rollout(labels={})
        latest_version: LatestVersion | None = None
        if template is not None:
            labels = {'latest': LabelRef(version=1, ref='latest')}
            rollout = Rollout(labels={'latest': 1.0})
            latest_version = LatestVersion(version=1, serialized_value=json.dumps(template))

        config = VariableConfig(
            name=variable_name,
            description=description,
            labels=labels,
            rollout=rollout,
            overrides=[],
            latest_version=latest_version,
            json_schema=None,
            template_inputs_schema=template_inputs_schema,
        )
        with self._lock:
            if variable_name in self._config.variables:
                raise VariableAlreadyExistsError(f"Prompt '{slug}' already exists")
            self._config.variables[variable_name] = config
            self._config._invalidate_alias_map()  # pyright: ignore[reportPrivateUsage]

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
