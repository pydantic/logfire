from __future__ import annotations as _annotations

import inspect
from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from functools import lru_cache
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
    'PromptVariable',
    'VariableBundle',
    'targeting_context',
    'override_variables',
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

        # Create a cached deserialization function for this variable instance.
        # Returns T | Exception to cache both successful deserializations and errors.
        @lru_cache(maxsize=128)
        def _deserialize_cached(serialized_value: str) -> T_co | Exception:
            try:
                return self.type_adapter.validate_json(serialized_value)
            except Exception as e:
                return e

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
                span.set_attributes(
                    {
                        'name': result.name,
                        'value': result.value,
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
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and (
                context_value := context_overrides.get(self.name)
            ) is not None:
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


@contextmanager
def override_variables(
    overrides: Mapping[Variable[Any], Any],
) -> Iterator[None]:
    """Context manager to temporarily override multiple variables' values at once.

    This is a convenience function for overriding multiple variables without nested
    context managers. Useful for testing or playground scenarios where you want to
    try different combinations of values.

    Args:
        overrides: A mapping of Variable instances to their override values.
            Values can be either direct values or ResolveFunction callables.

    Example:
        ```python skip="true"
        system_prompt = logfire.var(name='system_prompt', type=str, default='Default')
        temperature = logfire.var(name='temperature', type=float, default=0.7)
        model = logfire.var(name='model', type=str, default='gpt-4')

        # Override all at once instead of nested context managers
        with override_variables({system_prompt: 'Custom prompt', temperature: 0.9, model: 'claude-3.5-sonnet'}):
            result = await agent.run(query)
        ```
    """
    # Convert Variable instances to their names
    name_to_value = {var.name: value for var, value in overrides.items()}

    current = _VARIABLE_OVERRIDES.get() or {}
    token = _VARIABLE_OVERRIDES.set({**current, **name_to_value})
    try:
        yield
    finally:
        _VARIABLE_OVERRIDES.reset(token)


class PromptVariable(Variable[str]):
    """A specialized Variable for prompt templates with optional validation.

    PromptVariable is a convenience class for string variables that represent
    prompts or templates. It provides:
    - Type automatically set to `str`
    - Optional template variable validation

    Example:
        ```python skip="true"
        system_prompt = logfire.prompt_var(
            name='system_prompt',
            default='Hello, {user_name}! Welcome to {context}.',
            template_vars=['user_name', 'context'],  # Optional validation
        )
        ```
    """

    template_vars: Sequence[str] | None
    """Optional list of expected template variables for validation."""

    def __init__(
        self,
        name: str,
        *,
        default: str | ResolveFunction[str],
        description: str | None = None,
        template_vars: Sequence[str] | None = None,
        logfire_instance: logfire.Logfire,
    ):
        """Create a new prompt variable.

        Args:
            name: Unique name identifying this variable.
            default: Default prompt value to use when no configuration is found,
                or a function that computes the default.
            description: Optional human-readable description of this prompt.
            template_vars: Optional list of expected template variable names (e.g., ["user_name"]).
                If provided, a warning will be logged if the resolved prompt doesn't contain
                all expected template variables.
            logfire_instance: The Logfire instance this variable is associated with.
        """
        super().__init__(
            name,
            type=str,
            default=default,
            description=description,
            logfire_instance=logfire_instance,
        )
        self.template_vars = template_vars


class VariableBundle:
    """A collection of related variables that can be overridden together.

    VariableBundle allows you to group related variables and override them
    as a unit, making it easier to manage configuration for components that
    use multiple variables.

    Example:
        ```python skip="true"
        system_prompt = logfire.var(name='system_prompt', type=str, default='Default')
        model = logfire.var(name='model', type=str, default='gpt-4')
        temperature = logfire.var(name='temperature', type=float, default=0.7)

        agent_config = logfire.var_bundle(
            name='support_agent', variables={'system_prompt': system_prompt, 'model': model, 'temperature': temperature}
        )

        # Override multiple variables at once
        with agent_config.override({'system_prompt': 'New prompt', 'model': 'gpt-4o'}):
            result = await agent.run(query)

        # Access individual variables
        prompt = agent_config['system_prompt'].get().value
        ```
    """

    name: str
    """Name identifying this bundle."""
    variables: dict[str, Variable[Any]]
    """Mapping of keys to Variable instances in this bundle."""

    def __init__(self, name: str, variables: Mapping[str, Variable[Any]]):
        """Create a new variable bundle.

        Args:
            name: Name identifying this bundle.
            variables: Mapping of keys to Variable instances. Keys are used for
                accessing variables and for override mappings.
        """
        self.name = name
        self.variables = dict(variables)

    def __getitem__(self, key: str) -> Variable[Any]:
        """Get a variable from this bundle by key.

        Args:
            key: The key used when defining the bundle.

        Returns:
            The Variable instance.

        Raises:
            KeyError: If the key doesn't exist in the bundle.
        """
        return self.variables[key]

    def __contains__(self, key: str) -> bool:
        """Check if a key exists in this bundle."""
        return key in self.variables

    def __iter__(self) -> Iterator[str]:
        """Iterate over the keys in this bundle."""
        return iter(self.variables)

    def keys(self) -> Iterator[str]:
        """Return an iterator over the keys in this bundle."""
        return iter(self.variables)

    def values(self) -> Iterator[Variable[Any]]:
        """Return an iterator over the variables in this bundle."""
        return iter(self.variables.values())

    def items(self) -> Iterator[tuple[str, Variable[Any]]]:
        """Return an iterator over (key, variable) pairs in this bundle."""
        return iter(self.variables.items())

    @contextmanager
    def override(self, overrides: Mapping[str, Any]) -> Iterator[None]:
        """Context manager to override multiple variables in this bundle.

        Args:
            overrides: A mapping of bundle keys to override values.
                Only keys present in the bundle will be used.

        Example:
            ```python skip="true"
            with agent_config.override({'system_prompt': 'New prompt', 'model': 'gpt-4o'}):
                result = await agent.run(query)
            ```
        """
        # Convert bundle keys to Variable instances
        variable_overrides: dict[Variable[Any], Any] = {}
        for key, value in overrides.items():
            if key in self.variables:
                variable_overrides[self.variables[key]] = value

        with override_variables(variable_overrides):
            yield

    def get_all(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> dict[str, ResolvedVariable[Any]]:
        """Resolve all variables in this bundle.

        Args:
            targeting_key: Optional key for deterministic variant selection.
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A mapping of bundle keys to their resolved variables.
        """
        return {key: var.get(targeting_key=targeting_key, attributes=attributes) for key, var in self.variables.items()}
