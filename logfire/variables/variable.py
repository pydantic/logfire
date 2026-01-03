from __future__ import annotations as _annotations

import inspect
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from importlib.util import find_spec
from typing import Any, Generic, Protocol, TypeVar

from opentelemetry.trace import get_current_span
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

if find_spec('anyio') is not None:
    # Use anyio for running sync functions on separate threads in an event loop if it is available
    from anyio.to_thread import run_sync as to_thread
else:
    from asyncio import to_thread

import logfire
from logfire.variables.abstract import ResolvedVariable

__all__ = ('ResolveFunction', 'is_resolve_function', 'Variable')

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


_VARIABLE_OVERRIDES: ContextVar[dict[str, Any] | None] = ContextVar('_VARIABLE_OVERRIDES', default=None)

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
    value_type: type[T] | None = None
    """The expected type of this variable's values."""
    default: T | ResolveFunction[T]
    """Default value or function to compute the default."""
    description: str | None = None
    """Description of the variable."""

    logfire_instance: logfire.Logfire
    """The Logfire instance this variable is associated with."""

    def __init__(
        self,
        name: str,
        *,
        type: type[T],
        default: T | ResolveFunction[T],
        description: str | None = None,
        logfire_instance: logfire.Logfire,
    ):
        """Create a new managed variable.

        Args:
            name: Unique name identifying this variable.
            type: The expected type of this variable's values, used for validation.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            description: Optional human-readable description of what this variable controls.
            logfire_instance: The Logfire instance this variable is associated with. Used to determine config, etc.
        """
        self.name = name
        self.value_type = type
        self.default = default
        self.description = description

        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='variables')
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
        await to_thread(self.refresh_sync, force)

    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
        self.logfire_instance.config.get_variable_provider().refresh(force=force)

    def get(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> ResolvedVariable[T]:
        """Resolve the variable and return full details including variant and any errors.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
                If not provided and there is an active trace, its trace ID is used to ensure
                the same value is used throughout a single trace.
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable object containing the resolved value, selected variant,
            and any errors that occurred.
        """
        # TODO:
        #  * Should we include the serialized value as an attribute here?
        #  * Should we _not_ include the deserialized value as an attribute here?
        #  * Should some/all of the above be configurable? On a logfire/variable/call-site-specific basis?
        #   TODO: Alex says "i think the most important part is that it should be possible to globally disable creating these spans entirely, or have them off by default and allow globally enabling them."

        merged_attributes = self._get_merged_attributes(attributes)

        # Set the targeting key based on the current trace ID if appropriate
        if targeting_key is None and (current_trace_id := get_current_span().get_span_context().trace_id):
            # If there is no active trace, the current_trace_id will be zero
            targeting_key = f'trace_id:{current_trace_id:032x}'

        # Include the variable name directly here to make the span name more useful,
        # it'll still be low cardinality. This also prevents it from being scrubbed from the message.
        # Don't inline the f-string to avoid f-string magic.
        span_name = f'Resolve variable {self.name}'
        with self.logfire_instance.span(
            span_name,
            name=self.name,
            targeting_key=targeting_key,
            attributes=merged_attributes,
        ) as span:
            result = self._resolve(targeting_key, merged_attributes)
            span.set_attributes(
                {
                    'name': result.name,
                    'value': result.value,
                    'variant': result.variant,
                    'reason': result._reason,  # pyright: ignore[reportPrivateUsage]
                }
            )
            if result.exception:
                span.record_exception(result.exception)
            return result

    def _resolve(
        self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> ResolvedVariable[T]:
        try:
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and (
                context_value := context_overrides.get(self.name)
            ) is not None:
                if is_resolve_function(context_value):
                    context_value = context_value(targeting_key, attributes)
                return ResolvedVariable(name=self.name, value=context_value, _reason='context_override')

            provider = self.logfire_instance.config.get_variable_provider()
            serialized_result = provider.get_serialized_value(self.name, targeting_key, attributes)

            if serialized_result.value is None:
                default = self._get_default(targeting_key, attributes)
                return _with_value(serialized_result, default)

            try:
                value = self.type_adapter.validate_json(serialized_result.value)
            except ValidationError as e:
                default = self._get_default(targeting_key, attributes)
                return ResolvedVariable(name=self.name, value=default, exception=e, _reason='validation_error')

            return ResolvedVariable(name=self.name, value=value, variant=serialized_result.variant, _reason='resolved')

        except Exception as e:
            default = self._get_default(targeting_key, attributes)
            return ResolvedVariable(name=self.name, value=default, exception=e, _reason='other_error')

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


def _with_value(details: ResolvedVariable[Any], new_value: T) -> ResolvedVariable[T]:
    """Return a copy of the provided resolution details, just with a different value.

    Args:
        details: Existing resolution details to modify.
        new_value: The new value to use.

    Returns:
        A new ResolvedVariable with the given value.
    """
    return replace(details, value=new_value)
