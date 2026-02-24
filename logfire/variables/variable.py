from __future__ import annotations as _annotations

import inspect
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar

from opentelemetry.trace import get_current_span
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

from logfire.variables.composition import (
    ComposedReference,
    VariableCompositionError,
    expand_references,
    has_references,
)

if TYPE_CHECKING:
    from logfire.variables.abstract import VariableProvider
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
    '_BaseVariable',
    'Variable',
    'TemplateVariable',
    'targeting_context',
)

T_co = TypeVar('T_co', covariant=True)
InputsT = TypeVar('InputsT')


_VARIABLE_OVERRIDES: ContextVar[dict[str, Any] | None] = ContextVar('_VARIABLE_OVERRIDES', default=None)


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
        raise NotImplementedError  # pragma: no cover


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


class _BaseVariable(Generic[T_co]):
    """Base class for managed variables with shared resolution infrastructure.

    Contains all shared logic: init, deserialization, override, refresh, config,
    resolution pipeline. Subclasses (Variable, TemplateVariable) add their own get() method.
    """

    name: str
    """Unique name identifying this variable."""
    value_type: type[T_co]
    """The expected type of this variable's values."""
    default: T_co | ResolveFunction[T_co]
    """Default value or function to compute the default."""
    description: str | None
    """Description of the variable."""
    template_inputs_type: type[Any] | None
    """The Pydantic model type for template inputs, if template rendering is enabled."""

    logfire_instance: logfire.Logfire
    """The Logfire instance this variable is associated with."""

    def __init__(
        self,
        name: str,
        *,
        type: type[T_co],
        default: T_co | ResolveFunction[T_co],
        description: str | None = None,
        template_inputs: type[Any] | None = None,
        logfire_instance: logfire.Logfire,
    ):
        """Create a new managed variable.

        Args:
            name: Unique name identifying this variable.
            type: The expected type of this variable's values, used for validation.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            description: Optional human-readable description of what this variable controls.
            template_inputs: Optional Pydantic model type describing the expected template inputs
                for Handlebars rendering. When set, values can contain ``{{placeholder}}`` syntax.
            logfire_instance: The Logfire instance this variable is associated with. Used to determine config, etc.
        """
        self.name = name
        self.value_type = type
        self.default = default
        self.description = description
        self.template_inputs_type = template_inputs

        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='variables')
        self.type_adapter = TypeAdapter[T_co](type)

        if template_inputs is not None:
            self._template_inputs_adapter: TypeAdapter[Any] | None = TypeAdapter(template_inputs)
        else:
            self._template_inputs_adapter = None

    def get_template_inputs_schema(self) -> dict[str, Any] | None:
        """Return the JSON schema for template inputs, or None if not configured."""
        if self._template_inputs_adapter is not None:
            return self._template_inputs_adapter.json_schema()
        return None

    def _deserialize(self, serialized_value: str) -> T_co | Exception:
        """Deserialize a JSON string to the variable's type, returning an Exception on failure."""
        try:
            return self.type_adapter.validate_json(serialized_value)
        except Exception as e:
            return e

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

    async def refresh(self, force: bool = False):
        """Asynchronously refresh the variable."""
        await to_thread(self.refresh_sync, force)

    def refresh_sync(self, force: bool = False):
        """Synchronously refresh the variable."""
        self.logfire_instance.config.get_variable_provider().refresh(force=force)

    def _resolve(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        label: str | None = None,
        render_fn: Callable[[str], str] | None = None,
    ) -> ResolvedVariable[T_co]:
        serialized_result: ResolvedVariable[str | None] | None = None
        try:
            if (context_overrides := _VARIABLE_OVERRIDES.get()) is not None and self.name in context_overrides:
                context_value = context_overrides[self.name]
                if is_resolve_function(context_value):
                    context_value = context_value(targeting_key, attributes)
                # For TemplateVariable (render_fn set), the override is a template
                # that still gets rendered with inputs.
                if render_fn is not None:
                    context_value = self._render_default(context_value, render_fn)
                return ResolvedVariable(name=self.name, value=context_value, _reason='context_override')

            provider = self.logfire_instance.config.get_variable_provider()

            # If explicit label is requested, try to get that specific label
            if label is not None:
                serialized_result = provider.get_serialized_value_for_label(self.name, label)
                if serialized_result.value is not None:
                    return self._expand_and_deserialize(
                        serialized_result, provider, targeting_key, attributes, span, render_fn=render_fn
                    )
                # Label not found - fall through to default resolution

            serialized_result = provider.get_serialized_value(self.name, targeting_key, attributes)

            if serialized_result.value is None:
                default = self._get_default(targeting_key, attributes)
                if render_fn is not None:
                    default = self._render_default(default, render_fn)
                return _with_value(serialized_result, default)

            return self._expand_and_deserialize(
                serialized_result, provider, targeting_key, attributes, span, render_fn=render_fn
            )

        except Exception as e:
            if span and serialized_result is not None:  # pragma: no cover
                span.set_attribute('invalid_serialized_label', serialized_result.label)
                span.set_attribute('invalid_serialized_value', serialized_result.value)
            default = self._get_default(targeting_key, attributes)
            return ResolvedVariable(name=self.name, value=default, exception=e, _reason='other_error')

    def _render_default(self, default: Any, render_fn: Callable[[str], str]) -> T_co:
        """Serialize the default value, apply render_fn, then deserialize back."""
        try:
            serialized = self.type_adapter.dump_json(default).decode('utf-8')
            rendered = render_fn(serialized)
            result = self._deserialize(rendered)
            if isinstance(result, Exception):
                raise result
            return result
        except Exception:
            # If rendering the default fails, return the original default
            return default

    def _expand_and_deserialize(
        self,
        serialized_result: ResolvedVariable[str | None],
        provider: VariableProvider,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        render_fn: Callable[[str], str] | None = None,
    ) -> ResolvedVariable[T_co]:
        """Expand <<references>> in a serialized value, optionally render templates, then deserialize.

        Handles composition between the provider fetch and Pydantic deserialization.
        When render_fn is provided, it is applied after composition and before deserialization.
        """
        assert serialized_result.value is not None

        serialized_value = serialized_result.value
        composed: list[ComposedReference] = []

        # Expand <<references>> if any are present
        if has_references(serialized_value):

            def resolve_ref(ref_name: str) -> tuple[str | None, str | None, int | None, str]:
                ref_resolved = provider.get_serialized_value(ref_name, targeting_key, attributes)
                return (
                    ref_resolved.value,
                    ref_resolved.label,
                    ref_resolved.version,
                    ref_resolved._reason,  # pyright: ignore[reportPrivateUsage]
                )

            try:
                serialized_value, composed = expand_references(
                    serialized_value,
                    self.name,
                    resolve_ref,
                )
            except VariableCompositionError as e:
                default = self._get_default(targeting_key, attributes)
                return ResolvedVariable(
                    name=self.name,
                    value=default,
                    exception=e,
                    _reason='other_error',
                    label=serialized_result.label,
                    version=serialized_result.version,
                    composed_from=composed,
                )

        # Apply render_fn (template rendering) if provided
        if render_fn is not None:
            try:
                serialized_value = render_fn(serialized_value)
            except Exception as e:
                default = self._get_default(targeting_key, attributes)
                return ResolvedVariable(
                    name=self.name,
                    value=default,
                    exception=e,
                    _reason='other_error',
                    label=serialized_result.label,
                    version=serialized_result.version,
                    composed_from=composed,
                )

        # Deserialize the (possibly expanded/rendered) value
        value_or_exc = self._deserialize(serialized_value)
        if isinstance(value_or_exc, Exception):
            if span:  # pragma: no branch
                span.set_attribute('invalid_serialized_label', serialized_result.label)
                span.set_attribute('invalid_serialized_value', serialized_value)
            default = self._get_default(targeting_key, attributes)
            reason: str = 'validation_error' if isinstance(value_or_exc, ValidationError) else 'other_error'
            return ResolvedVariable(
                name=self.name,
                value=default,
                exception=value_or_exc,
                _reason=reason,
                composed_from=composed,
            )

        return ResolvedVariable(
            name=self.name,
            value=value_or_exc,
            label=serialized_result.label,
            version=serialized_result.version,
            _reason='resolved',
            composed_from=composed,
            _serialized_value=serialized_value,
            _deserializer=self._deserialize,
        )

    def _get_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> T_co:
        if is_resolve_function(self.default):
            return self.default(targeting_key, merged_attributes)
        else:
            return self.default

    def _get_merged_attributes(self, attributes: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        from logfire._internal.config import LocalVariablesOptions, VariablesOptions

        result: dict[str, Any] = {}
        variables = self.logfire_instance.config.variables
        # Apply in order of lowest to highest priority:
        # resource attributes < baggage < user-provided attributes
        include_resource = True
        include_baggage = True
        if isinstance(variables, (VariablesOptions, LocalVariablesOptions)):
            include_resource = variables.include_resource_attributes_in_context
            include_baggage = variables.include_baggage_in_context
        if include_resource:
            result.update(self.logfire_instance.resource_attributes)
        if include_baggage:
            result.update(logfire.get_baggage())
        if attributes:
            result.update(attributes)
        return result

    def to_config(self) -> VariableConfig:
        """Create a VariableConfig from this Variable instance.

        This creates a minimal config with just the name, schema, and example.
        No labels or versions are created - use this to generate a template config that can be edited.

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

        template_inputs_schema: dict[str, Any] | None = None
        if self._template_inputs_adapter is not None:
            template_inputs_schema = self._template_inputs_adapter.json_schema()

        return VariableConfig(
            name=self.name,
            description=self.description,
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
            json_schema=json_schema,
            example=example,
            template_inputs_schema=template_inputs_schema,
        )

    def _get_result_and_record_span(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        label: str | None,
        render_fn: Callable[[str], str] | None = None,
    ) -> ResolvedVariable[T_co]:
        """Common get() logic: resolve targeting key, open span, call _resolve, record attributes."""
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
            if _get_variables_instrument(self.logfire_instance.config.variables):
                span = stack.enter_context(
                    self.logfire_instance.span(
                        span_name,
                        name=self.name,
                        targeting_key=targeting_key,
                        attributes=merged_attributes,
                    )
                )
            result = self._resolve(targeting_key, merged_attributes, span, label, render_fn=render_fn)
            # Ensure rendering support is always available
            if result._deserializer is None:  # pyright: ignore[reportPrivateUsage]
                result._deserializer = self._deserialize  # pyright: ignore[reportPrivateUsage]
            if result._serialized_value is None and result.value is not None:  # pyright: ignore[reportPrivateUsage]
                try:
                    result._serialized_value = self.type_adapter.dump_json(result.value).decode('utf-8')  # pyright: ignore[reportPrivateUsage]
                except Exception:
                    pass
            if span is not None:
                # Serialize value safely for OTel span attributes, which only support primitives.
                # Try to JSON serialize the value; if that fails, fall back to string representation.
                try:
                    serialized_value = self.type_adapter.dump_json(result.value).decode('utf-8')
                except Exception:
                    serialized_value = repr(result.value)
                attrs: dict[str, Any] = {
                    'name': result.name,
                    'value': serialized_value,
                    'label': result.label,
                    'version': result.version,
                    'reason': result._reason,  # pyright: ignore[reportPrivateUsage]
                }
                if result.composed_from:
                    attrs['composed_from'] = json.dumps(
                        [
                            {
                                'name': c.name,
                                'version': c.version,
                                'label': c.label,
                                'reason': c.reason,
                                'error': c.error,
                            }
                            for c in result.composed_from
                        ]
                    )
                span.set_attributes(attrs)
                if result.exception:
                    span.record_exception(
                        result.exception,
                    )
            return result


class Variable(_BaseVariable[T_co]):
    """A managed variable that can be resolved dynamically based on configuration."""

    def get(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        label: str | None = None,
    ) -> ResolvedVariable[T_co]:
        """Resolve the variable and return full details including label, version, and any errors.

        Args:
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
                If not provided, falls back to contextvar targeting key (set via targeting_context),
                then to the current trace ID if there is an active trace.
            attributes: Optional attributes for condition-based targeting rules.
            label: Optional explicit label name to select. If provided, bypasses rollout
                weights and targeting, directly selecting the specified label. If the label
                doesn't exist in the configuration, falls back to default resolution.

        Returns:
            A ResolvedVariable object containing the resolved value, selected label,
            version, and any errors that occurred.
        """
        return self._get_result_and_record_span(targeting_key, attributes, label)


class TemplateVariable(_BaseVariable[T_co], Generic[T_co, InputsT]):
    """A managed variable with integrated template rendering.

    Like ``Variable``, but ``get()`` requires ``inputs`` and automatically renders
    Handlebars ``{{placeholder}}`` templates in the resolved value before returning.
    The pipeline is: resolve → compose ``<<refs>>`` → render ``{{}}`` → deserialize.
    """

    inputs_type: type[InputsT]
    """The type used for template inputs."""

    def __init__(
        self,
        name: str,
        *,
        type: type[T_co],
        default: T_co | ResolveFunction[T_co],
        inputs_type: type[InputsT],
        description: str | None = None,
        logfire_instance: logfire.Logfire,
    ):
        """Create a new template variable.

        Args:
            name: Unique name identifying this variable.
            type: The expected type of this variable's values, used for validation.
            default: Default value to use when no configuration is found, or a function
                that computes the default based on targeting_key and attributes.
            inputs_type: The type (typically a Pydantic ``BaseModel``) describing the expected
                template inputs. Used for type-safe ``get(inputs)`` calls and JSON schema generation.
            description: Optional human-readable description of what this variable controls.
            logfire_instance: The Logfire instance this variable is associated with.
        """
        super().__init__(
            name,
            type=type,
            default=default,
            description=description,
            template_inputs=inputs_type,
            logfire_instance=logfire_instance,
        )
        self.inputs_type = inputs_type

    def get(
        self,
        inputs: InputsT,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        label: str | None = None,
    ) -> ResolvedVariable[T_co]:
        """Resolve the variable, render templates with the given inputs, and return the result.

        The resolution pipeline is:
        1. Fetch serialized value from provider (or use default)
        2. Expand ``<<variable_name>>`` composition references
        3. Render ``{{placeholder}}`` Handlebars templates using ``inputs``
        4. Deserialize to the variable's type

        Args:
            inputs: Template context values. Typically a Pydantic ``BaseModel`` instance
                matching ``inputs_type``. All ``{{placeholder}}`` expressions in the value
                are rendered using this context.
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.
            label: Optional explicit label name to select.

        Returns:
            A ResolvedVariable with the fully rendered and deserialized value.
        """
        from logfire.variables.abstract import render_serialized_string

        def _render_fn(serialized_json: str) -> str:
            return render_serialized_string(serialized_json, inputs)

        return self._get_result_and_record_span(targeting_key, attributes, label, render_fn=_render_fn)


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
    variables: Sequence[Variable[Any] | TemplateVariable[Any, Any]] | None = None,
) -> Iterator[None]:
    """Set the targeting key for variable resolution within this context.

    The targeting key is used for deterministic label selection - the same targeting key
    will always resolve to the same label for a given variable configuration.

    Args:
        targeting_key: The targeting key to use for deterministic label selection
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


def _get_variables_instrument(variables: Any) -> bool:
    """Get the `instrument` setting from variables config, defaulting to True."""
    from logfire._internal.config import LocalVariablesOptions, VariablesOptions

    if isinstance(variables, (VariablesOptions, LocalVariablesOptions)):
        return variables.instrument
    return True
