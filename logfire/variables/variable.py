from __future__ import annotations as _annotations

import asyncio
import inspect
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Generic, Protocol, TypeVar

from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

import logfire
from logfire.variables.abstract import VariableResolutionDetails

__all__ = ('ResolveFunction', 'is_resolve_function', 'Variable')

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


_VARIABLE_OVERRIDES = ContextVar[dict[str, Any] | None]('_VARIABLE_OVERRIDES', default=None)

_DEFAULT_SENTINEL = object()


class ResolveFunction(Protocol[T_co]):
    """Protocol for functions that resolve variable values based on context."""

    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        """Resolve the variable value given a targeting key and attributes."""
        raise NotImplementedError


def is_resolve_function(f: Any) -> TypeIs[ResolveFunction[Any]]:
    """Check if a callable matches the ResolveFunction signature.

    Args:
        f: The object to check.

    Returns:
        True if the callable has a signature matching ResolveFunction.
    """
    if not callable(f):
        return False
    signature = inspect.signature(f)
    params = list(signature.parameters.values())
    if len(params) == 2 and params[0].name == 'targeting_key' and params[1].name == 'attributes':
        return True
    return False


class Variable(Generic[T]):
    """A managed variable that can be resolved dynamically based on configuration."""

    name: str
    """Unique name identifying this variable."""
    default: T | ResolveFunction[T]
    """Default value or function to compute the default."""
    value_type: type[T] | None = None
    """The expected type of this variable's values."""

    logfire_instance: logfire.Logfire
    """The Logfire instance this variable is associated with."""

    def __init__(
        self,
        name: str,
        *,
        default: T | ResolveFunction[T],
        type: type[T],
        logfire_instance: logfire.Logfire,
    ):
        """Create a new managed variable.

        Args:
            name: Unique name identifying this variable.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            type: The expected type of this variable's values, used for validation.
            logfire_instance: The Logfire instance this variable is associated with. Used to determine config, etc.
        """
        self.name = name
        self.default = default

        self.logfire_instance = logfire_instance
        self.type_adapter = TypeAdapter[T](type)

    @contextmanager
    def override(self, value: T | ResolveFunction[T]) -> Iterator[None]:
        """Context manager to temporarily override this variable's value.

        Args:
            value: The value to use within this context, or a function that computes
                the value based on targeting_key and attributes.
        """
        current = _VARIABLE_OVERRIDES.get() or {}
        token = _VARIABLE_OVERRIDES.set({**current, self.name: value})
        try:
            yield
        finally:
            _VARIABLE_OVERRIDES.reset(token)

    async def refresh(self, force: bool = False):
        """Asynchronously refresh the variable."""
        await asyncio.to_thread(self.logfire_instance.config.get_variable_provider().refresh, force=force)

    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
        self.logfire_instance.config.get_variable_provider().refresh(force=force)

    def get(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> T:
        """Resolve and return the variable's value.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            The resolved value of the variable.
        """
        return (self.get_details(targeting_key, attributes)).value

    def get_details(
        self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> VariableResolutionDetails[T]:
        """Resolve the variable and return full details including variant and any errors.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A VariableResolutionDetails object containing the resolved value, selected variant,
            and any errors that occurred.
        """
        merged_attributes = self._get_merged_attributes(attributes)

        # TODO: How much of the following code should be in the try: except:?
        try:
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and (
                context_value := context_overrides.get(self.name)
            ) is not None:
                if is_resolve_function(context_value):
                    context_value = context_value(targeting_key, merged_attributes)
                return VariableResolutionDetails(value=context_value, _reason='context_override')

            provider = self.logfire_instance.config.get_variable_provider()
            serialized_result = provider.get_serialized_value(self.name, targeting_key, merged_attributes)

            if serialized_result.value is None:
                default = self._get_default(targeting_key, merged_attributes)
                return serialized_result.with_value(default)

            try:
                value = self.type_adapter.validate_json(serialized_result.value)
            except ValidationError as e:
                default = self._get_default(targeting_key, merged_attributes)
                return VariableResolutionDetails(value=default, exception=e, _reason='validation_error')

            return VariableResolutionDetails(value=value, variant=serialized_result.variant, _reason='resolved')

        except Exception as e:
            default = self._get_default(targeting_key, merged_attributes)
            return VariableResolutionDetails(value=default, exception=e, _reason='other_error')

    def _get_default(self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None) -> T:
        if is_resolve_function(self.default):
            return self.default(targeting_key, merged_attributes)
        else:
            return self.default

    def _get_merged_attributes(self, attributes: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        result = dict(attributes) if attributes else {}
        variables_options = self.logfire_instance.config.variables
        if variables_options.include_baggage_in_context:
            result.update(logfire.get_baggage())
        if variables_options.include_resource_attributes_in_context:
            result.update(self.logfire_instance.resource_attributes)
        return result
