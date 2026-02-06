from __future__ import annotations as _annotations

import inspect
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from opentelemetry.trace import get_current_span
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

if TYPE_CHECKING:
    from logfire.variables.config import VariableConfig

if find_spec('anyio') is not None:  # pragma: no branch
    # Use anyio for running sync functions on separate threads in an event loop if it is available
    from anyio.to_thread import run_sync as to_thread
else:
    from asyncio import to_thread  # pragma: no cover

import logfire
from logfire.variables.abstract import ResolvedVariable

__all__ = (
    'ResolveFunction',
    'is_resolve_function',
    'Variable',
    'targeting_context',
)

T_co = TypeVar('T_co', covariant=True)


_VARIABLE_OVERRIDES: ContextVar[dict[str, Any] | None] = ContextVar('_VARIABLE_OVERRIDES', default=None)

# Context var for explicit variant selection (bypasses rollout)
_VARIANT_OVERRIDES: ContextVar[dict[str, str] | None] = ContextVar('_VARIANT_OVERRIDES', default=None)


@dataclass
class _TargetingContextData:
    """Internal data structure for targeting context."""

    default: str | None = None
    """Default targeting key for all variables."""
    by_variable: dict[str, str] = field(default_factory=dict[str, str])
    """Variable-specific targeting keys (variable name -> targeting key)."""


_TARGETING_CONTEXT: ContextVar[_TargetingContextData | None] = ContextVar('_TARGETING_CONTEXT', default=None)


class ResolveFunction(Protocol[T_co]):
    """Protocol for functions that resolve variable values based on context."""

    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        """Resolve the variable value given a targeting key and attributes."""
        raise NotImplementedError


def is_resolve_function(f: Any) -> TypeIs[ResolveFunction[Any]]:
    """Check if a callable matches the ResolveFunction signature.

    A resolve function is any callable that can be called with exactly two positional arguments
    (targeting_key and attributes). This includes:
    - Functions/lambdas with exactly 2 parameters
    - Functions with 2+ parameters where all after the first 2 have defaults
    - Functions with *args or **kwargs

    Args:
        f: The object to check.

    Returns:
        True if the callable can be invoked with two positional arguments.
    """
    if not callable(f):
        return False
    try:
        signature = inspect.signature(f)
    except (ValueError, TypeError):
        # Can't get signature (e.g., built-in), assume not a resolve function
        return False

    params = list(signature.parameters.values())
    if not params:
        return False

    # Count required positional parameters and check for *args
    required_positional = 0
    has_var_positional = False
    optional_positional = 0

    for param in params:
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            has_var_positional = True
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            # **kwargs doesn't affect positional argument count
            pass
        elif param.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if param.default is inspect.Parameter.empty:
                required_positional += 1
            else:
                optional_positional += 1
        elif param.kind == inspect.Parameter.KEYWORD_ONLY:  # pragma: no branch
            # Keyword-only params don't affect positional argument count
            pass

    # Can be called with exactly 2 positional args if:
    # - Has *args (can accept any number), OR
    # - Required positional params <= 2 AND total positional params >= 2
    total_positional = required_positional + optional_positional
    if has_var_positional:
        return required_positional <= 2
    else:
        return required_positional <= 2 and total_positional >= 2


