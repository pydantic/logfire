from __future__ import annotations as _annotations

import inspect
import json
import warnings
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, cast

from opentelemetry.trace import get_current_span
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypeIs

from logfire.variables._handlebars import HandlebarsError
from logfire.variables.composition import (
    ComposedReference,
    VariableCompositionError,
    expand_references,
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
from logfire.variables.abstract import ResolutionReason, ResolvedVariable

__all__ = (
    'ResolveFunction',
    'is_resolve_function',
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

        self._variable_registry = logfire_instance._variables  # pyright: ignore[reportPrivateUsage]
        self.logfire_instance = logfire_instance.with_settings(custom_scope_suffix='variables')
        self.type_adapter = TypeAdapter[T_co](type)

    def _deserialize(self, serialized_value: str) -> T_co | ValidationError | ValueError | TypeError:
        """Deserialize a JSON string to the variable's type, returning an Exception on failure."""
        try:
            return self.type_adapter.validate_json(serialized_value)
        except (ValidationError, ValueError, TypeError) as e:
            return e

    @contextmanager
    def override(self, value: T_co | ResolveFunction[T_co]) -> Generator[None]:
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
            # Top-level context-override fast path: handled here, before
            # `_lookup_serialized` even sees the name. Overrides do not
            # participate in `@{ref}@` composition (their value is the user's
            # literal choice), and the round-trip through dump_json /
            # validate_json that `_lookup_serialized` would otherwise perform
            # silently drops any value that isn't JSON-serializable. Restore
            # the pre-#1951 behaviour: if the override serializes, take the
            # render path; if it doesn't, return the typed Python value
            # verbatim.
            context_overrides = _VARIABLE_OVERRIDES.get()
            if context_overrides is not None and self.name in context_overrides:
                return self._resolve_context_override(
                    context_overrides[self.name], targeting_key, attributes, render_fn
                )

            provider = self.logfire_instance.config.get_variable_provider()

            serialized_result = self._lookup_serialized(
                self.name,
                provider=provider,
                targeting_key=targeting_key,
                attributes=attributes,
                label=label,
            )

            if serialized_result.value is None:
                return self._resolve_code_default(
                    targeting_key,
                    attributes,
                    serialized_result=serialized_result,
                )

            result = self._expand_and_deserialize(
                serialized_result, provider, targeting_key, attributes, span, render_fn=render_fn
            )
            # Preserve the lookup-tier signal: if the value came from the code
            # default (via `_lookup_serialized`) rather than the provider, we
            # promote the success reason from 'resolved' to 'code_default' and
            # carry the provider's exception through so callers can surface it.
            if serialized_result.reason == 'code_default' and result.reason == 'resolved':
                result.reason = 'code_default'
            if result.exception is None and serialized_result.exception is not None:
                result.exception = serialized_result.exception
            return result

        except Exception as e:
            if span and serialized_result is not None:  # pragma: no cover
                span.set_attribute('invalid_serialized_label', serialized_result.label)
                span.set_attribute('invalid_serialized_value', serialized_result.value)
            try:
                default = self._get_default(targeting_key, attributes)
            except Exception:
                default = cast('T_co', None)
            return ResolvedVariable(name=self.name, value=default, exception=e, reason='other_error')

    def _resolve_context_override(
        self,
        override_value: T_co | ResolveFunction[T_co],
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        render_fn: Callable[[str], str] | None,
    ) -> ResolvedVariable[T_co]:
        """Return a resolution for the top-level context override.

        Overrides do not participate in composition. When the override value
        serializes cleanly, run any provided `render_fn` (template rendering)
        against the JSON form and revalidate so the user gets the same shape
        a provider value would yield. When it doesn't serialize — common for
        custom Python types, arbitrary objects, etc. — return the user's
        value verbatim under `reason='context_override'`. Returning verbatim
        is the legacy behaviour Devin / Alex flagged on #1951; the previous
        implementation silently dropped these values back to the provider /
        code default.
        """
        if is_resolve_function(override_value):
            resolved_value = cast('T_co', override_value(targeting_key, attributes))
        else:
            resolved_value = cast('T_co', override_value)
        try:
            serialized = self.type_adapter.dump_json(resolved_value).decode('utf-8')
        except (ValueError, TypeError, RuntimeError):
            return ResolvedVariable(name=self.name, value=resolved_value, reason='context_override')
        if render_fn is not None:
            serialized = render_fn(serialized)
        validated = self.type_adapter.validate_json(serialized)
        return ResolvedVariable(name=self.name, value=validated, reason='context_override')

    def _lookup_serialized(
        self,
        name: str,
        *,
        provider: VariableProvider,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        label: str | None = None,
    ) -> ResolvedVariable[str | None]:
        """Resolve a variable name to its serialized value using the standard priority chain.

        Priority: context override -> provider (label-specific then default) -> registered code default.

        Used by both `_resolve` (for `self.name`) and the composition expander
        (for child `@{ref}@` lookups) so the two paths can't drift.
        """
        variable = self._variable_registry.get(name)
        context_overrides = _VARIABLE_OVERRIDES.get()

        # 1. Context override (only for variables whose type we know)
        if context_overrides is not None and name in context_overrides and variable is not None:
            override_value = context_overrides[name]
            if is_resolve_function(override_value):
                override_value = override_value(targeting_key, attributes)
            try:
                serialized = variable.type_adapter.dump_json(override_value).decode('utf-8')
            except (ValueError, TypeError, RuntimeError):
                pass  # Fall through to provider/code default
            else:
                return ResolvedVariable(name=name, value=serialized, reason='context_override')

        # 2. Provider (label-specific first, falling back to default targeting)
        if label is not None:
            provider_result = provider.get_serialized_value_for_label(name, label)
            if provider_result.value is None:
                provider_result = provider.get_serialized_value(name, targeting_key, attributes)
        else:
            provider_result = provider.get_serialized_value(name, targeting_key, attributes)

        if provider_result.value is not None:
            return provider_result

        # 3. Registered code default
        if variable is not None:
            serialized_default = variable._get_serialized_default(targeting_key, attributes)
            if serialized_default is not None:
                return ResolvedVariable(
                    name=name,
                    value=serialized_default,
                    label=provider_result.label,
                    version=provider_result.version,
                    reason='code_default',
                    exception=provider_result.exception,
                )

        # No value at any tier; propagate the provider's metadata so callers
        # can surface the original exception/reason.
        return provider_result

    def _expand_and_deserialize(
        self,
        serialized_result: ResolvedVariable[str | None],
        provider: VariableProvider,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        render_fn: Callable[[str], str] | None = None,
    ) -> ResolvedVariable[T_co]:
        """Expand @{references}@ in a serialized value, optionally render templates, then deserialize.

        Handles composition between the provider fetch and Pydantic deserialization.
        When render_fn is provided, it is applied after composition and before deserialization.
        """
        assert serialized_result.value is not None

        serialized_value = serialized_result.value
        composed: list[ComposedReference] = []

        # Always run through `expand_references`, even when no `@{ref}@` tags
        # are present: it's also responsible for unescaping `\@{...}@` →
        # `@{...}@`. Gating on `has_references` produced inconsistent
        # observable behaviour where an escaped-only value (e.g.
        # `r'\@{baz}@'`) kept its backslash, but the same escape combined
        # with a real reference correctly produced the literal `@{baz}@`.
        def resolve_ref(
            ref_name: str,
        ) -> tuple[str | None, str | None, int | None, ResolutionReason]:
            # Shares the lookup priority with `_resolve` so that composition
            # respects overrides and registered code defaults rather than
            # only consulting the provider.
            ref_result = self._lookup_serialized(
                ref_name,
                provider=provider,
                targeting_key=targeting_key,
                attributes=attributes,
            )
            return (ref_result.value, ref_result.label, ref_result.version, ref_result.reason)

        try:
            serialized_value, composed = expand_references(
                serialized_value,
                self.name,
                resolve_ref,
            )
            if composition_error := _first_composition_error(composed):
                return self._fallback_to_default(
                    exception=VariableCompositionError(composition_error),
                    failure_stage='composition',
                    targeting_key=targeting_key,
                    attributes=attributes,
                    serialized_result=serialized_result,
                    composed=composed,
                )
        except VariableCompositionError as e:
            return self._fallback_to_default(
                exception=e,
                failure_stage='composition',
                targeting_key=targeting_key,
                attributes=attributes,
                serialized_result=serialized_result,
                composed=composed,
            )

        # Apply render_fn (template rendering) if provided
        if render_fn is not None:
            try:
                serialized_value = render_fn(serialized_value)
            except (HandlebarsError, ValueError, TypeError) as e:
                return self._fallback_to_default(
                    exception=e,
                    failure_stage='template rendering',
                    targeting_key=targeting_key,
                    attributes=attributes,
                    serialized_result=serialized_result,
                    composed=composed,
                )

        # Deserialize the (possibly expanded/rendered) value
        value_or_exc = self._deserialize(serialized_value)
        if isinstance(value_or_exc, Exception):
            if span:  # pragma: no branch
                span.set_attribute('invalid_serialized_label', serialized_result.label)
                span.set_attribute('invalid_serialized_value', serialized_value)
            reason: str = 'validation_error' if isinstance(value_or_exc, ValidationError) else 'other_error'
            return ResolvedVariable(
                name=self.name,
                value=self._get_default(targeting_key, attributes),
                exception=value_or_exc,
                reason=reason,
                label=serialized_result.label,
                version=serialized_result.version,
                composed_from=composed,
            )

        return ResolvedVariable(
            name=self.name,
            value=value_or_exc,
            label=serialized_result.label,
            version=serialized_result.version,
            reason='resolved',
            composed_from=composed,
        )

    def _fallback_to_default(
        self,
        *,
        exception: Exception,
        failure_stage: str,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        serialized_result: ResolvedVariable[str | None],
        composed: list[ComposedReference],
    ) -> ResolvedVariable[T_co]:
        """Fall back to the code default and warn after a composition or render failure.

        *failure_stage* identifies which step in the pipeline failed so the
        warning text is accurate: composition (`@{ref}@` expansion) and
        template rendering (`{{...}}` against `inputs`) reach this fallback
        through different branches and shouldn't all surface as
        "composition failed".
        """
        warnings.warn(
            f"Variable '{self.name}' {failure_stage} failed; falling back to code default: {exception}",
            category=RuntimeWarning,
            stacklevel=2,
        )
        return ResolvedVariable(
            name=self.name,
            value=self._get_default(targeting_key, attributes),
            exception=exception,
            reason='other_error',
            label=serialized_result.label,
            version=serialized_result.version,
            composed_from=composed,
        )

    def _get_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> T_co:
        if is_resolve_function(self.default):
            return self.default(targeting_key, merged_attributes)
        else:
            return self.default

    def _get_serialized_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> str | None:
        """Return the code default serialized as JSON, or None if serialization fails."""
        try:
            default = self._get_default(targeting_key, merged_attributes)
            return self.type_adapter.dump_json(default).decode('utf-8')
        except (ValueError, TypeError, RuntimeError):
            return None

    def _resolve_code_default(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        serialized_result: ResolvedVariable[str | None],
    ) -> ResolvedVariable[T_co]:
        """Build a ResolvedVariable from the registered code default.

        Reached when `_lookup_serialized` could not produce a serialized value at
        any tier (typically because the code default could not be JSON-serialized
        for the composition/render pipeline). Returns the deserialized default
        directly; composition and rendering are skipped because there is no
        serialized form to operate on.
        """
        return ResolvedVariable(
            name=self.name,
            value=self._get_default(targeting_key, attributes),
            exception=serialized_result.exception,
            label=serialized_result.label,
            version=serialized_result.version,
            reason='code_default',
        )

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

        return VariableConfig(
            name=self.name,
            description=self.description,
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
            json_schema=json_schema,
            example=example,
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
            if span is not None:
                # Serialize value safely for OTel span attributes, which only support primitives.
                # Try to JSON serialize the value; if that fails, fall back to string representation.
                try:
                    serialized_value = self.type_adapter.dump_json(result.value).decode('utf-8')
                except (ValueError, TypeError, RuntimeError):
                    serialized_value = repr(result.value)
                attrs: dict[str, Any] = {
                    'name': result.name,
                    'value': serialized_value,
                    'label': result.label,
                    'version': result.version,
                    'reason': result.reason,
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
                    span.record_exception(result.exception)
            return result

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


class TemplateVariable(Variable[T_co], Generic[T_co, InputsT]):
    """A managed variable with integrated template rendering.

    Like `Variable`, but `get()` requires `inputs` and automatically renders
    Handlebars `{{placeholder}}` templates in the resolved value before returning.
    The pipeline is: resolve → compose `@{refs}@` → render `{{}}` → deserialize.
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
            inputs_type: The type (typically a Pydantic `BaseModel`) describing the expected
                template inputs. Used for type-safe `get(inputs)` calls and JSON schema generation.
            description: Optional human-readable description of what this variable controls.
            logfire_instance: The Logfire instance this variable is associated with.
        """
        super().__init__(
            name,
            type=type,
            default=default,
            description=description,
            logfire_instance=logfire_instance,
        )
        self.inputs_type = inputs_type
        self._inputs_type_adapter: TypeAdapter[InputsT] = TypeAdapter(inputs_type)

    def get_template_inputs_schema(self) -> dict[str, Any]:
        """Return the JSON schema derived from `inputs_type`."""
        return self._inputs_type_adapter.json_schema()

    def to_config(self) -> VariableConfig:
        """Create a VariableConfig, including `template_inputs_schema`."""
        config = super().to_config()
        config.template_inputs_schema = self.get_template_inputs_schema()
        return config

    def get(  # pyright: ignore[reportIncompatibleMethodOverride]
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
        2. Expand `@{variable_name}@` composition references
        3. Render `{{placeholder}}` Handlebars templates using `inputs`
        4. Deserialize to the variable's type

        Args:
            inputs: Template context values. Typically a Pydantic `BaseModel` instance
                matching `inputs_type`. All `{{placeholder}}` expressions in the value
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


def get_template_inputs_schema(variable: Variable[Any]) -> dict[str, Any] | None:
    """Return the template inputs JSON schema, or None for non-template variables."""
    if isinstance(variable, TemplateVariable):
        return variable.get_template_inputs_schema()
    return None


def _first_composition_error(composed: list[ComposedReference]) -> str | None:
    """Return the first nested composition error, if any."""
    for ref in composed:
        if ref.error is not None:
            return ref.error
        if nested_error := _first_composition_error(ref.composed_from):
            return nested_error
    return None


@contextmanager
def targeting_context(
    targeting_key: str,
    variables: Sequence[Variable[Any] | TemplateVariable[Any, Any]] | None = None,
) -> Generator[None]:
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
