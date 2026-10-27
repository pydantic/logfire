from __future__ import annotations as _annotations

import inspect
import json
import math
import os
import secrets
import threading
import warnings
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, Generic, Literal, Protocol, TypeVar, cast

from opentelemetry.trace import get_current_span
from pydantic import TypeAdapter, ValidationError
from pydantic_core import ErrorDetails
from typing_extensions import TypeIs, assert_never

from logfire.variables.composition import (
    ComposedReference,
    VariableCompositionError,
    expand_references,
    find_references,
)

if TYPE_CHECKING:
    from logfire._internal.config import TemplateMismatchPolicy
    from logfire.experimental.feature_flags import FlagEvaluationDetails
    from logfire.variables.abstract import RuleEvaluationReason, VariableProvider
    from logfire.variables.config import VariableConfig

if find_spec('anyio') is not None:  # pragma: no branch
    # Use anyio for running sync functions on separate threads in an event loop if it is available
    from anyio.to_thread import run_sync as to_thread
else:
    from asyncio import to_thread  # pragma: no cover

import logfire
from logfire._internal.integrations.executors import THREAD_CONTEXTVARS
from logfire._internal.trace_scope import current_trace_scope
from logfire.variables.abstract import ResolutionReason, ResolvedVariable, VariableProviderEvaluationState

__all__ = (
    'ResolveFunction',
    'is_resolve_function',
    'Variable',
    'TemplateVariable',
    'TemplateInputsMismatchError',
    'feature_context',
    'targeting_context',
)


class TemplateInputsMismatchError(Exception):
    """Render-time `{{field}}` mismatch raised under the strict policy.

    Raised by `TemplateVariable.get(inputs)` when the resolved template
    references a `{{field}}` not declared in the variable's `inputs_type`
    and the active `template_mismatch_policy` is `'error'`.

    Distinct from `HandlebarsError` so it bypasses the SDK's composition-
    failure fallback and propagates to the caller — the `'error'` policy
    is meant to fail loudly, not silently degrade to the code default.
    """


T_co = TypeVar('T_co', covariant=True)
InputsT = TypeVar('InputsT')
FlagT = TypeVar('FlagT')


_VARIABLE_OVERRIDES: ContextVar[dict[object, Any] | None] = ContextVar('_VARIABLE_OVERRIDES', default=None)

# Per-`get()`-call cache for the code-default value. Keyed by `id(variable)`.
# Lets `_get_default_cached` short-circuit when the same callable default
# would otherwise be invoked twice in one resolution. Each entry is
# `(ok: bool, value_or_exception: Any)`: successful invocations cache the
# returned value; raising invocations cache the exception so re-entry
# re-raises without re-invoking the callable. Set up by `Variable._resolve`
# at the top of the call and reset when it returns.
_DEFAULT_CACHE: ContextVar[dict[int, tuple[bool, Any]] | None] = ContextVar('_DEFAULT_CACHE', default=None)

_MAX_DECLARATION_ATTRIBUTE_BYTES = 64 * 1024
"""Maximum serialized size for a schema or code default attached to a declaration span."""

_MAX_DECLARATION_PREVIEW_BYTES = 1024
"""Maximum serialized preview size when a declaration attribute is too large to attach in full."""


