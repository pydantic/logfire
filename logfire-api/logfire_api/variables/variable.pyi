import logfire
from _typeshed import Incomplete
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from logfire.variables.abstract import VariableResolutionDetails
from typing import Any, Generic, Protocol, TypeVar
from typing_extensions import TypeIs

__all__ = ['ResolveFunction', 'is_resolve_function', 'Variable']

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)

class ResolveFunction(Protocol[T_co]):
    """Protocol for functions that resolve variable values based on context."""
    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        """Resolve the variable value given a targeting key and attributes."""

def is_resolve_function(f: Any) -> TypeIs[ResolveFunction[Any]]:
    """Check if a callable matches the ResolveFunction signature.

    Args:
        f: The object to check.

    Returns:
        True if the callable has a signature matching ResolveFunction.
    """

class Variable(Generic[T]):
    """A managed variable that can be resolved dynamically based on configuration."""
    name: str
    default: T | ResolveFunction[T]
    value_type: type[T] | None
    logfire_instance: logfire.Logfire
    type_adapter: Incomplete
    def __init__(self, name: str, *, default: T | ResolveFunction[T], type: type[T], logfire_instance: logfire.Logfire) -> None:
        """Create a new managed variable.

        Args:
            name: Unique name identifying this variable.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            type: The expected type of this variable's values, used for validation.
            logfire_instance: The Logfire instance this variable is associated with. Used to determine config, etc.
        """
    @contextmanager
    def override(self, value: T | ResolveFunction[T]) -> Iterator[None]:
        """Context manager to temporarily override this variable's value.

        Args:
            value: The value to use within this context, or a function that computes
                the value based on targeting_key and attributes.
        """
    async def refresh(self, force: bool = False):
        """Asynchronously refresh the variable."""
    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
    def get(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> T:
        """Resolve and return the variable's value.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            The resolved value of the variable.
        """
    def get_details(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> VariableResolutionDetails[T]:
        """Resolve the variable and return full details including variant and any errors.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails object containing the resolved value, selected variant,
            and any errors that occurred.
        """
