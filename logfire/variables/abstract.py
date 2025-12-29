from __future__ import annotations as _annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

__all__ = ('ResolvedVariable', 'VariableProvider', 'NoOpVariableProvider')

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


@dataclass(kw_only=True)
class ResolvedVariable(Generic[T_co]):
    """Details about a variable resolution including value, variant, and any errors.

    This class can be used as a context manager. When used as a context manager, it
    automatically sets baggage with the variable name and variant, enabling downstream
    spans and logs to be associated with the variable resolution that was active at the time.

    Example:
        ```python
        my_var = logfire.var(name='my_var', default='default', type=str)
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

        # TODO:
        #  * Should we "nest" the value into a 'logfire.variables' key, rather than separate keys for each variable?
        #  * Is there a better value to use here over `<code_default>` when the variant is None?
        #  * Should either of the above be configurable?
        #  * Should we _require_ you to enter the context to get the value of a variable?
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
