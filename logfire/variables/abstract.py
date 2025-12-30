from __future__ import annotations as _annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar

if TYPE_CHECKING:
    from logfire.variables.config import VariableConfig, VariablesConfig

__all__ = (
    'ResolvedVariable',
    'VariableProvider',
    'NoOpVariableProvider',
    'VariableWriteError',
    'VariableNotFoundError',
    'VariableAlreadyExistsError',
)

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


class VariableWriteError(Exception):
    """Base exception for variable write operation failures."""

    pass


class VariableNotFoundError(VariableWriteError):
    """Raised when a variable is not found."""

    pass


class VariableAlreadyExistsError(VariableWriteError):
    """Raised when trying to create a variable that already exists."""

    pass


@dataclass(kw_only=True)
class ResolvedVariable(Generic[T_co]):
    """Details about a variable resolution including value, variant, and any errors.

    This class can be used as a context manager. When used as a context manager, it
    automatically sets baggage with the variable name and variant, enabling downstream
    spans and logs to be associated with the variable resolution that was active at the time.

    Example:
        ```python
        my_var = logfire.var(name='my_var', type=str, default='default')
        with my_var.get() as details:
            # Inside this context, baggage is set with:
            # logfire.variables.my_var = <variant_name> (or '<code_default>' if no variant)
            value = details.value
            # Any spans/logs created here will have the baggage attached
        ```
    """

    name: str
    """The name of the variable."""
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

    def __post_init__(self):
        self._exit_stack = ExitStack()

    def __enter__(self):
        self._exit_stack.__enter__()

        import logfire

        self._exit_stack.enter_context(
            logfire.set_baggage(**{f'logfire.variables.{self.name}': self.variant or '<code_default>'})
        )

        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        self._exit_stack.__exit__(exc_type, exc_val, exc_tb)


class VariableProvider(ABC):
    """Abstract base class for variable value providers."""

    @abstractmethod
    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Retrieve the serialized value for a variable.

        Args:
            variable_name: The name of the variable to resolve.
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
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

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Retrieve the full configuration for a variable.

        Args:
            name: The name of the variable.

        Returns:
            The VariableConfig if found, or None if the variable doesn't exist.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation returns None.
        """
        return None

    def get_all_variables_config(self) -> VariablesConfig:
        """Retrieve all variable configurations.

        This is used by push_variables() to compute diffs.

        Returns:
            A VariablesConfig containing all variable configurations.
            Returns an empty VariablesConfig if no configs are available.
        """
        from logfire.variables.config import VariablesConfig

        return VariablesConfig(variables={})

    def create_variable(self, config: VariableConfig) -> VariableConfig:
        """Create a new variable configuration.

        Args:
            config: The configuration for the new variable.

        Returns:
            The created VariableConfig.

        Raises:
            VariableAlreadyExistsError: If a variable with this name already exists.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning and returns the config unchanged.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )
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

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning and returns the config unchanged.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )
        return config

    def delete_variable(self, name: str) -> None:
        """Delete a variable configuration.

        Args:
            name: The name of the variable to delete.

        Raises:
            VariableNotFoundError: If the variable does not exist.

        Note:
            Subclasses should override this method to provide actual implementations.
            The default implementation emits a warning.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable writes',
            stacklevel=2,
        )

    def batch_update(self, updates: dict[str, VariableConfig | None]) -> None:
        """Update multiple variables atomically.

        This default implementation processes updates sequentially. Subclasses
        (especially remote providers) may override this to batch operations
        into a single API call for better performance.

        Args:
            updates: A mapping of variable names to their new configurations.
                Unrecognized names will be created.
                A None value means the variable should be deleted.
                All others will be updated.
        """
        for name, config in updates.items():
            if config is None:
                self.delete_variable(name)
            elif self.get_variable_config(name) is None:
                self.create_variable(config)
            else:
                self.update_variable(name, config)


@dataclass
class NoOpVariableProvider(VariableProvider):
    """A variable provider that always returns None, used when no provider is configured."""

    def get_serialized_value(
        self,
        variable_name: str,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> ResolvedVariable[str | None]:
        """Return None for all variable lookups.

        Args:
            variable_name: The name of the variable to resolve (ignored).
            targeting_key: Optional key for deterministic variant selection (ignored).
            attributes: Optional attributes for condition-based targeting rules (ignored).

        Returns:
            A ResolvedVariable with value=None.
        """
        return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Return None for all variable lookups.

        Args:
            name: The name of the variable (ignored).

        Returns:
            Always None since no provider is configured.
        """
        return None