class Variable(Generic[T_co]):
    """A managed variable that can be resolved dynamically based on configuration."""

    name: str
    """Unique name identifying this variable."""
    value_type: type[T_co]
    """The expected type of this variable's values."""
    default: T_co | ResolveFunction[T_co]
    """Default value or function to compute the default."""
    description: str | None
    """Description of the variable."""

    logfire_instance: logfire.Logfire
    """The Logfire instance this variable is associated with."""

    def __init__(
        self,
        name: str,
        *,
        type: type[T_co],
        default: T_co | ResolveFunction[T_co],
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
        self.type_adapter = TypeAdapter[T_co](type)
        self._on_change_callbacks: list[Callable[[], None]] = []

        # Create a cached deserialization function for this variable instance.
        # Returns T | Exception. Only successful results are cached; exceptions are
        # returned but not cached so that transient errors don't persist permanently.
        _cache: dict[str, T_co] = {}
        _cache_order: list[str] = []
        _cache_maxsize = 128
        _cache_lock = threading.Lock()

        def _deserialize_cached(serialized_value: str) -> T_co | Exception:
            with _cache_lock:
                if serialized_value in _cache:
                    return _cache[serialized_value]
            try:
                result = self.type_adapter.validate_json(serialized_value)
            except Exception as e:
                return e
            with _cache_lock:
                # Evict oldest entry if cache is full
                if len(_cache) >= _cache_maxsize:
                    oldest = _cache_order.pop(0)
                    _cache.pop(oldest, None)
                _cache[serialized_value] = result
                _cache_order.append(serialized_value)
            return result

        self._deserialize_cached = _deserialize_cached

    @contextmanager
    def override(self, value: T_co | ResolveFunction[T_co]) -> Iterator[None]:
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

    @contextmanager
    def use_variant(self, variant_key: str) -> Iterator[None]:
        """Context manager to select a specific variant, bypassing rollout weights.

        This allows you to explicitly select a configured variant by key, regardless of
        the rollout configuration. Useful for testing specific variants or for playground
        scenarios where you want to preview a particular variant.

        Args:
            variant_key: The key of the variant to select. If the variant doesn't exist
                in the configuration, resolution will fall back to the default behavior.

        Example:
            ```python skip="true"
            # Select the "experimental" variant for all resolutions within this context
            with my_variable.use_variant('experimental'):
                value = my_variable.get().value  # Always gets "experimental" variant
            ```
        """
        current = _VARIANT_OVERRIDES.get() or {}
        token = _VARIANT_OVERRIDES.set({**current, self.name: variant_key})
        try:
            yield
        finally:
            _VARIANT_OVERRIDES.reset(token)

    async def refresh(self, force: bool = False):
        """Asynchronously refresh the variable."""
        await to_thread(self.refresh_sync, force)

    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
        self.logfire_instance.config.get_variable_provider().refresh(force=force)

    def on_change(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback to be called when this variable's remote configuration changes.

        The callback receives no arguments. Call `variable.get()` inside the callback
        to see the new value. Callbacks run on the provider's polling thread, so they
        should be fast and non-blocking.

        Can be used as a decorator:

            @my_var.on_change
            def handle_change():
                new_value = my_var.get().value
                invalidate_cache()

        Args:
            callback: A no-argument callable to invoke when the variable's config changes.

        Returns:
            The callback (for use as a decorator).
        """
        self._on_change_callbacks.append(callback)
        return callback

    def _notify_change(self) -> None:
        """Internal: fire all registered on_change callbacks."""
        for callback in self._on_change_callbacks:
            try:
                callback()
            except Exception:
                import logging

                logging.getLogger('logfire').exception(f'Error in on_change callback for variable {self.name!r}')

    def get(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        variant: str | None = None,
    ) -> ResolvedVariable[T_co]:
        """Resolve the variable and return full details including variant and any errors.

        Args:
            targeting_key: Optional key for deterministic variant selection (e.g., user ID).
                If not provided, falls back to contextvar targeting key (set via targeting_context),
                then to the current trace ID if there is an active trace.
            attributes: Optional attributes for condition-based targeting rules.
            variant: Optional explicit variant key to select. If provided, bypasses rollout
                weights and targeting, directly selecting the specified variant. If the variant
                doesn't exist in the configuration, falls back to default resolution.

        Returns:
            A ResolvedVariable object containing the resolved value, selected variant,
            and any errors that occurred.
        """
        # Check for variant override from context if not specified at call-site
        if variant is None:
            variant = _get_contextvar_variant_override(self.name)
        merged_attributes = self._get_merged_attributes(attributes)

        # Targeting key resolution: call-site > contextvar > trace_id
        if targeting_key is None:
            targeting_key = _get_contextvar_targeting_key(self.name)

        if targeting_key is None and (current_trace_id := get_current_span().get_span_context().trace_id):
            # If there is no active trace, the current_trace_id will be zero
            targeting_key = f'trace_id:{current_trace_id:032x}'

        # Include the variable name directly here to make the span name more useful,
        # it'll still be low cardinality. This also prevents it from being scrubbed from the message.
        # Don't inline the f-string to avoid f-string magic.
        span_name = f'Resolve variable {self.name}'
        with ExitStack() as stack:
            span: logfire.LogfireSpan | None = None
            if self.logfire_instance.config.variables.instrument:
                span = stack.enter_context(
                    self.logfire_instance.span(
                        span_name,
                        name=self.name,
                        targeting_key=targeting_key,
                        attributes=merged_attributes,
                    )
                )
            result = self._resolve(targeting_key, merged_attributes, span, variant)
            if span is not None:
                # Serialize value safely for OTel span attributes, which only support primitives.
                # Try to JSON serialize the value; if that fails, fall back to string representation.
                try:
                    serialized_value = self.type_adapter.dump_json(result.value).decode('utf-8')
                except Exception:
                    serialized_value = repr(result.value)
                span.set_attributes(
                    {
                        'name': result.name,
                        'value': serialized_value,
                        'variant': result.variant,
                        'reason': result._reason,  # pyright: ignore[reportPrivateUsage]
                    }
                )
                if result.exception:
                    span.record_exception(
                        result.exception,
                    )
            return result

    def _resolve(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        variant: str | None = None,
    ) -> ResolvedVariable[T_co]:
        serialized_result: ResolvedVariable[str | None] | None = None
        try:
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and self.name in context_overrides:
                context_value = context_overrides[self.name]
                if is_resolve_function(context_value):
                    context_value = context_value(targeting_key, attributes)
                return ResolvedVariable(name=self.name, value=context_value, _reason='context_override')

            provider = self.logfire_instance.config.get_variable_provider()

            # If explicit variant is requested, try to get that specific variant
            if variant is not None:
                serialized_result = provider.get_serialized_value_for_variant(self.name, variant)
                if serialized_result.value is not None:
                    # Successfully got the explicit variant
                    value_or_exc = self._deserialize_cached(serialized_result.value)
                    if isinstance(value_or_exc, Exception):
                        if span:  # pragma: no branch
                            span.set_attribute('invalid_serialized_variant', serialized_result.variant)
                            span.set_attribute('invalid_serialized_value', serialized_result.value)
                        default = self._get_default(targeting_key, attributes)
                        reason: str = 'validation_error' if isinstance(value_or_exc, ValidationError) else 'other_error'
                        return ResolvedVariable(name=self.name, value=default, exception=value_or_exc, _reason=reason)
                    return ResolvedVariable(
                        name=self.name, value=value_or_exc, variant=serialized_result.variant, _reason='resolved'
                    )
                # Variant not found - fall through to default resolution

            serialized_result = provider.get_serialized_value(self.name, targeting_key, attributes)

            if serialized_result.value is None:
                default = self._get_default(targeting_key, attributes)
                return _with_value(serialized_result, default)

            # Use cached deserialization - returns T | Exception
            value_or_exc = self._deserialize_cached(serialized_result.value)
            if isinstance(value_or_exc, Exception):
                if span:  # pragma: no branch
                    span.set_attribute('invalid_serialized_variant', serialized_result.variant)
                    span.set_attribute('invalid_serialized_value', serialized_result.value)
                default = self._get_default(targeting_key, attributes)
                reason: str = 'validation_error' if isinstance(value_or_exc, ValidationError) else 'other_error'
                return ResolvedVariable(name=self.name, value=default, exception=value_or_exc, _reason=reason)

            return ResolvedVariable(
                name=self.name, value=value_or_exc, variant=serialized_result.variant, _reason='resolved'
            )

        except Exception as e:
            if span and serialized_result is not None:  # pragma: no cover
                span.set_attribute('invalid_serialized_variant', serialized_result.variant)
                span.set_attribute('invalid_serialized_value', serialized_result.value)
            default = self._get_default(targeting_key, attributes)
            return ResolvedVariable(name=self.name, value=default, exception=e, _reason='other_error')

    def _get_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> T_co:
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

    def to_config(self) -> VariableConfig:
        """Create a VariableConfig from this Variable instance.

        This creates a minimal config with just the name, schema, and example.
        No variants are created - use this to generate a template config that can be edited.

        Returns:
            A VariableConfig with minimal configuration.
        """
        from logfire.variables.config import Rollout, VariableConfig

        # Get JSON schema from the type adapter
        json_schema = self.type_adapter.json_schema()

        # Get the serialized default value as an example (if not a function)
        example: str | None = None
        if not is_resolve_function(self.default):
            example = self.type_adapter.dump_json(self.default).decode('utf-8')

        return VariableConfig(
            name=self.name,
            description=self.description,
            variants={},
            rollout=Rollout(variants={}),
            overrides=[],
            json_schema=json_schema,
            example=example,
        )


def _with_value(details: ResolvedVariable[Any], new_value: T_co) -> ResolvedVariable[T_co]:
    """Return a copy of the provided resolution details, just with a different value.

    Args:
        details: Existing resolution details to modify.
        new_value: The new value to use.

    Returns:
        A new ResolvedVariable with the given value.
    """
    return replace(details, value=new_value)


@contextmanager
def targeting_context(
    targeting_key: str,
    variables: Sequence[Variable[Any]] | None = None,
) -> Iterator[None]:
    """Set the targeting key for variable resolution within this context.

    The targeting key is used for deterministic variant selection - the same targeting key
    will always resolve to the same variant for a given variable configuration.

    Args:
        targeting_key: The targeting key to use for deterministic variant selection
            (e.g., user ID, organization ID).
        variables: If provided, only apply this targeting key to these specific variables.
            If not provided, this becomes the default targeting key for all variables.

    Variable-specific targeting always takes precedence over the default, regardless
    of nesting order. Call-site explicit targeting_key still wins over everything.

    Example:
        # Set default targeting for all variables
        with targeting_context("user123"):
            value = my_variable.get()  # uses "user123"

        # Set targeting for specific variables
        with targeting_context("org456", variables=[org_variable]):
            org_value = org_variable.get()  # uses "org456"
            other_value = other_variable.get()  # uses default or trace_id

        # Combine default and specific - order doesn't matter for precedence
        with targeting_context("user123"):
            with targeting_context("org456", variables=[org_variable]):
                org_value = org_variable.get()  # uses "org456" (specific wins)
                other_value = other_variable.get()  # uses "user123" (default)
    """
    current = _TARGETING_CONTEXT.get()

    # Build new context by merging with current
    new_data = _TargetingContextData(
        default=current.default if current else None,
        by_variable=dict(current.by_variable) if current else {},
    )

    if variables is None:
        new_data.default = targeting_key
    else:
        for var in variables:
            new_data.by_variable[var.name] = targeting_key

    token = _TARGETING_CONTEXT.set(new_data)
    try:
        yield
    finally:
        _TARGETING_CONTEXT.reset(token)


def _get_contextvar_targeting_key(variable_name: str) -> str | None:
    """Get the targeting key from context for a specific variable.

    Args:
        variable_name: The name of the variable to get the targeting key for.

    Returns:
        The targeting key if one is set in context, None otherwise.
        Variable-specific targeting takes precedence over the default.
    """
    ctx = _TARGETING_CONTEXT.get()
    if ctx is None:
        return None
    # Variable-specific takes precedence over default
    return ctx.by_variable.get(variable_name, ctx.default)


def _get_contextvar_variant_override(variable_name: str) -> str | None:
    """Get the variant override from context for a specific variable.

    Args:
        variable_name: The name of the variable to get the variant override for.

    Returns:
        The variant key if one is set in context, None otherwise.
    """
    ctx = _VARIANT_OVERRIDES.get()
    if ctx is None:
        return None
    return ctx.get(variable_name)