def _declaration_schema_without_defaults(schema: dict[str, Any] | list[Any] | str | int | float | bool | None) -> Any:
    """Copy schema nodes without default annotations, which can contain unredacted values.

    Visit schema keywords only: property/definition names and literal values such as
    ``const={"default": "value"}`` are not schema annotations and must remain intact.
    """
    if isinstance(schema, list):
        return [_declaration_schema_without_defaults(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result: dict[str, Any] = {}
    for key, value in schema.items():
        if key == 'default':
            continue
        if key in ('$defs', 'definitions', 'properties', 'patternProperties', 'dependentSchemas', 'dependencies'):
            result[key] = {name: _declaration_schema_without_defaults(child) for name, child in value.items()}
        elif key in (
            'allOf',
            'anyOf',
            'oneOf',
            'prefixItems',
            'items',
            'additionalItems',
            'contains',
            'additionalProperties',
            'unevaluatedProperties',
            'unevaluatedItems',
            'propertyNames',
            'not',
            'if',
            'then',
            'else',
            'contentSchema',
        ):
            result[key] = _declaration_schema_without_defaults(value)
        else:
            result[key] = value
    return result


@dataclass
class _TargetingContextData:
    """Internal data structure for targeting context."""

    default: str | None = None
    """Default targeting key for all variables."""
    by_variable: dict[str, str] = field(default_factory=dict[str, str])
    """Variable-specific targeting keys (variable name -> targeting key)."""
    attributes: dict[str, Any] = field(default_factory=dict[str, Any])
    """Request-local attributes shared by managed-variable evaluations."""


_TARGETING_CONTEXT: ContextVar[_TargetingContextData | None] = ContextVar('_TARGETING_CONTEXT', default=None)
_FEATURE_TARGETING_KEY: ContextVar[str | None] = ContextVar('_FEATURE_TARGETING_KEY', default=None)
# Where the targeting key of the feature flag being evaluated came from: 'explicit' for a call-site
# or context key, 'trace' or 'ephemeral' for a fallback key that Logfire chose.
_FEATURE_TARGETING_KEY_SOURCE: ContextVar[str | None] = ContextVar('_FEATURE_TARGETING_KEY_SOURCE', default=None)
# A fallback key for unkeyed flag evaluations outside a trace. It stays set for the rest of the context.
_EPHEMERAL_TARGETING_KEY: ContextVar[str | None] = ContextVar('_EPHEMERAL_TARGETING_KEY', default=None)
_TRACE_TARGETING_KEY_LOCK = threading.Lock()

# Thread pool tasks see the overrides and targeting context of the code that submitted them.
THREAD_CONTEXTVARS.extend([_VARIABLE_OVERRIDES, _TARGETING_CONTEXT, _FEATURE_TARGETING_KEY, _EPHEMERAL_TARGETING_KEY])


class ResolveFunction(Protocol[T_co]):
    """Protocol for functions that resolve variable values based on context."""

    def __call__(self, targeting_key: str | None, attributes: Mapping[str, Any] | None) -> T_co:
        """Resolve the variable value given a targeting key and attributes."""
        raise NotImplementedError  # pragma: no cover


class _TargetableVariable(Protocol):
    """Structural type accepted by variable-specific targeting contexts."""

    @property
    def name(self) -> str: ...


class _RenderFunction(Protocol):
    def __call__(self, serialized_json: str, /) -> str:
        """Render a serialized JSON value before deserialization."""
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


def _emit_resolution_warning(message: str, *, stacklevel: int = 3) -> None:
    """Emit a non-fatal resolution warning without letting it abort or corrupt resolution.

    Resolution is *filter-independent*: a ``-W error`` / ``filterwarnings=error`` config would
    otherwise turn one of these informational ``RuntimeWarning``s into an exception, which the
    broad fallback ``except`` in ``_resolve`` then catches -- replacing the correctly-computed
    ``ResolvedVariable`` (whose ``reason``/``exception`` already carry the real signal) with a
    bogus ``reason='other_error'`` and the ``RuntimeWarning`` as its exception. Suppressing the
    escalation here guarantees callers always get the structured result regardless of the active
    warning filter; the warning is still shown whenever the filter permits.
    """
    try:
        warnings.warn(message, category=RuntimeWarning, stacklevel=stacklevel)
    except Exception:
        pass


def _feature_flag_evaluation_details(
    result: ResolvedVariable[T_co],
    provider_state: VariableProviderEvaluationState = 'ready',
) -> FlagEvaluationDetails[T_co]:
    """Translate a managed-variable result into the feature-flag domain model."""
    from logfire.experimental.feature_flags import FlagErrorCode, FlagEvaluationDetails, FlagEvaluationReason

    reason: FlagEvaluationReason = 'default'
    error_code: FlagErrorCode | None = None
    error_message: str | None = None

    if result.reason == 'validation_error':
        reason = 'error'
        if _is_json_parse_error(result.exception):
            error_code = 'parse_error'
            error_message = 'Configured value is not valid JSON.'
        else:
            error_code = 'type_mismatch'
            error_message = _type_mismatch_message(result.exception)
    elif result.reason == 'other_error' or result.exception is not None:
        reason = 'error'
        error_code = 'general'
        error_message = 'Feature flag evaluation failed.'
    elif result.reason == 'context_override':
        reason = 'context_override'
    elif isinstance(result, _ResolvedFeatureFlag) and result.flag_not_found:
        reason = 'error'
        error_code = 'flag_not_found'
        error_message = f"Feature flag '{result.name}' is not configured in Logfire."
    elif result.rule_evaluation_reason == 'split':
        reason = 'split'
    elif result.rule_evaluation_reason == 'targeting_match' and result.reason == 'resolved':
        reason = 'targeting_match'
    elif result.reason == 'resolved':
        # Custom providers may resolve a value without exposing rule metadata.
        reason = 'static'

    if error_code is None and result.reason != 'context_override':
        if provider_state == 'not_ready':
            reason = 'error'
            error_code = 'provider_not_ready'
            error_message = 'The feature flag provider has not loaded configuration yet.'
        elif provider_state == 'error':
            reason = 'error'
            error_code = 'general'
            error_message = 'The feature flag provider could not load configuration.'
        elif provider_state == 'fatal':
            reason = 'error'
            error_code = 'provider_fatal'
            error_message = 'The feature flag provider is no longer available.'
        elif provider_state == 'stale':
            reason = 'stale'
        elif provider_state != 'ready':
            assert_never(provider_state)

    has_error = error_code is not None
    metadata: dict[str, Any] = {}
    if result.version is not None and not has_error:
        metadata['logfire.value_version'] = result.version
    if provider_state == 'stale' and not has_error and result.reason != 'context_override':
        metadata['logfire.provider_state'] = 'stale'
    if (
        isinstance(result, _ResolvedFeatureFlag)
        and result.targeting_key_source in ('trace', 'ephemeral')
        and reason == 'split'
    ):
        # The split used a fallback key, so the variant is only consistent within this trace.
        metadata['logfire.targeting_key_source'] = result.targeting_key_source
    return FlagEvaluationDetails(
        flag_key=result.name,
        value=result.value,
        variant=None if has_error else result.label,
        reason=reason,
        error_code=error_code,
        error_message=error_message,
        flag_metadata=metadata,
    )


def _is_json_parse_error(exception: Exception | None) -> bool:
    """Return whether validation failed because the configured value is not valid JSON."""
    return isinstance(exception, ValidationError) and any(
        error['type'] == 'json_invalid' for error in exception.errors(include_input=False, include_url=False)
    )


def _error_with_location(error: ErrorDetails) -> str:
    """Describe a validation error by its location and type."""
    return f'{".".join(str(part) for part in error["loc"]) or "value"} ({error["type"]})'


def _error_type(error: ErrorDetails) -> str:
    """Describe a validation error by its type only."""
    return error['type']


def _type_mismatch_message(
    exception: Exception | None, describe_error: Callable[[ErrorDetails], str] = _error_with_location
) -> str:
    """Describe the failing fields and error types without including the rejected input.

    Locations can contain keys from the configured value, such as the keys of a dict-typed flag.
    Telemetry leaves the process, so it describes each error with `_error_type` only.
    """
    message = 'Configured value did not match the declared flag type'
    if not isinstance(exception, ValidationError):
        return f'{message}.'
    # Error messages can quote custom validator text, and the input can contain secrets, so
    # neither is included.
    problems = [describe_error(error) for error in exception.errors(include_input=False, include_url=False)]
    shown = ', '.join(problems[:3])
    if len(problems) > 3:
        shown += f', and {len(problems) - 3} more'
    return f'{message}: {shown}.'


def _feature_flag_telemetry_attributes(
    result: ResolvedVariable[T_co],
    provider_state: VariableProviderEvaluationState = 'ready',
) -> dict[str, Any]:
    """Describe the decision; add its value only after JSON-mode serialization."""
    details = _feature_flag_evaluation_details(result, provider_state)
    result_attributes: dict[str, Any] = {
        'feature_flag.key': result.name,
        'feature_flag.provider.name': 'logfire',
        'feature_flag.result.reason': details.reason,
        'logfire.feature_flag.resolution_reason': result.reason,
    }
    if details.variant is not None:
        result_attributes['feature_flag.result.variant'] = details.variant
    if result.version is not None and details.error_code is None:
        # Managed-variable versions identify the selected value, not the complete flag ruleset.
        # Keep that useful detail without assigning OpenTelemetry's `feature_flag.version`, which
        # is reserved for a version that uniquely identifies the flag or flag set configuration.
        result_attributes['logfire.feature_flag.value_version'] = result.version
    if details.error_code is not None:
        result_attributes['error.type'] = details.error_code.lower()
        # Every internal error classification above has a matching safe, generic message.
        result_attributes['feature_flag.error.message'] = (
            _type_mismatch_message(result.exception, _error_type)
            if details.error_code == 'type_mismatch'
            else details.error_message
        )
    return result_attributes


def _feature_flag_telemetry_value(value: Any, serialized_value: str | None) -> Any:
    """Return a valid OpenTelemetry attribute without changing the existing scalar contract."""
    if isinstance(value, (bool, str, int, float)):
        return value
    if serialized_value is not None:
        return serialized_value
    return '<unavailable>'


def _scrubbed_value_changed(before: Any, after: Any) -> bool:
    """Compare JSON-compatible values without treating unchanged NaNs as replacements."""
    if isinstance(before, float) and isinstance(after, float) and math.isnan(before) and math.isnan(after):
        return False
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        before_mapping = cast(Mapping[Any, Any], before)
        after_mapping = cast(Mapping[Any, Any], after)
        return before_mapping.keys() != after_mapping.keys() or any(
            _scrubbed_value_changed(before_mapping[key], after_mapping[key]) for key in before_mapping.keys()
        )
    if (
        isinstance(before, Sequence)
        and isinstance(after, Sequence)
        and not isinstance(before, (str, bytes, bytearray))
        and not isinstance(after, (str, bytes, bytearray))
    ):
        before_sequence = cast(Sequence[Any], before)
        after_sequence = cast(Sequence[Any], after)
        return len(before_sequence) != len(after_sequence) or any(
            _scrubbed_value_changed(before_item, after_item)
            for before_item, after_item in zip(before_sequence, after_sequence)
        )
    return before != after


def _scrub_feature_flag_result(
    telemetry: dict[str, Any], name: str, value: Any, logfire_instance: logfire.Logfire
) -> dict[str, Any]:
    """Apply the same fail-closed value policy to native and OpenFeature outcomes."""
    scrub_key = f'logfire.feature_flag.result.{name}'
    try:
        scrubbed, notes = logfire_instance.config.scrubber.scrub_value(('attributes',), {scrub_key: value})
        changed = bool(notes) or _scrubbed_value_changed(value, scrubbed[scrub_key])
    except Exception:
        changed = True
    if changed:
        telemetry.pop('feature_flag.result.value', None)
        telemetry['logfire.feature_flag.result.value_status'] = 'scrubbed'
    return telemetry


# Stage of the resolution pipeline that a `_ResolveAttempt` failed at. Drives both
# the fallback warning text and the resulting `ResolutionReason` ('validation' maps
# to 'validation_error', everything else to 'other_error').
_FailureStage = str  # 'composition' | 'template rendering' | 'validation'


@dataclass
class _ResolveAttempt:
    """Outcome of a single compose -> render -> deserialize attempt.

    `ok=True` carries the successful `result`. `ok=False` carries the
    `exception` and the pipeline `stage` that failed, which the caller uses to
    decide how to fall back (e.g. a `'composition'` failure on the code default
    triggers a non-strict retry).
    """

    ok: bool
    result: ResolvedVariable[Any] | None = None
    exception: Exception | None = None
    stage: _FailureStage = ''
    composed: list[ComposedReference] = field(default_factory=list['ComposedReference'])


@dataclass(kw_only=True)
class _ResolvedFeatureFlag(ResolvedVariable[T_co]):
    """A resolution paired with the provider-health snapshot used for its telemetry and return value."""

    provider_state: VariableProviderEvaluationState
    flag_not_found: bool = False
    """Whether a ready provider has no configuration for this flag."""
    targeting_key_source: str | None = None
    """Where the targeting key came from: 'explicit', 'trace', 'ephemeral', or None without a key."""


class _FlagEvaluationCore(Generic[T_co]):
    """Shared typed evaluation engine for feature flags and the legacy variables API."""

    kind: Literal['feature_flag', 'variable']
    """The product surface the concrete declaration API represents."""

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
        self._declaration_span_pid: int | None = None
        self._declaration_lock_pid = os.getpid()
        self._declaration_lock = threading.Lock()

    def _deserialize(self, serialized_value: str) -> T_co | ValidationError | ValueError | TypeError:
        """Deserialize a JSON string to the variable's type, returning an Exception on failure."""
        try:
            return self.type_adapter.validate_json(serialized_value)
        except (ValidationError, ValueError, TypeError) as e:
            return e

    def _deserialize_resolved_value(
        self, serialized_result: ResolvedVariable[str | None], serialized_value: str
    ) -> T_co | ValidationError | ValueError | TypeError:
        """Validate a value after composition and rendering."""
        return self._deserialize(serialized_value)

    @property
    def _override_key(self) -> object:
        """Preserve the legacy name-based override scope for managed variables."""
        return self.name

    @contextmanager
    def override(self, value: T_co | ResolveFunction[T_co]) -> Generator[None]:
        """Context manager to temporarily override this variable's value.

        Inside the `with` block, every `get()` call on this variable returns
        *value* (or the result of calling it as a `ResolveFunction`) instead
        of consulting the provider or code default.

        ## Composition still applies

        Overrides **do** participate in `@{ref}@` composition: *value* runs
        through the same compose → render → deserialize pipeline as a stored
        value, so it can stand in for a candidate stored value (e.g. during
        iterative optimization) and resolve identically to how it would once
        pushed. If you override with the string `'hi @{user}@'`, the
        `@{user}@` *is* expanded against the live provider/config.

        ## Template rendering still applies to TemplateVariable

        For `TemplateVariable.get(inputs)`, `{{...}}` rendering against
        *inputs* runs on the override the same way it would on a
        provider value — *as long as the override is JSON-serializable*.
        For example, overriding with `'Hi {{name}}'` and calling
        `get(Inputs(name='Alice'))` yields `'Hi Alice'`.

        ## Unserializable overrides come back verbatim

        If *value* can't be serialized through the variable's type adapter
        (e.g. an arbitrary Python object on a `Variable[object]`), the
        override is returned exactly as you passed it in, with no
        serialize/deserialize round-trip and no template render pass. This
        matches the "literal user choice" intent — a non-JSON Python value
        is by definition not a template, so there's nothing to render.

        Args:
            value: The value to use within this context, or a function that computes
                the value based on targeting_key and attributes.
        """
        current = _VARIABLE_OVERRIDES.get() or {}
        token = _VARIABLE_OVERRIDES.set({**current, self._override_key: value})
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
        render_fn: _RenderFunction | None = None,
    ) -> ResolvedVariable[T_co]:
        # `_DEFAULT_CACHE` memoises the code-default value across every
        # `_get_default_cached` call inside this `get()` invocation, so a
        # callable default isn't re-invoked when a downstream fallback path also
        # needs it. Both values and exceptions are cached.
        cache_token = _DEFAULT_CACHE.set({})
        try:
            return self._resolve_inner(targeting_key, attributes, span, label, render_fn)
        finally:
            _DEFAULT_CACHE.reset(cache_token)

    def _resolve_inner(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        label: str | None,
        render_fn: _RenderFunction | None,
    ) -> ResolvedVariable[T_co]:
        serialized_result: ResolvedVariable[str | None] | None = None
        try:
            # Top-level context-override fast path: handled here, before
            # `_lookup_serialized` even sees the name. The override runs
            # through the same compose (`@{ref}@`) → render (`{{}}`) →
            # deserialize pipeline as a stored value (see
            # `_resolve_context_override`), and the round-trip through
            # dump_json / validate_json that `_lookup_serialized` would
            # otherwise perform silently drops any value that isn't
            # JSON-serializable. Restore the pre-#1951 behaviour: if the
            # override serializes, take the compose/render path; if it
            # doesn't, return the typed Python value verbatim.
            context_overrides = _VARIABLE_OVERRIDES.get()
            if context_overrides is not None and self._override_key in context_overrides:
                return self._resolve_context_override(
                    context_overrides[self._override_key], targeting_key, attributes, span, render_fn
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

            if serialized_result.reason == 'code_default':
                # The lookup chain already fell through to the (serializable) code
                # default. Compose it the lenient way (strict, then non-strict, then
                # raw) — there's nothing further to fall back to.
                return self._resolve_code_default_value(
                    serialized_result.value,
                    provider,
                    targeting_key,
                    attributes,
                    span,
                    render_fn,
                    trigger_exc=None,
                    trigger_stage='',
                    label=None,
                    version=None,
                    provider_exception=serialized_result.exception,
                    feature_flag_reason=serialized_result.rule_evaluation_reason,
                )

            # A provider (or label-specific) value: compose it strictly, so any
            # unresolved `@{ref}@`/`@{ref.field}@` (or cycle/parse/depth) falls back
            # to the code default rather than rendering empty in place.
            attempt = self._try_resolve(
                serialized_result, provider, targeting_key, attributes, span, render_fn, strict=True
            )
            if attempt.ok:
                # A provider/label value carries no exception of its own (providers don't attach
                # one to a value that's present); the provider-error cases all return value=None
                # and flow through the code-default path below, which surfaces the exception.
                return cast('ResolvedVariable[T_co]', attempt.result)
            return self._resolve_code_default_value(
                self._get_serialized_default(targeting_key, attributes),
                provider,
                targeting_key,
                attributes,
                span,
                render_fn,
                trigger_exc=attempt.exception,
                trigger_stage=attempt.stage,
                trigger_composed=attempt.composed,
                label=serialized_result.label,
                version=serialized_result.version,
                provider_exception=serialized_result.exception,
                feature_flag_reason=serialized_result.rule_evaluation_reason,
            )

        except TemplateInputsMismatchError:
            # The `'error'` template_mismatch_policy explicitly opts into a
            # loud failure mode — bypass the default-fallback path and let
            # the exception reach the caller.
            raise
        except Exception as e:
            if span and serialized_result is not None:  # pragma: no cover
                self._record_invalid_value(span, serialized_result.label, serialized_result.value)
            try:
                default = self._get_default_cached(targeting_key, attributes)
            except Exception as default_exc:
                default = cast('T_co', None)
                _emit_resolution_warning(
                    f"Variable '{self.name}' could not be resolved and its code default raised; "
                    f'returning None: {default_exc}'
                )
            return ResolvedVariable(name=self.name, value=default, exception=e, reason='other_error')

    def _resolve_context_override(
        self,
        override_value: T_co | ResolveFunction[T_co],
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        render_fn: _RenderFunction | None,
    ) -> ResolvedVariable[T_co]:
        """Return a resolution for the top-level context override.

        When the override value serializes cleanly, run it through the same
        compose (`@{ref}@`) → render (`{{}}`) → deserialize pipeline a stored
        value takes, so an override can stand in for a candidate stored value
        (e.g. during iterative optimization) and resolve identically to how it
        would once pushed. `@{ref}@` references are expanded against the live
        provider/config, so the override participates in composition.

        When the value doesn't serialize — common for custom Python types,
        arbitrary objects, etc. — return the user's value verbatim under
        `reason='context_override'` (no compose/render pass possible without a
        string form). Returning verbatim is the legacy behaviour Devin / Alex
        flagged on #1951; the previous implementation silently dropped these
        values back to the provider / code default.
        """
        if is_resolve_function(override_value):
            resolved_value = cast('T_co', override_value(targeting_key, attributes))
        else:
            resolved_value = cast('T_co', override_value)
        try:
            serialized = self.type_adapter.dump_json(resolved_value).decode('utf-8')
        except (ValueError, TypeError, RuntimeError):
            return ResolvedVariable(name=self.name, value=resolved_value, reason='context_override')

        provider = self.logfire_instance.config.get_variable_provider()
        serialized_result = ResolvedVariable[str | None](name=self.name, value=serialized, reason='context_override')
        # Compose the override strictly (it stands in for a candidate provider value), so a
        # missing reference falls back to the code default just as a stored value would.
        attempt = self._try_resolve(
            serialized_result, provider, targeting_key, attributes, span, render_fn, strict=True
        )
        if attempt.ok:
            result = cast('ResolvedVariable[T_co]', attempt.result)
            result.reason = 'context_override'
            return result
        return self._resolve_code_default_value(
            self._get_serialized_default(targeting_key, attributes),
            provider,
            targeting_key,
            attributes,
            span,
            render_fn,
            trigger_exc=attempt.exception,
            trigger_stage=attempt.stage,
            trigger_composed=attempt.composed,
            label=None,
            version=None,
            provider_exception=None,
            feature_flag_reason=None,
        )

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
        variable = self if name == self.name else self._variable_registry.get(name)
        context_overrides = _VARIABLE_OVERRIDES.get()

        # 1. Context override (only for variables whose type we know)
        if variable is not None and context_overrides is not None and variable._override_key in context_overrides:
            override_value = context_overrides[variable._override_key]
            if is_resolve_function(override_value):
                override_value = override_value(targeting_key, attributes)
            try:
                serialized = variable.type_adapter.dump_json(override_value).decode('utf-8')
            except (ValueError, TypeError, RuntimeError) as e:
                _emit_resolution_warning(
                    f"Context override for variable '{name}' could not be serialized while resolving "
                    f"'{self.name}' composition; falling through to provider/code default: {e}"
                )
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
                    label=None,
                    version=None,
                    reason='code_default',
                    exception=provider_result.exception,
                    rule_evaluation_reason=provider_result.rule_evaluation_reason,
                )

        # No value at any tier; propagate the provider's metadata so callers
        # can surface the original exception/reason.
        return provider_result

    def _try_resolve(
        self,
        serialized_result: ResolvedVariable[str | None],
        provider: VariableProvider,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        render_fn: _RenderFunction | None = None,
        *,
        strict: bool,
    ) -> _ResolveAttempt:
        """Attempt one compose -> render -> deserialize pass over a serialized value.

        Composition runs in *strict* mode when `strict=True`: an unresolved
        `@{ref}@`/`@{ref.field}@` raises rather than rendering empty, so the
        caller can fall back. On any failure this returns an unsuccessful
        `_ResolveAttempt` (with the failing stage) rather than falling back
        itself — the caller decides what to do. `render_fn` (template `{{}}`
        rendering) is applied after composition and is always non-strict.
        """
        from pydantic_handlebars import HandlebarsError

        assert serialized_result.value is not None
        serialized_value = serialized_result.value

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

        composed: list[ComposedReference] = []
        # Always run through `expand_references`, even when no `@{ref}@` tags
        # are present: it's also responsible for unescaping `\@{...}@` →
        # `@{...}@`. Gating on `has_references` produced inconsistent
        # observable behaviour where an escaped-only value (e.g.
        # `r'\@{baz}@'`) kept its backslash, but the same escape combined
        # with a real reference correctly produced the literal `@{baz}@`.
        try:
            serialized_value, composed = expand_references(
                serialized_value,
                self.name,
                resolve_ref,
                strict=strict,
            )
            if fatal_error := _first_fatal_composition_error(composed):
                # Cycles / depth overflow are structural failures — the value can't be
                # meaningfully composed at all, in either strictness mode. Carry `composed`
                # so the fall-back result can surface the failure chain in `composed_from`.
                return _ResolveAttempt(
                    ok=False,
                    exception=VariableCompositionError(fatal_error),
                    stage='composition',
                    composed=composed,
                )
        except (VariableCompositionError, HandlebarsError, AssertionError) as e:
            # VariableCompositionError: cycle/depth overflow raised by expand_references.
            # HandlebarsError: an unresolved reference under strict mode, or a malformed
            # (`@{#if x}@`) value; AssertionError: a reserved name (`@{true}@`). All are
            # composition failures the caller turns into a code-default fall back.
            return _ResolveAttempt(ok=False, exception=e, stage='composition')

        # Apply render_fn (template rendering) if provided. Note: a
        # `TemplateInputsMismatchError` from the `'error'` policy is intentionally
        # not caught here — it propagates to the caller as a loud failure.
        if render_fn is not None:
            try:
                serialized_value = render_fn(serialized_value)
            except (HandlebarsError, ValueError, TypeError) as e:
                return _ResolveAttempt(ok=False, exception=e, stage='template rendering')

        # Deserialize the (possibly expanded/rendered) value.
        value_or_exc = self._deserialize_resolved_value(serialized_result, serialized_value)
        if isinstance(value_or_exc, Exception):
            if span:  # pragma: no branch
                self._record_invalid_value(span, serialized_result.label, serialized_value)
            return _ResolveAttempt(ok=False, exception=value_or_exc, stage='validation')

        return _ResolveAttempt(
            ok=True,
            result=ResolvedVariable(
                name=self.name,
                value=value_or_exc,
                label=serialized_result.label,
                version=serialized_result.version,
                reason='resolved',
                composed_from=composed,
                rule_evaluation_reason=serialized_result.rule_evaluation_reason,
            ),
        )

    def _resolve_code_default_value(
        self,
        serialized_default: str | None,
        provider: VariableProvider,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        span: logfire.LogfireSpan | None,
        render_fn: _RenderFunction | None,
        *,
        trigger_exc: Exception | None,
        trigger_stage: _FailureStage,
        trigger_composed: list[ComposedReference] | None = None,
        label: str | None,
        version: int | None,
        provider_exception: Exception | None,
        feature_flag_reason: RuleEvaluationReason | None,
    ) -> ResolvedVariable[T_co]:
        """Resolve via the code default: compose strict, then non-strict, then raw.

        The code default is the lenient last resort, so an unresolved `@{ref}@`
        *within it* renders as an empty string (non-strict) rather than failing —
        there is nowhere further to fall back to. A structural failure (cycle /
        depth / parse) even under non-strict, or a render/validation failure,
        falls back to the raw, uncomposed default value.

        `trigger_exc`/`trigger_stage` describe the provider/override failure that
        triggered this fall back, or are `None` when the code default is itself
        the primary resolved value. When set, the result carries that provenance
        (`reason`, `exception`, and the original `label`/`version`).
        """
        if trigger_exc is not None:
            self._warn_fallback(trigger_stage, trigger_exc)

        if serialized_default is None:
            # The code default isn't JSON-serializable (e.g. an arbitrary Python object or a
            # callable returning one), so there's nothing to compose — return it verbatim.
            return ResolvedVariable(
                name=self.name,
                value=self._get_default_cached(targeting_key, attributes),
                exception=trigger_exc if trigger_exc is not None else provider_exception,
                reason=self._fallback_reason(trigger_stage) if trigger_exc is not None else 'code_default',
                label=label,
                version=version,
                rule_evaluation_reason=feature_flag_reason,
            )

        default_result = ResolvedVariable[str | None](
            name=self.name,
            value=serialized_default,
            reason='code_default',
            rule_evaluation_reason=feature_flag_reason,
        )
        # Compose the code default strictly first; if a reference within it is unresolved,
        # re-compose non-strict so the missing reference renders as an empty string.
        attempt = self._try_resolve(default_result, provider, targeting_key, attributes, span, render_fn, strict=True)
        if not attempt.ok and attempt.stage == 'composition':
            attempt = self._try_resolve(
                default_result, provider, targeting_key, attributes, span, render_fn, strict=False
            )
            if attempt.ok:
                _emit_resolution_warning(
                    f"Variable '{self.name}' code default has unresolved composition reference(s); "
                    'rendering them as empty strings.'
                )

        if attempt.ok:
            result = cast('ResolvedVariable[T_co]', attempt.result)
            if trigger_exc is not None:
                result.reason = self._fallback_reason(trigger_stage)
                result.exception = trigger_exc
                result.label = label
                result.version = version
                # Surface why the original value was discarded (e.g. the cycle chain), rather
                # than the code default's own (here, successful) composition tree.
                if trigger_composed:
                    result.composed_from = trigger_composed
            else:
                result.reason = 'code_default'
                result.label = None
                result.version = None
                if result.exception is None and provider_exception is not None:
                    result.exception = provider_exception
            return result

        # The code default failed even non-strict (a cycle/parse/depth error, or a
        # render/validation failure) — return the raw, uncomposed default value.
        final_exc = trigger_exc if trigger_exc is not None else attempt.exception
        final_stage = trigger_stage if trigger_exc is not None else attempt.stage
        if trigger_exc is None and final_exc is not None:
            self._warn_fallback(final_stage, final_exc, code_default=True)
        return ResolvedVariable(
            name=self.name,
            value=self._get_default_cached(targeting_key, attributes),
            exception=final_exc,
            reason=self._fallback_reason(final_stage),
            label=label,
            version=version,
            composed_from=trigger_composed or [],
            rule_evaluation_reason=feature_flag_reason,
        )

    @staticmethod
    def _fallback_reason(stage: _FailureStage) -> ResolutionReason:
        """Map a failing pipeline stage to the resolution reason for the fallback."""
        return 'validation_error' if stage == 'validation' else 'other_error'

    def _record_invalid_value(self, span: logfire.LogfireSpan, label: str | None, value: str | None) -> None:
        """Preserve the legacy managed-variable diagnostics."""
        span.set_attribute('invalid_serialized_label', label)
        span.set_attribute('invalid_serialized_value', value)

    def _warn_fallback(self, stage: _FailureStage, exception: Exception, *, code_default: bool = False) -> None:
        """Warn that resolution fell back after a failure at *stage*.

        *stage* identifies which step failed (composition / template rendering /
        validation) so the message is accurate. A validation failure uses the
        richer `_warn_validation_fallback` formatting.
        """
        if stage == 'validation':
            self._warn_validation_fallback(exception)
        elif code_default:
            _emit_resolution_warning(
                f"Variable '{self.name}' code default {stage} failed; returning the raw default: {exception}"
            )
        else:
            _emit_resolution_warning(
                f"Variable '{self.name}' {stage} failed; falling back to code default: {exception}"
            )

    def _get_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> T_co:
        if is_resolve_function(self.default):
            return self.default(targeting_key, merged_attributes)
        else:
            return self.default

    def _get_default_cached(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> T_co:
        """Return the code default, memoised for the duration of one `_resolve` call.

        Avoids re-invoking a callable default twice when the same `get()`
        consults it on multiple fallback paths. Both successful values and
        raised exceptions are cached -- a callable that raises on first
        invocation re-raises (without re-invoking) on subsequent calls, so a
        failing default doesn't get called multiple times either. Outside a
        `_resolve` call the cache is not set and this is a direct passthrough to
        `_get_default`.
        """
        cache = _DEFAULT_CACHE.get()
        if cache is None:  # pragma: no cover
            # Defensive: every production call site is inside `_resolve`, which
            # sets the cache. Falling back to a direct compute keeps the helper
            # safe if someone reaches in from an unexpected entry point in the
            # future.
            return self._get_default(targeting_key, merged_attributes)
        key = id(self)
        if key not in cache:
            try:
                cache[key] = (True, self._get_default(targeting_key, merged_attributes))
            except Exception as e:
                cache[key] = (False, e)
        ok, payload = cache[key]
        if ok:
            return cast('T_co', payload)
        raise cast('Exception', payload)

    def _get_serialized_default(
        self, targeting_key: str | None = None, merged_attributes: Mapping[str, Any] | None = None
    ) -> str | None:
        """Return the code default serialized as JSON, or None if serialization fails."""
        try:
            default = self._get_default_cached(targeting_key, merged_attributes)
            return self.type_adapter.dump_json(default).decode('utf-8')
        except (ValueError, TypeError, RuntimeError):
            return None

    def _resolve_code_default(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        serialized_result: ResolvedVariable[str | None],
    ) -> ResolvedVariable[T_co]:
        """Build a ResolvedVariable from the registered code default."""
        return ResolvedVariable(
            name=self.name,
            value=self._get_default_cached(targeting_key, attributes),
            exception=serialized_result.exception,
            label=None,
            version=None,
            reason='code_default',
            rule_evaluation_reason=serialized_result.rule_evaluation_reason,
        )

    def _warn_validation_fallback(self, error: Exception) -> None:
        detail: object = (
            error.errors(include_input=False, include_url=False) if isinstance(error, ValidationError) else error
        )
        _emit_resolution_warning(
            f"Variable '{self.name}' value failed validation; falling back to code default: {detail}"
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
        result.update(_get_contextvar_attributes())
        if attributes is not None:
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

        # Get the serialized default value as an example (if not a function). Use
        # `_get_serialized_default`, which tolerates a non-serializable default by returning None.
        example: str | None = None
        if not is_resolve_function(self.default):
            example = self._get_serialized_default()

        return VariableConfig(
            name=self.name,
            description=self.description,
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
            json_schema=json_schema,
            example=example,
        )

    def _emit_declaration_once(self, resolution_span: logfire.LogfireSpan) -> None:
        """Emit one code-first definition span per variable and process.

        The declaration is telemetry, not remote configuration: it lets Logfire offer an
        unrecognized code-defined variable for confirmation without allowing application
        processes to create or activate remote variables. A process created with ``fork``
        gets its own declaration opportunity because its telemetry pipeline may be distinct.
        """
        pid = os.getpid()
        if self._declaration_span_pid == pid or not resolution_span.is_recording():
            return

        # A lock can be inherited while held when a multi-threaded process forks. Replace it
        # in the child before acquiring it rather than risking a permanent deadlock.
        if self._declaration_lock_pid != pid:
            self._declaration_lock = threading.Lock()
            self._declaration_lock_pid = pid

        with self._declaration_lock:
            if self._declaration_span_pid == pid:
                return
            # Claim before generating metadata. Pydantic schema hooks are user code and may
            # resolve this variable recursively; the nested call must see the claim rather
            # than block on this non-reentrant lock. Telemetry is best-effort, so a failure
            # remains claimed instead of disrupting every future resolution attempt.
            self._declaration_span_pid = pid

        # Build metadata after releasing the lock. JSON Schema hooks are user code and may be
        # slow as well as reentrant; declaration telemetry must not serialize concurrent reads.
        try:
            attributes = self._declaration_attributes()
            # Keep the concrete name rather than f-string magic's source template so the
            # span is immediately useful when viewed outside the discovery UI.
            declaration_span_name = f'Declare variable {self.name}'
            with self.logfire_instance.span(declaration_span_name, **attributes) as declaration_span:
                if not declaration_span.is_recording():
                    with self._declaration_lock:
                        self._declaration_span_pid = None
        except Exception:
            return

    def _declaration_attributes(self) -> dict[str, Any]:
        attributes: dict[str, Any] = {
            'logfire.variable.declaration': True,
            'logfire.variable.declaration_version': 1,
            'logfire.variable.name': self.name,
            'logfire.variable.kind': self.kind,
        }
        if self.description:
            # The remote API accepts at most 500 characters, so sending more cannot improve
            # the confirmation flow and needlessly increases telemetry volume.
            attributes['logfire.variable.description'] = self.description[:500]

        try:
            schema = json.dumps(
                _declaration_schema_without_defaults(self.type_adapter.json_schema()),
                ensure_ascii=False,
                separators=(',', ':'),
                sort_keys=True,
            )
        except Exception:  # Some arbitrary user-defined types cannot produce JSON Schema.
            attributes['logfire.variable.schema_status'] = 'unavailable'
        else:
            self._attach_bounded_attribute(attributes, 'logfire.variable.schema', schema)

        if is_resolve_function(self.default):
            # Do not invoke user code merely to populate discovery metadata. The callable may
            # be expensive, context-dependent, or have side effects.
            attributes['logfire.variable.code_default_status'] = 'dynamic'
        else:
            try:
                serialized_default = self._get_serialized_default()
            except Exception:
                serialized_default = None
            if serialized_default is None:
                attributes['logfire.variable.code_default_status'] = 'unavailable'
            else:
                # The exported attribute has a generic name, so normal span scrubbing cannot
                # infer that an opaque value belongs to a variable named ``api_key`` or
                # ``password``. Scrub it under the user-provided variable name first.
                scrub_key = f'logfire.variable.code_default.{self.name}'
                scrubbed, scrubbed_notes = self.logfire_instance.config.scrubber.scrub_value(
                    ('attributes',), {scrub_key: serialized_default}
                )
                if scrubbed_notes:
                    attributes['logfire.variable.code_default_status'] = 'scrubbed'
                else:
                    scrubbed_default = scrubbed[scrub_key]
                    if isinstance(scrubbed_default, str):
                        self._attach_bounded_attribute(attributes, 'logfire.variable.code_default', scrubbed_default)
                    else:
                        attributes['logfire.variable.code_default_status'] = 'unavailable'

        try:
            inputs_schema = get_template_inputs_schema(self)
            if inputs_schema is not None:
                serialized_inputs_schema = json.dumps(
                    _declaration_schema_without_defaults(inputs_schema),
                    ensure_ascii=False,
                    separators=(',', ':'),
                    sort_keys=True,
                )
                self._attach_bounded_attribute(
                    attributes, 'logfire.variable.template_inputs_schema', serialized_inputs_schema
                )
        except Exception:
            attributes['logfire.variable.template_inputs_schema_status'] = 'unavailable'
        return attributes

    @staticmethod
    def _attach_bounded_attribute(attributes: dict[str, Any], name: str, value: str) -> None:
        size = len(value.encode())
        attributes[f'{name}_size_bytes'] = size
        if size <= _MAX_DECLARATION_ATTRIBUTE_BYTES:
            attributes[name] = value
        else:
            attributes[f'{name}_status'] = 'too_large'
            attributes[f'{name}_preview'] = value.encode()[:_MAX_DECLARATION_PREVIEW_BYTES].decode(errors='ignore')

    def _get_result_and_record_span(
        self,
        targeting_key: str | None,
        attributes: Mapping[str, Any] | None,
        label: str | None,
        render_fn: _RenderFunction | None = None,
    ) -> ResolvedVariable[T_co]:
        """Common get() logic: resolve targeting key, open span, call _resolve, record attributes."""
        merged_attributes = self._get_merged_attributes(attributes)

        # Targeting key resolution: call-site > contextvar > trace_id
        if targeting_key is None:
            targeting_key = _get_contextvar_targeting_key(self.name)

        if targeting_key is None:
            targeting_key = self._fallback_targeting_key()

        # Include the variable name directly here to make the span name more useful,
        # it'll still be low cardinality. This also prevents it from being scrubbed from the message.
        # Don't inline the f-string to avoid f-string magic.
        span_name = 'feature_flag.evaluation' if self.kind == 'feature_flag' else f'Resolve variable {self.name}'
        with ExitStack() as stack:
            span: logfire.LogfireSpan | None = None
            if _get_variables_instrument(self.logfire_instance.config.variables):
                span_context = self._telemetry_context(targeting_key, merged_attributes)
                span = stack.enter_context(
                    self.logfire_instance.span(
                        span_name,
                        name=self.name,
                        **span_context,
                    )
                )
                # Emit discovery metadata before the first access. Keep it on its own child span
                # so declaration attribute limits cannot displace resolution telemetry.
                self._emit_declaration_once(span)
            result = self._finalize_resolution_result(
                self._resolve(targeting_key, merged_attributes, span, label, render_fn=render_fn)
            )
            if span is not None:
                # Serialize value safely for OTel span attributes, which only support primitives.
                # Keep the legacy repr fallback for variables, never for feature flags: repr
                # can include fields absent from the JSON shape inspected by the scrubber.
                try:
                    serialized_value = self.type_adapter.dump_json(result.value).decode('utf-8')
                except (ValueError, TypeError, RuntimeError):
                    serialized_value = None if self.kind == 'feature_flag' else repr(result.value)
                attrs = self._resolution_telemetry_attributes(
                    result,
                    serialized_value=serialized_value,
                    targeting_key=targeting_key,
                    attributes=merged_attributes,
                    requested_label=label,
                )
                if result.composed_from:
                    import json

                    attrs['composed_from'] = json.dumps(
                        [_serialize_composed_reference(c) for c in result.composed_from]
                    )
                span.set_attributes(attrs)
                if result.exception:
                    self._record_resolution_exception(span, result.exception)
            return result

    def _finalize_resolution_result(self, result: ResolvedVariable[T_co]) -> ResolvedVariable[T_co]:
        """Finalize a resolved value before both telemetry and the caller observe it."""
        return result

    def _resolution_telemetry_attributes(
        self,
        result: ResolvedVariable[T_co],
        *,
        serialized_value: str | None,
        targeting_key: str | None,
        attributes: Mapping[str, Any],
        requested_label: str | None,
    ) -> dict[str, Any]:
        """Build attributes for a managed-variable resolution span."""
        return {
            'name': result.name,
            'value': serialized_value,
            'label': result.label,
            'version': result.version,
            'reason': result.reason,
        }

    def _telemetry_context(self, targeting_key: str | None, attributes: Mapping[str, Any]) -> dict[str, Any]:
        """Return evaluation context attributes included on the resolution span."""
        return {'targeting_key': targeting_key, 'attributes': attributes}

    def _record_resolution_exception(self, span: logfire.LogfireSpan, exception: BaseException) -> None:
        """Record a managed-variable resolution exception."""
        span.record_exception(exception)

    def _fallback_targeting_key(self) -> str | None:
        """Return the targeting key to use when neither the caller nor the context supplies one."""
        current_trace_id = get_current_span().get_span_context().trace_id
        # If there is no active trace, the current_trace_id will be zero
        return f'trace_id:{current_trace_id:032x}' if current_trace_id else None

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


class Variable(_FlagEvaluationCore[T_co]):
    """Backward-compatible managed-variable API implemented on the feature-flag evaluation core."""

    kind = 'variable'


class _ManagedVariableFlagAdapter(_FlagEvaluationCore[FlagT]):  # pyright: ignore[reportUnusedClass]
    """Native feature-flag adapter backed by the shared typed evaluation core."""

    kind = 'feature_flag'

    @property
    def _override_key(self) -> object:
        """Keep test overrides local to the declared flag, not every instance sharing its name."""
        return self

    def _record_invalid_value(self, span: logfire.LogfireSpan, label: str | None, value: str | None) -> None:
        # Rejected configuration can contain secrets too. Only record the safe error classification,
        # never the raw input or its label through the legacy diagnostic path.
        pass

    def _warn_fallback(self, stage: _FailureStage, exception: Exception, *, code_default: bool = False) -> None:
        # Validators and serializers are user code; even exception text can contain rejected
        # credentials. Keep actionable classification without including inputs or exceptions.
        stage_description = 'value failed validation' if stage == 'validation' else f'{stage} failed'
        _emit_resolution_warning(f"Feature flag '{self.name}' {stage_description}; falling back to code default.")

    def _fallback_targeting_key(self) -> str:
        """Return a random key that keeps unkeyed evaluations consistent within the current trace.

        The key belongs to the local trace scope, which lasts from the start to the end of this
        process's root span for the trace. Work started inside that span shares the key, and a new
        root span draws a new one, even with the same trace ID. A caller therefore cannot reuse a
        trace ID to keep a variant. Outside a trace, a random key stays set for the rest of the
        current context.
        """
        scope = current_trace_scope()
        if scope is not None:
            with _TRACE_TARGETING_KEY_LOCK:
                if scope.feature_flag_targeting_key is None:
                    scope.feature_flag_targeting_key = f'trace:{secrets.token_hex(16)}'
                return scope.feature_flag_targeting_key
        key = _EPHEMERAL_TARGETING_KEY.get()
        if key is None:
            key = f'ephemeral:{secrets.token_hex(16)}'
            _EPHEMERAL_TARGETING_KEY.set(key)
        return key

    def __init__(
        self,
        name: str,
        *,
        type: type[FlagT],
        default: FlagT,
        description: str | None = None,
        logfire_instance: logfire.Logfire,
    ):
        # Managed variables permit incompatible sentinel defaults, but a typed feature flag
        # promises that every value it returns conforms to its declared type. Validate before
        # initializing the variables engine so it never observes an invalid default.
        if callable(default):
            raise TypeError('Feature flag defaults must be static values, not callables.')
        validated_default = TypeAdapter[FlagT](type).validate_python(default, strict=True)
        super().__init__(
            name,
            type=type,
            default=validated_default,
            description=description,
            logfire_instance=logfire_instance,
        )

    def _deserialize(self, serialized_value: str) -> FlagT | ValidationError | ValueError | TypeError:
        """Validate remote values without coercing one JSON scalar type into another."""
        try:
            return self.type_adapter.validate_json(serialized_value, strict=True)
        except (ValidationError, ValueError, TypeError) as e:
            return e

    def _deserialize_resolved_value(
        self, serialized_result: ResolvedVariable[str | None], serialized_value: str
    ) -> FlagT | ValidationError | ValueError | TypeError:
        # Defaults and test overrides are already validated Python values. Only validate again
        # when composition changed their serialized value; validators need not be idempotent.
        if serialized_value == serialized_result.value:
            if serialized_result.reason == 'code_default':
                # Native flags reject callable defaults at construction; the shared core also
                # supports legacy callable defaults, so its attribute type is wider.
                return self.default  # pyright: ignore[reportReturnType]
            if serialized_result.reason == 'context_override':
                overrides = _VARIABLE_OVERRIDES.get()
                if overrides is not None and self._override_key in overrides:
                    return overrides[self._override_key]
        return self._deserialize(serialized_value)

    def override(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, value: FlagT | ResolveFunction[FlagT]
    ) -> AbstractContextManager[None]:
        """Validate the override value when it is created, before it enters the flag's context."""
        validated_value: FlagT = self.type_adapter.validate_python(value, strict=True)
        return super().override(validated_value)

    def get(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
        *,
        label: str | None = None,
    ) -> ResolvedVariable[FlagT]:
        """Evaluate the flag and return its value and resolution details."""
        if targeting_key is None:
            targeting_key = self._get_context_targeting_key()
        has_stable_targeting_key = targeting_key is not None
        if has_stable_targeting_key:
            source = 'explicit'
        else:
            targeting_key = self._fallback_targeting_key()
            source = 'trace' if targeting_key.startswith('trace:') else 'ephemeral'

        source_token = _FEATURE_TARGETING_KEY_SOURCE.set(source)
        try:
            result = super().get(targeting_key, attributes, label=label)
        finally:
            _FEATURE_TARGETING_KEY_SOURCE.reset(source_token)
        if not has_stable_targeting_key and result.reason != 'context_override':
            try:
                variable_config = self.logfire_instance.config.get_variable_provider().get_variable_config(self.name)
                requires_targeting_key = variable_config is not None and variable_config.requires_targeting_key(
                    self._get_merged_attributes(attributes)
                )
            except Exception:
                # This inspection only enriches a warning. Malformed custom-provider metadata
                # must not replace the safe value already returned by resolution.
                return result
            label_selects_static_value = (
                variable_config is not None and label is not None and label in variable_config.labels
            )
            if requires_targeting_key and not label_selects_static_value:
                _emit_resolution_warning(
                    f"Feature flag '{self.name}' has a percentage rollout but no stable targeting key, "
                    'so the variant stays the same only within the current trace. '
                    'Pass targeting_key=... or use feature_context(...) to keep each subject on one variant.',
                )
        return result

    def _get_context_targeting_key(self) -> str | None:
        """Resolve feature-specific context without losing variable-specific precedence."""
        context = _TARGETING_CONTEXT.get()
        if context is not None and self.name in context.by_variable:
            return context.by_variable[self.name]
        feature_key = _FEATURE_TARGETING_KEY.get()
        if feature_key is not None:
            return feature_key
        return context.default if context is not None else None

    def _telemetry_context(self, targeting_key: str | None, attributes: Mapping[str, Any]) -> dict[str, Any]:
        # Targeting attributes can contain customer data, so they never leave the process. The
        # targeting key answers "why did this subject get this variant?", so it is recorded as
        # OpenTelemetry's `feature_flag.context.id` when the application supplied it.
        del attributes
        if targeting_key is None or _FEATURE_TARGETING_KEY_SOURCE.get() != 'explicit':
            return {}
        return {'feature_flag.context.id': targeting_key}

    def _record_resolution_exception(self, span: logfire.LogfireSpan, exception: BaseException) -> None:
        # Provider exceptions may contain targeting data. The generic error attributes retain the
        # actionable classification without exporting exception text from feature-flag evaluation.
        del span, exception

    def _resolution_telemetry_attributes(
        self,
        result: ResolvedVariable[FlagT],
        *,
        serialized_value: str | None,
        targeting_key: str | None,
        attributes: Mapping[str, Any],
        requested_label: str | None,
    ) -> dict[str, Any]:
        del targeting_key, requested_label
        if not isinstance(result, _ResolvedFeatureFlag):
            result = self._finalize_resolution_result(result)
            try:
                serialized_value = self.type_adapter.dump_json(result.value).decode()
            except (ValueError, TypeError, RuntimeError):
                serialized_value = None
        provider_state = result.provider_state
        telemetry = _feature_flag_telemetry_attributes(result, provider_state)
        try:
            # Scrub the same JSON-compatible shape used for structured evaluation telemetry.
            # Python-mode serializers may leave nested credentials inside opaque objects.
            value = self.type_adapter.dump_python(result.value, mode='json')
        except (ValueError, TypeError, RuntimeError):
            # The serialized fallback is one opaque string, so path-based scrubbing cannot inspect
            # nested fields. Omit it instead of weakening the scrubber's fail-closed guarantee.
            telemetry['logfire.feature_flag.result.value_status'] = 'serialization_error'
            return telemetry
        # Honor serializer redaction for scalars as well as structured values. The exported
        # scalar must come from the same JSON-mode value inspected by the scrubber below.
        telemetry['feature_flag.result.value'] = _feature_flag_telemetry_value(value, serialized_value)
        return _scrub_feature_flag_result(telemetry, self.name, value, self.logfire_instance)

    def evaluate_flag(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails[FlagT]:
        """Evaluate through managed variables and translate to the feature-flag contract."""
        result = self.get(targeting_key, attributes)
        if not isinstance(result, _ResolvedFeatureFlag):  # pragma: no cover - base-class contract guard
            result = self._finalize_resolution_result(result)
        return _feature_flag_evaluation_details(result, result.provider_state)

    def _finalize_resolution_result(self, result: ResolvedVariable[FlagT]) -> _ResolvedFeatureFlag[FlagT]:
        """Apply one provider-health snapshot to the returned value and its telemetry."""
        provider_state = self._get_provider_evaluation_state()
        result = self._result_for_provider_state(result, provider_state)
        return _ResolvedFeatureFlag(
            name=result.name,
            value=result.value,
            label=result.label,
            version=result.version,
            exception=result.exception,
            composed_from=result.composed_from,
            reason=result.reason,
            rule_evaluation_reason=result.rule_evaluation_reason,
            provider_state=provider_state,
            flag_not_found=self._is_flag_not_found(result, provider_state),
            targeting_key_source=_FEATURE_TARGETING_KEY_SOURCE.get(),
        )

    def _is_flag_not_found(
        self, result: ResolvedVariable[FlagT], provider_state: VariableProviderEvaluationState
    ) -> bool:
        """Return whether a provider with loaded configuration has no entry for this flag.

        A flag that is configured but whose rollout selects the code default is not missing.
        Without a configured provider, for example without an API key, flags use their code
        defaults without reporting an error.
        """
        from logfire.variables.abstract import NoOpVariableProvider

        if result.reason != 'code_default' or result.exception is not None or provider_state not in ('ready', 'stale'):
            return False
        try:
            provider = self.logfire_instance.config.get_variable_provider()
            return not isinstance(provider, NoOpVariableProvider) and provider.get_variable_config(self.name) is None
        except Exception:
            # This check only classifies a value that resolution already returned safely.
            return False

    def _result_for_provider_state(
        self,
        result: ResolvedVariable[FlagT],
        provider_state: VariableProviderEvaluationState,
    ) -> ResolvedVariable[FlagT]:
        """Use the code default when the provider cannot safely serve configuration."""
        if result.reason == 'context_override':
            return result
        if provider_state in ('not_ready', 'error', 'fatal'):
            # Feature flags reject callable defaults during construction, so the inherited union
            # has been narrowed at runtime even though the shared core's annotation cannot express it.
            default: FlagT = self.default  # pyright: ignore[reportAssignmentType]
            return ResolvedVariable(name=self.name, value=default, reason='code_default')
        return result

    def _get_provider_evaluation_state(self) -> VariableProviderEvaluationState:
        """Read provider health without allowing diagnostics to break evaluation."""
        try:
            state = self.logfire_instance.config.get_variable_provider().get_evaluation_state()
        except Exception:
            return 'error'
        if state in ('not_ready', 'ready', 'stale', 'fatal'):
            return state
        return 'error'


class TemplateVariable(Variable[T_co], Generic[T_co, InputsT]):
    """A managed variable with integrated template rendering.

    Like `Variable`, but `get()` requires `inputs` and automatically renders
    Handlebars `{{placeholder}}` templates in the resolved value before returning.
    The pipeline is: resolve → compose `@{refs}@` → render `{{}}` → deserialize.
    """

    inputs_type: type[InputsT]
    """The type used for template inputs."""

    template_mismatch_policy: TemplateMismatchPolicy | None
    """Per-variable override of the render-time `{{field}}` mismatch policy.

    `None` means "inherit from `VariablesOptions` / `LocalVariablesOptions`"; an
    explicit value overrides the instance-level policy for this variable only,
    even when relaxing.
    """

    def __init__(
        self,
        name: str,
        *,
        type: type[T_co],
        default: T_co | ResolveFunction[T_co],
        inputs_type: type[InputsT],
        description: str | None = None,
        logfire_instance: logfire.Logfire,
        template_mismatch_policy: TemplateMismatchPolicy | None = None,
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
            template_mismatch_policy: Per-variable override of the render-time
                `{{field}}` mismatch policy. `None` (default) inherits from
                `VariablesOptions` / `LocalVariablesOptions`.
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
        self.template_mismatch_policy = template_mismatch_policy

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

        Raises:
            TemplateInputsMismatchError: When `template_mismatch_policy` resolves
                to `'error'` and the post-composition template references a
                `{{field}}` not declared in `inputs_type`.
        """
        from logfire.variables.abstract import render_serialized_string

        policy = self._effective_template_mismatch_policy()

        def _render_fn(serialized_json: str) -> str:
            if policy != 'ignore':
                self._check_template_fields(serialized_json, policy)
            return render_serialized_string(serialized_json, inputs)

        return self._get_result_and_record_span(targeting_key, attributes, label, render_fn=_render_fn)

    def _effective_template_mismatch_policy(self) -> TemplateMismatchPolicy:
        """Resolve the policy for this variable's next `get()` call.

        Per-variable wins when set (even when relaxing). Otherwise reads the
        instance-level `VariablesOptions` / `LocalVariablesOptions` setting,
        falling back to `'warn'` if no managed-variables config is in use.
        """
        if self.template_mismatch_policy is not None:
            return self.template_mismatch_policy
        from logfire._internal.config import LocalVariablesOptions, VariablesOptions

        options = self.logfire_instance.config.variables
        if isinstance(options, (VariablesOptions, LocalVariablesOptions)):
            return options.template_mismatch_policy
        return 'warn'

    def _check_template_fields(self, serialized_value: str, policy: TemplateMismatchPolicy) -> None:
        """Apply the render-time mismatch policy.

        Walks every `{{field}}` reference in the post-composition serialized
        template through `pydantic_handlebars.check_template_compatibility`
        against `inputs_type`'s JSON schema. Any error-severity issue
        triggers the policy: `'error'` raises `TemplateInputsMismatchError`,
        `'warn'` emits a `RuntimeWarning`. (`'ignore'` callers never reach
        this path.)
        """
        from pydantic_handlebars import check_template_compatibility

        from logfire.variables.template_validation import extract_template_strings

        templates = extract_template_strings(serialized_value)
        if not templates:
            return
        schema = self.get_template_inputs_schema()
        result = check_template_compatibility(templates, schema)
        error_fields = [issue.field_path for issue in result.issues if issue.severity == 'error']
        if not error_fields:
            return

        fields_str = ', '.join(repr(f) for f in dict.fromkeys(error_fields))
        message = (
            f"Variable '{self.name}': template references {fields_str} "
            f'which are not declared in inputs_type {self.inputs_type.__name__!r}.'
        )
        if policy == 'error':
            raise TemplateInputsMismatchError(message)
        # Use the filter-independent emitter: a raw `warnings.warn` here would, under
        # `-W error` / `filterwarnings=error`, escalate to a RuntimeWarning that the resolve
        # fallback `except` swallows — turning the 'warn' policy into a silent code-default
        # fallback (reason='other_error') instead of rendering-and-warning.
        _emit_resolution_warning(message)


def get_template_inputs_schema(variable: _FlagEvaluationCore[Any]) -> dict[str, Any] | None:
    """Return the template inputs JSON schema, or None for non-template variables."""
    if isinstance(variable, TemplateVariable):
        return variable.get_template_inputs_schema()
    return None


def _serialize_composed_reference(ref: ComposedReference) -> dict[str, Any]:
    """Serialize a composition reference for OTel span attributes."""
    data: dict[str, Any] = {
        'name': ref.name,
        'version': ref.version,
        'label': ref.label,
        'reason': ref.reason,
        'error': ref.error,
    }
    if ref.composed_from:
        data['composed_from'] = [_serialize_composed_reference(c) for c in ref.composed_from]
    return data


def _first_fatal_composition_error(composed: list[ComposedReference]) -> str | None:
    """Return the first *fatal* nested composition error (cycle / depth overflow), if any.

    Soft, per-reference failures (a missing/unresolvable reference, or a referenced variable
    with a malformed value) are deliberately ignored here: composition leaves the literal
    `@{ref}@` text in place for those, so the partially-composed value is still usable and
    should not trigger a wholesale fallback to the code default.
    """
    for ref in composed:
        if ref.error is not None and ref.fatal:
            return ref.error
        if nested_error := _first_fatal_composition_error(ref.composed_from):
            return nested_error
    return None


def _static_composition_refs(variable: _FlagEvaluationCore[Any]) -> set[str]:
    """Return the `@{ref}@` names in *variable*'s code default, or empty for a non-static default.

    Only inspects a static (non-callable, JSON-serializable) default — a callable default can't
    be introspected at declaration time without invoking it, which would be inappropriate here.
    """
    if is_resolve_function(variable.default):
        return set()
    try:
        serialized = variable.type_adapter.dump_json(variable.default).decode('utf-8')
    except (ValueError, TypeError, RuntimeError):
        return set()
    return set(find_references(serialized))


def warn_on_template_inputs_composition_mismatch(
    registry: Mapping[str, _FlagEvaluationCore[Any]], variable: _FlagEvaluationCore[Any]
) -> None:
    """Warn when a variable *without* `inputs_type` composes one *with* `inputs_type`.

    Composing a `template_var()` (which declares template inputs) into a plain `var()` is almost
    always a mistake: the plain variable has no inputs, so the composed template's placeholders
    can never receive values when resolved through it. This is checked at declaration time, in
    both directions, so the order in which the two variables are declared doesn't matter. Only
    static (non-callable) code defaults are inspected.
    """

    def _warn(plain_name: str, template_name: str) -> None:
        warnings.warn(
            f'Variable {plain_name!r} composes template variable {template_name!r}, but {plain_name!r} '
            f'has no inputs_type of its own, so the composed template placeholders cannot receive '
            f'inputs when {plain_name!r} is resolved. Declare {plain_name!r} with template_var() and a '
            f'compatible inputs_type if you intend to render it, or remove the reference.',
            category=RuntimeWarning,
            stacklevel=3,
        )

    if not isinstance(variable, TemplateVariable):
        # A plain variable being declared: does it compose an already-registered template var?
        for ref_name in _static_composition_refs(variable):
            if isinstance(registry.get(ref_name), TemplateVariable):
                _warn(variable.name, ref_name)
    else:
        # A template variable being declared: does an already-registered plain var compose it?
        for other in registry.values():
            if other is variable or isinstance(other, TemplateVariable):
                continue
            if variable.name in _static_composition_refs(other):
                _warn(other.name, variable.name)


@contextmanager
def targeting_context(
    targeting_key: str,
    variables: Sequence[_TargetableVariable] | None = None,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Generator[None]:
    """Set the request-local targeting key and attributes for variable resolution.

    The targeting key is used for deterministic label selection - the same targeting key
    will always resolve to the same label for a given variable configuration.

    Args:
        targeting_key: The targeting key to use for deterministic label selection
            (e.g., user ID, organization ID).
        variables: If provided, only apply this targeting key to these specific variables.
            If not provided, this becomes the default targeting key for all variables.
        attributes: Optional targeting attributes shared by all variables in this context.
            Nested contexts merge attributes, with inner values taking precedence.

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
        attributes=dict(current.attributes) if current else {},
    )

    if variables is None:
        new_data.default = targeting_key
    else:
        for var in variables:
            new_data.by_variable[var.name] = targeting_key
    if attributes is not None:
        new_data.attributes.update(attributes)

    token = _TARGETING_CONTEXT.set(new_data)
    try:
        yield
    finally:
        _TARGETING_CONTEXT.reset(token)


@contextmanager
def feature_context(
    targeting_key: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> Generator[None]:
    """Set request-local targeting for feature flags and other managed variables.

    Inside the block, feature flags use this targeting key even when a nested `targeting_context()`
    sets another default key. Managed variables use it like a `targeting_context()` default.
    Attributes supplied directly to an evaluation take precedence over values set here.

    Args:
        targeting_key: Stable identifier used for deterministic rollouts, such as a user or organization ID.
        attributes: Optional targeting attributes, such as the user's plan or region.

    Raises:
        ValueError: If `targeting_key` is empty.
    """
    if not targeting_key:
        raise ValueError('feature_context() requires a non-empty targeting key.')
    feature_token = _FEATURE_TARGETING_KEY.set(targeting_key)
    try:
        with targeting_context(targeting_key, attributes=attributes):
            yield
    finally:
        _FEATURE_TARGETING_KEY.reset(feature_token)


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


def _get_contextvar_attributes() -> Mapping[str, Any]:
    """Return request-local targeting attributes."""
    ctx = _TARGETING_CONTEXT.get()
    return ctx.attributes if ctx is not None else {}


def _get_variables_instrument(variables: Any) -> bool:
    """Get the `instrument` setting from variables config, defaulting to True."""
    from logfire._internal.config import LocalVariablesOptions, VariablesOptions

    if isinstance(variables, (VariablesOptions, LocalVariablesOptions)):
        return variables.instrument
    return True
