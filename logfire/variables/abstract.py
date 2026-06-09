from __future__ import annotations as _annotations

import json
import warnings
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

SyncMode = Literal['merge', 'replace']

if TYPE_CHECKING:
    # Pydantic is pulled in by the `[variables]` extra, not base logfire —
    # so its imports stay TYPE_CHECKING + function-local. `import logfire`
    # itself must work without pydantic installed (Pyodide regression
    # guard, exercised by `pyodide_test/test.mjs`).
    from pydantic import TypeAdapter

    import logfire
    from logfire.variables.composition import ComposedReference
    from logfire.variables.config import VariableConfig, VariablesConfig, VariableTypeConfig
    from logfire.variables.template_validation import TemplateFieldIssue
    from logfire.variables.variable import Variable

# ANSI color codes for terminal output
ANSI_RESET = '\033[0m'
ANSI_BOLD = '\033[1m'
ANSI_DIM = '\033[2m'
ANSI_RED = '\033[31m'
ANSI_GREEN = '\033[32m'
ANSI_YELLOW = '\033[33m'
ANSI_CYAN = '\033[36m'
ANSI_GRAY = '\033[90m'

__all__ = (
    'ResolvedVariable',
    'ResolutionReason',
    'SyncMode',
    'ValidationReport',
    'VariableProvider',
    'NoOpVariableProvider',
    'VariableWriteError',
    'VariableNotFoundError',
    'VariableAlreadyExistsError',
    'render_serialized_string',
)

T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)

ResolutionReason = Literal[
    'resolved',
    'context_override',
    'missing_config',
    'unrecognized_variable',
    'validation_error',
    'other_error',
    'no_provider',
    'code_default',
]
"""Why a variable (or a composed reference) resolved to its final value.

- `resolved`: provider returned a value that was used as-is.
- `context_override`: a value set via `Variable.override(...)` was used.
- `missing_config`: the variable exists on the provider but the targeting/rollout produced no value.
- `unrecognized_variable`: the provider has no entry for the variable.
- `validation_error`: the serialized value failed deserialization.
- `other_error`: composition, rendering or other error during resolution.
- `no_provider`: no provider is configured.
- `code_default`: the variable's code-default was used because the provider had no value.
"""


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
    """Details about a variable resolution including value, label, version, and any errors.

    This class can be used as a context manager. When used as a context manager, it
    automatically sets baggage with the variable name, label, and (when applicable)
    version, enabling downstream spans and logs to be associated with the variable
    resolution that was active at the time.

    Example:
        ```python skip="true"
        my_var = logfire.var(name='my_var', type=str, default='default')
        with my_var.get() as details:
            # Inside this context, baggage is set with:
            #   logfire.variables.my_var          = <label> (or '<code_default>' if no label)
            #   logfire.variables.my_var.version  = <version> (only when a versioned value was resolved)
            value = details.value
            # Any spans/logs created here will have the baggage attached.
        ```
    """

    name: str
    """The name of the variable."""
    value: T_co
    """The resolved value of the variable."""
    label: str | None = None
    """The name of the selected label, if any."""
    version: int | None = None
    """The version number of the resolved value, if any."""
    exception: Exception | None = None
    """Any exception that occurred during resolution."""
    composed_from: list[ComposedReference] = field(default_factory=list['ComposedReference'])
    """Variables that were composed into this value via @{reference}@ expansion.

    Each entry is a ComposedReference for a referenced variable, including
    its label, version, reason, and any nested composed_from entries.
    """
    reason: ResolutionReason
    """How the variable was resolved (see `ResolutionReason` for possible values)."""

    def __post_init__(self):
        self._exit_stack = ExitStack()

    def __enter__(self):
        self._exit_stack.__enter__()

        import logfire

        baggage_entries: dict[str, str] = {
            f'logfire.variables.{self.name}': self.label or '<code_default>',
        }
        # Propagate the version alongside the label so downstream spans can be
        # filtered or grouped by `(label, version)` directly. Only set when a
        # version actually resolved — code-default resolutions have version=None
        # and shouldn't add a baggage entry whose value would be misleading.
        if self.version is not None:
            baggage_entries[f'logfire.variables.{self.name}.version'] = str(self.version)
        self._exit_stack.enter_context(logfire.set_baggage(**baggage_entries))

        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any) -> None:
        self._exit_stack.__exit__(exc_type, exc_val, exc_tb)


def _inputs_to_context(inputs: Any) -> dict[str, Any]:
    """Convert template `inputs` to a context dict for Handlebars rendering.

    Accepts whatever the variable's declared `inputs_type` might be, since
    `template_var()` allows any `TypeAdapter`-supported type: a Pydantic `BaseModel`
    (via `model_dump()`), a `dict`/`Mapping`, a dataclass, a `TypedDict` instance, an
    attrs class, etc. Anything that isn't already a model or mapping is run through
    pydantic's general `to_jsonable_python` serialization, mirroring how the value's
    own `template_inputs_schema` is derived. `None` yields an empty context.

    Args:
        inputs: Template context values.

    Returns:
        A dict suitable for use as a Handlebars template context.

    Raises:
        TypeError: If inputs can't be serialized to a mapping context.
    """
    if inputs is None:
        return {}
    if hasattr(inputs, 'model_dump'):
        return inputs.model_dump()
    if isinstance(inputs, Mapping):
        return dict(inputs)  # pyright: ignore[reportUnknownArgumentType]

    # Fall back to pydantic's general serialization so dataclasses / TypedDict instances /
    # attrs classes / etc. work as inputs (matching the arbitrary `inputs_type` the SDK allows).
    from pydantic_core import to_jsonable_python

    try:
        dumped = to_jsonable_python(inputs)
    except Exception as e:
        raise TypeError(
            f'Could not serialize render inputs of type {type(inputs).__name__!r} to a template '
            'context; pass a Pydantic model, dataclass, TypedDict, dict/Mapping, or another '
            'pydantic-serializable object.'
        ) from e
    if isinstance(dumped, dict):
        return cast('dict[str, Any]', dumped)
    raise TypeError(
        f'Render inputs of type {type(inputs).__name__!r} serialized to {type(dumped).__name__!r}, '
        'but a mapping is required for a template context.'
    )


def render_serialized_string(serialized_json: str, inputs: Any) -> str:
    """Render Handlebars templates in a serialized JSON string.

    Decodes the JSON, renders all string values containing `{{placeholders}}`
    using the provided inputs, then re-encodes to JSON.

    Args:
        serialized_json: A JSON-encoded string potentially containing Handlebars templates.
        inputs: Template context values. Can be a Pydantic `BaseModel`, `dict`,
            `Mapping`, or `None`.

    Returns:
        The rendered JSON string.
    """
    context = _inputs_to_context(inputs)

    # Wrap all string values in SafeString to disable HTML escaping.
    # For prompt/config templates (not HTML), escaping is undesirable.
    context = _wrap_safe_context(context)

    # Decode the serialized JSON, render string values, then re-encode.
    # We can't render the raw JSON directly because substituted values
    # might contain JSON-special characters (e.g., double quotes) that
    # would make the resulting JSON invalid.
    decoded = json.loads(serialized_json)
    rendered_value = _render_json_value(decoded, context)
    return json.dumps(rendered_value)


def _wrap_safe_context(context: dict[str, Any]) -> dict[str, Any]:
    """Recursively wrap all string values in SafeString to disable HTML escaping."""
    return {k: _wrap_safe_value(v) for k, v in context.items()}


def _wrap_safe_value(value: Any) -> Any:
    """Wrap a single value: strings become SafeString, dicts/lists are recursed."""
    from pydantic_handlebars import SafeString

    if isinstance(value, str):
        return SafeString(value)
    if isinstance(value, dict):
        return _wrap_safe_context(value)  # pyright: ignore[reportUnknownArgumentType]
    if isinstance(value, list):
        return [_wrap_safe_value(item) for item in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def _render_json_value(value: Any, context: dict[str, Any]) -> Any:
    """Recursively render Handlebars templates in a decoded JSON value.

    Only string values are rendered; dicts and lists are walked recursively.
    *compile_template* is the LRU-cached compile helper from
    `_handlebars.compile_runtime_template` — passing it in (rather than
    importing here) keeps the recursion cheap and makes the cache hit on
    repeated identical sources.
    """
    from logfire.variables._handlebars import compile_runtime_template

    if isinstance(value, str):
        if '{{' not in value:
            return value
        return compile_runtime_template(value).render(context)
    if isinstance(value, dict):
        return {k: _render_json_value(v, context) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_render_json_value(item, context) for item in value]  # pyright: ignore[reportUnknownVariableType]
    # Numbers, booleans, None pass through unchanged
    return value


# --- Dataclasses for push/validate operations ---


@dataclass
class LabelCompatibility:
    """Result of checking a label value's compatibility with a schema."""

    label: str
    serialized_value: str
    is_compatible: bool
    error: str | None = None


@dataclass
class VariableChange:
    """Represents a change to be made to a variable."""

    name: str
    change_type: str  # 'create', 'update_schema', 'update_description', 'no_change'
    local_schema: dict[str, Any] | None = None
    server_schema: dict[str, Any] | None = None
    initial_value: str | None = None  # JSON serialized
    incompatible_labels: list[LabelCompatibility] | None = None
    server_id: str | None = None  # For updates
    local_description: str | None = None
    server_description: str | None = None
    description_differs: bool = False  # True if descriptions differ (for warning)
    template_inputs_schema: dict[str, Any] | None = None  # JSON Schema for template inputs
    value_schema_changed: bool = False  # True if the value's JSON schema changed (for 'update_schema')
    inputs_schema_changed: bool = False  # True if the template-inputs schema changed (for 'update_schema')


@dataclass
class VariableDiff:
    """Represents the diff between local and server variables."""

    changes: list[VariableChange]
    orphaned_server_variables: list[str]  # Variables on server not in local code
    reference_errors: list[str] = field(default_factory=list[str])
    """All reference problems (non-existent refs *and* cycles)."""
    reference_cycles: list[str] = field(default_factory=list[str])
    """The subset of `reference_errors` that are cycles.

    Cycles are unconditionally unresolvable (no environment can satisfy `A -> B -> A`), so a
    push blocks on them even in non-strict mode — unlike a missing reference, which may
    legitimately resolve in another codebase/environment and is only a warning in non-strict.
    """
    template_field_issues: list[TemplateFieldIssue] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    """Template `{{field}}` references that don't match a TemplateVariable's declared `inputs_type`.

    Covers both locally-declared code defaults and server-stored label values
    (so a server template authored against an older schema flags a mismatch
    against the local `inputs_type`). Composition `@{ref}@` chains are
    followed; an incompatible reference in a chained-in variable shows the
    composition path that led to it.
    """

    @property
    def has_changes(self) -> bool:
        """Return True if there are any changes to apply."""
        return any(c.change_type != 'no_change' for c in self.changes)


@dataclass
class LabelValidationError:
    """Represents a validation error for a specific label value."""

    variable_name: str
    label: str | None
    error: Exception


@dataclass
class DescriptionDifference:
    """Represents a description difference between local and server."""

    variable_name: str
    local_description: str | None
    server_description: str | None


@dataclass
class ValidationReport:
    """Report of variable validation results.

    This class contains the results of validating variable definitions against
    a provider's configuration. It can be used to check for errors programmatically
    or formatted for human-readable output.

    Example:
        ```python skip="true"
        report = provider.validate_variables(variables)
        if not report.is_valid:
            print(report.format())
            sys.exit(1)
        ```
    """

    errors: list[LabelValidationError]
    """List of validation errors found."""
    variables_checked: int
    """Total number of variables that were checked."""
    variables_not_on_server: list[str]
    """Names of variables that exist locally but not on the server."""
    description_differences: list[DescriptionDifference]
    """List of variables where local and server descriptions differ."""
    reference_errors: list[str] = field(default_factory=list[str])
    """Errors found while checking `@{variable}@` references (missing refs *and* cycles)."""
    reference_cycles: list[str] = field(default_factory=list[str])
    """The subset of `reference_errors` that are cycles (always-fatal, vs. possibly-resolvable missing refs)."""
    template_field_issues: list[TemplateFieldIssue] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    """Template `{{field}}` references that don't match a TemplateVariable's declared `inputs_type`."""

    @property
    def has_errors(self) -> bool:
        """Return True if there are any validation errors."""
        return not self.is_valid

    @property
    def is_valid(self) -> bool:
        """Return False if there are validation errors, missing variables, or reference errors."""
        return (
            len(self.errors) == 0
            and len(self.variables_not_on_server) == 0
            and len(self.reference_errors) == 0
            and len(self.template_field_issues) == 0
        )

    def format(self, *, colors: bool = True) -> str:
        """Format the validation report for human-readable output.

        Args:
            colors: If True, include ANSI color codes in output.

        Returns:
            A formatted string representation of the report.
        """
        reset = ANSI_RESET if colors else ''
        red = ANSI_RED if colors else ''
        green = ANSI_GREEN if colors else ''
        yellow = ANSI_YELLOW if colors else ''
        cyan = ANSI_CYAN if colors else ''

        lines: list[str] = []

        if self.errors:
            lines.append(f'\n{red}=== Validation Errors ==={reset}')
            for error in self.errors:
                if error.label is None:  # pragma: no cover
                    lines.append(f'  {red}✗ {error.variable_name}: {error.error}{reset}')
                else:
                    lines.append(f'  {red}✗ {error.variable_name} (label: {error.label}){reset}')
                    # Format the error message, indenting each line
                    error_lines = str(error.error).split('\n')
                    for line in error_lines[:5]:  # Limit to first 5 lines
                        lines.append(f'      {line}')
                    if len(error_lines) > 5:
                        lines.append(f'      ... ({len(error_lines) - 5} more lines)')

        if self.variables_not_on_server:
            lines.append(f'\n{yellow}=== Variables Not Found on Server ==={reset}')
            for name in self.variables_not_on_server:
                lines.append(f'  {yellow}? {name}{reset}')

        variables_with_errors = len({e.variable_name for e in self.errors})
        valid_count = self.variables_checked - variables_with_errors - len(self.variables_not_on_server)
        # Only advertise "Valid" when the report as a whole is valid. Otherwise
        # a partial pass (per-variable type checks succeeded but reference /
        # template-field errors exist) emits the contradictory pair
        # "=== Valid (N variables) ===" + "=== Reference errors ===".
        if valid_count > 0 and self.is_valid:
            lines.append(f'\n{green}=== Valid ({valid_count} variables) ==={reset}')

        # Show description differences as informational warnings
        if self.description_differences:
            lines.append(f'\n{cyan}=== Description differences (informational) ==={reset}')
            lines.append(f'{cyan}Note: Different descriptions may be intentional for different codebases.{reset}')
            for diff in self.description_differences:
                lines.append(f'  {cyan}! {diff.variable_name}{reset}')
                local_desc = diff.local_description or '(none)'
                server_desc = diff.server_description or '(none)'
                lines.append(f'    Local:  {local_desc}')
                lines.append(f'    Server: {server_desc}')

        # Show reference errors
        if self.reference_errors:
            lines.append(f'\n{red}=== Reference errors ==={reset}')
            for error in self.reference_errors:
                lines.append(f'  {red}✗ {error}{reset}')

        # Show template-field issues
        if self.template_field_issues:
            lines.append(f'\n{red}=== Template field issues ==={reset}')
            for issue in self.template_field_issues:
                lines.append(f'  {red}✗ {_describe_template_field_issue(issue)}{reset}')

        # Summary line
        if not self.is_valid:
            issue_count = (
                variables_with_errors
                + len(self.variables_not_on_server)
                + len(self.reference_errors)
                + len(self.template_field_issues)
            )
            lines.append(f'\n{red}Validation failed: {issue_count} issue(s) found.{reset}')
        else:
            lines.append(f'\n{green}Validation passed: All {self.variables_checked} variable(s) are valid.{reset}')

        return '\n'.join(lines)


# --- Helper functions for push/validate operations ---


def _get_json_schema(variable: Variable[object]) -> dict[str, Any]:
    """Get the JSON schema for a variable's type."""
    return variable.type_adapter.json_schema()


def _get_default_serialized(variable: Variable[object]) -> str | None:
    """Get the serialized default value for a variable.

    Returns None if the default is a ResolveFunction (can't serialize a function).
    """
    from logfire.variables.variable import is_resolve_function

    if is_resolve_function(variable.default):
        return None
    # Serialize the default value using Pydantic
    return variable.type_adapter.dump_json(variable.default).decode('utf-8')


def _check_label_compatibility(
    variable: Variable[object],
    label: str,
    serialized_value: str,
) -> LabelCompatibility:
    """Check if a label's value is compatible with the variable's type."""
    from pydantic import ValidationError

    try:
        variable.type_adapter.validate_json(serialized_value)
        return LabelCompatibility(
            label=label,
            serialized_value=serialized_value,
            is_compatible=True,
        )
    except ValidationError as e:
        return LabelCompatibility(
            label=label,
            serialized_value=serialized_value,
            is_compatible=False,
            error=str(e),
        )


def _check_all_label_compatibility(
    variable: Variable[object],
    server_var: VariableConfig,
) -> list[LabelCompatibility]:
    """Check all labeled values and latest_version against the variable's Python type.

    Returns a list of incompatible labels (empty if all are compatible).
    """
    from logfire.variables.config import LabeledValue

    incompatible: list[LabelCompatibility] = []
    for label, labeled_value in server_var.labels.items():
        if isinstance(labeled_value, LabeledValue):
            compat = _check_label_compatibility(
                variable,
                label,
                labeled_value.serialized_value,
            )
            if not compat.is_compatible:
                incompatible.append(compat)
    # Also check latest version
    if server_var.latest_version is not None:
        compat = _check_label_compatibility(
            variable,
            'latest',
            server_var.latest_version.serialized_value,
        )
        if not compat.is_compatible:
            incompatible.append(compat)
    return incompatible


def _check_type_label_compatibility(
    adapter: TypeAdapter[Any],
    server_var: VariableConfig,
) -> list[LabelCompatibility]:
    """Check all labeled values and latest_version against a TypeAdapter.

    Similar to _check_all_label_compatibility but works with a TypeAdapter
    instead of a Variable instance, for use with push_variable_types.

    Returns a list of incompatible labels (empty if all are compatible).
    """
    from pydantic import ValidationError

    from logfire.variables.config import LabeledValue

    incompatible: list[LabelCompatibility] = []
    for label, labeled_value in server_var.labels.items():
        if isinstance(labeled_value, LabeledValue):
            try:
                adapter.validate_json(labeled_value.serialized_value)
            except ValidationError as e:
                incompatible.append(
                    LabelCompatibility(
                        label=label,
                        serialized_value=labeled_value.serialized_value,
                        is_compatible=False,
                        error=str(e),
                    )
                )
    # Also check latest version
    if server_var.latest_version is not None:
        try:
            adapter.validate_json(server_var.latest_version.serialized_value)
        except ValidationError as e:
            incompatible.append(
                LabelCompatibility(
                    label='latest',
                    serialized_value=server_var.latest_version.serialized_value,
                    is_compatible=False,
                    error=str(e),
                )
            )
    return incompatible


def _describe_template_field_issue(issue: TemplateFieldIssue) -> str:
    """Render a `TemplateFieldIssue` as a single human-readable line.

    Names the *validated* template variable (`root_variable`) whose `inputs_type` schema the
    field was checked against, and — when the field lives in a different, composed fragment —
    where it was actually found and the `@{ref}@` chain that reached it. This keeps the
    attribution unambiguous: a shared fragment can be valid on its own yet incompatible with a
    particular root that composes it.
    """
    # An empty reference_path means the field is in the root variable's own value (a non-empty
    # path is only ever built by following `@{ref}@`s away from the root), so it's the
    # direct-vs-composed discriminator.
    if not issue.reference_path:
        where = ''
    else:
        location = issue.found_in_variable
        if issue.found_in_label is not None:
            location += f' (label: {issue.found_in_label})'
        chain = ' via ' + ' -> '.join(f'@{{{ref}}}@' for ref in issue.reference_path)
        where = f' found in {location}{chain}'
    return (
        f'{issue.root_variable}: {{{{{issue.field_name}}}}}{where} '
        f"is not declared in {issue.root_variable}'s inputs_type schema"
    )


def _collect_template_field_issues(
    variables: Sequence[Variable[object]],
    server_config: VariablesConfig,
) -> list[TemplateFieldIssue]:
    """Validate `{{field}}` references in every TemplateVariable against its declared schema.

    For each `TemplateVariable`, walks the composition graph and checks
    every template string — in the local code default, in any server-stored
    label value, and in any referenced variable's values — against the
    variable's `inputs_type` JSON schema. Mismatches are returned as
    `TemplateFieldIssue` entries.

    Covers both push-time goals D and E in #1950: D wires the existing
    composition-aware validator into the sync path; E surfaces the case
    where a server-stored template was authored against an older schema
    that's incompatible with the current local `inputs_type`.

    """
    from logfire.variables.template_validation import validate_template_composition
    from logfire.variables.variable import TemplateVariable, is_resolve_function

    issues: list[TemplateFieldIssue] = []
    locals_by_name = {v.name: v for v in variables}

    def get_all_serialized_values(name: str) -> dict[str | None, str]:
        """Return ``{label_or_None: serialized_json}`` for every value *name* can serve.

        Each server label is resolved through its ref chain (`follow_ref`), so `LabelRef`
        labels — including refs to the reserved ``latest`` / ``code_default`` targets — are
        followed and keyed by the label's own name. That way a template issue is reported
        against the label that actually serves the offending value. The latest version is
        keyed ``'latest'``, and the local code default is keyed ``None`` ("the value served
        when the rollout routes to ``code_default`` or selects no label").

        The code default is always included when present, independent of any server value:
        the runtime can serve it even when a ``latest_version`` exists (empty rollout /
        100%-code-default), so it must be validated too. ``'latest'`` and ``None`` can't
        collide with a server label — ``latest`` is a reserved label name (see `LabelRef`)
        and ``None`` is not a string.
        """
        result: dict[str | None, str] = {}
        server_var = server_config.variables.get(name)
        if server_var is not None:
            for label, labeled in server_var.labels.items():
                serialized, _ = server_var.follow_ref(labeled)
                if serialized is not None:
                    result[label] = serialized
            if server_var.latest_version is not None:
                result.setdefault('latest', server_var.latest_version.serialized_value)
        local_var = locals_by_name.get(name)
        if local_var is not None and not is_resolve_function(local_var.default):
            try:
                result[None] = local_var.type_adapter.dump_json(local_var.default).decode('utf-8')
            except Exception:  # pragma: no cover
                # Defensive: a registered variable's default normally serializes against its own
                # type adapter. If it somehow doesn't, skip validating it rather than crash the push.
                pass
        return result

    # `validate_template_composition` already dedups within each root's walk, and every issue it
    # returns carries that root's name, so issues from different roots are inherently distinct.
    # No cross-root dedup is applied: a shared fragment incompatible with several roots is a
    # separate problem for each root and is reported once per affected root (deliberately *not*
    # collapsed into one line, which would hide which template variable(s) are actually broken).
    for variable in variables:
        if not isinstance(variable, TemplateVariable):
            continue
        schema = variable.get_template_inputs_schema()
        result = validate_template_composition(variable.name, schema, get_all_serialized_values)
        issues.extend(result.issues)

    return issues


def _check_reference_errors(
    variables: Sequence[Variable[object]],
    server_config: VariablesConfig,
) -> tuple[list[str], list[str]]:
    """Check for reference errors: non-existent refs and cycles.

    Returns ``(all_errors, cycles)`` where ``all_errors`` lists every problem (missing
    references followed by cycles) and ``cycles`` is the cycle subset. Callers block on
    cycles unconditionally but treat missing references as non-strict warnings.

    Walks the full composition graph starting from each locally-registered
    variable, transitively following `@{ref}@` edges into server-only
    variables — so a missing reference reachable only through a chain that
    passes through a server-only node still surfaces, as does a cycle whose
    midpoints are server-only.

    `VariablesConfig` is treated as self-contained for substitution: any
    `@{name}@` whose `name` isn't in either the local registration set or
    `server_config` is reported as a non-existent reference, the same way
    a registration miss is.
    """
    from logfire.variables.composition import find_references_and_errors
    from logfire.variables.config import LabeledValue
    from logfire.variables.variable import is_resolve_function

    warnings_list: list[str] = []

    all_names: set[str] = {v.name for v in variables} | set(server_config.variables.keys())
    locals_by_name = {v.name: v for v in variables}

    def _refs_of(name: str) -> set[str]:
        """Collect refs from every serialized value reachable for *name*.

        That's the local code default (if registered locally) plus every
        labeled server value plus the `latest_version`. A malformed `@{...}@`
        value is recorded as a reference error (rather than crashing the walk),
        and a local default that can't be serialized is skipped — we want the
        walker to keep going either way.
        """
        refs: set[str] = set()

        def _record(serialized: str) -> None:
            found, errors = find_references_and_errors(serialized)
            refs.update(found)
            for err in errors:
                warnings_list.append(f"Variable '{name}': {err}")

        local = locals_by_name.get(name)
        if local is not None and not is_resolve_function(local.default):
            try:
                serialized_default = local.type_adapter.dump_json(local.default).decode('utf-8')
            except (ValueError, TypeError, RuntimeError):
                # Only the local default's *serialization* can fail here; reference parsing is
                # handled (and never raises) inside `_record`. Skip an unserializable default and
                # keep walking the rest of the graph.
                serialized_default = None
            if serialized_default is not None:
                _record(serialized_default)
        server_var = server_config.variables.get(name)
        if server_var is not None:
            for labeled in server_var.labels.values():
                if isinstance(labeled, LabeledValue):
                    _record(labeled.serialized_value)
            if server_var.latest_version is not None:
                _record(server_var.latest_version.serialized_value)
        return refs

    # BFS the composition graph from every local variable in declaration
    # order. Each node we visit contributes its outgoing edges to
    # `ref_graph` and, if any point at an unknown name, a
    # non-existent-reference warning. Visited names are gated on `seen` so
    # a shared sub-tree is walked once.
    ref_graph: dict[str, set[str]] = {}
    seen: set[str] = set()
    frontier: deque[str] = deque(v.name for v in variables)
    while frontier:
        current = frontier.popleft()
        if current in seen:
            continue
        seen.add(current)
        refs = _refs_of(current)
        if refs:
            ref_graph[current] = refs
        for ref in refs:
            if ref not in all_names:
                warnings_list.append(f"Variable '{current}' references '@{{{ref}}}@' which does not exist.")
            elif ref not in seen:
                frontier.append(ref)

    # Cycle detection on the assembled graph. Because the graph includes
    # nodes reached transitively through server-only variables, cycles
    # whose midpoints are server-only are now caught too.
    def _detect_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        in_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> None:
            if node in in_stack:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            in_stack.add(node)
            path.append(node)
            for neighbor in graph.get(node, set()):
                dfs(neighbor)
            path.pop()
            in_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)
        return cycles

    cycle_messages: list[str] = []
    try:
        cycles = _detect_cycles(ref_graph)
    except RecursionError:
        # The reference graph comes from arbitrary server config and can exceed Python's recursion
        # limit; surface a clean, blocking error instead of crashing with a RecursionError.
        cycles = []
        message = (
            'Reference graph is too deeply nested to validate for cycles; '
            'check for an extremely long or circular @{ref}@ chain.'
        )
        warnings_list.append(message)
        cycle_messages.append(message)
    for cycle in cycles:
        cycle_str = ' -> '.join(cycle)
        message = f'Reference cycle detected: {cycle_str}'
        warnings_list.append(message)
        cycle_messages.append(message)

    return warnings_list, cycle_messages


def _compute_diff(
    variables: Sequence[Variable[object]],
    server_config: VariablesConfig,
) -> VariableDiff:
    """Compute the diff between local variables and server config.

    Args:
        variables: Local variable definitions.
        server_config: Server variable configurations (from provider.get_all_variables_config()).

    Returns:
        A VariableDiff describing the changes needed.
    """
    changes: list[VariableChange] = []
    local_names = {v.name for v in variables}

    for variable in variables:
        local_schema = _get_json_schema(variable)
        local_description = variable.description
        server_var = server_config.variables.get(variable.name)

        from logfire.variables.variable import get_template_inputs_schema

        template_inputs_schema = get_template_inputs_schema(variable)

        if server_var is None:
            # New variable - needs to be created
            default_serialized = _get_default_serialized(variable)
            changes.append(
                VariableChange(
                    name=variable.name,
                    change_type='create',
                    local_schema=local_schema,
                    initial_value=default_serialized,
                    local_description=local_description,
                    template_inputs_schema=template_inputs_schema,
                )
            )
        else:
            # Variable exists - check if schema changed
            server_schema = server_var.json_schema
            server_description = server_var.description

            # Normalize schemas for comparison (remove $defs if empty, etc.)
            local_normalized = json.dumps(local_schema, sort_keys=True)
            server_normalized = json.dumps(server_schema, sort_keys=True) if server_schema else '{}'

            schema_changed = local_normalized != server_normalized
            local_template_inputs_normalized = json.dumps(template_inputs_schema, sort_keys=True)
            server_template_inputs_normalized = json.dumps(server_var.template_inputs_schema, sort_keys=True)
            template_inputs_schema_changed = local_template_inputs_normalized != server_template_inputs_normalized

            # Check if description differs (for warning purposes)
            # Normalize: treat None and empty string as equivalent
            local_desc_normalized = local_description or None
            server_desc_normalized = server_description or None
            description_differs = local_desc_normalized != server_desc_normalized

            if schema_changed or template_inputs_schema_changed:
                # Schema changed - check label value compatibility
                incompatible = _check_all_label_compatibility(variable, server_var)

                changes.append(
                    VariableChange(
                        name=variable.name,
                        change_type='update_schema',
                        local_schema=local_schema,
                        server_schema=server_schema,
                        incompatible_labels=incompatible if incompatible else None,
                        local_description=local_description,
                        server_description=server_description,
                        description_differs=description_differs,
                        template_inputs_schema=template_inputs_schema,
                        value_schema_changed=schema_changed,
                        inputs_schema_changed=template_inputs_schema_changed,
                    )
                )
            else:
                # No schema change needed - still check label value compatibility
                incompatible = _check_all_label_compatibility(variable, server_var)

                changes.append(
                    VariableChange(
                        name=variable.name,
                        change_type='no_change',
                        incompatible_labels=incompatible if incompatible else None,
                        local_description=local_description,
                        server_description=server_description,
                        description_differs=description_differs,
                    )
                )

    # Find orphaned server variables (on server but not in local code)
    orphaned = [name for name in server_config.variables.keys() if name not in local_names]

    # Check for reference errors (non-existent refs, cycles)
    reference_errors, reference_cycles = _check_reference_errors(variables, server_config)

    # Check template variables' `{{field}}` references against their declared
    # `inputs_type` JSON schemas (D + E in #1950): catches both local code
    # defaults with mismatched fields and server-stored templates authored
    # against an older schema.
    template_field_issues = _collect_template_field_issues(variables, server_config)

    return VariableDiff(
        changes=changes,
        orphaned_server_variables=orphaned,
        reference_errors=reference_errors,
        reference_cycles=reference_cycles,
        template_field_issues=template_field_issues,
    )


def _format_diff(diff: VariableDiff) -> str:
    """Format the diff for display to the user."""
    lines: list[str] = []

    creates = [c for c in diff.changes if c.change_type == 'create']
    updates = [c for c in diff.changes if c.change_type == 'update_schema']
    unchanged = [c for c in diff.changes if c.change_type == 'no_change']
    description_diffs = [c for c in diff.changes if c.description_differs]

    if creates:
        lines.append(f'\n{ANSI_GREEN}=== Variables to CREATE ==={ANSI_RESET}')
        for change in creates:
            lines.append(f'  {ANSI_GREEN}+ {change.name}{ANSI_RESET}')
            if change.local_description:
                lines.append(f'    Description: {change.local_description}')
            if change.initial_value:
                lines.append(f'    Example value: {change.initial_value}')
            else:
                lines.append('    (No example value - default is a function)')

    if updates:
        lines.append(f'\n{ANSI_YELLOW}=== Variables to UPDATE (schema changed) ==={ANSI_RESET}')
        for change in updates:
            # Distinguish what actually changed: the value's JSON schema, the template-inputs
            # schema, or both — so a template-inputs-only change doesn't read as "(schema changed)"
            # for the value type.
            if change.value_schema_changed and change.inputs_schema_changed:
                detail = ' (value + template inputs schema)'
            elif change.inputs_schema_changed:
                detail = ' (template inputs schema)'
            elif change.value_schema_changed:
                detail = ' (value schema)'
            else:
                detail = ''
            lines.append(f'  {ANSI_YELLOW}~ {change.name}{detail}{ANSI_RESET}')
            if change.incompatible_labels:
                lines.append(f'    {ANSI_RED}Warning: Incompatible label values:{ANSI_RESET}')
                for compat in change.incompatible_labels:
                    lines.append(f'      - {compat.label}: {compat.error}')

    if unchanged:
        lines.append(f'\n{ANSI_GRAY}=== No changes needed ({len(unchanged)} variables) ==={ANSI_RESET}')
        for change in unchanged:
            lines.append(f'  {ANSI_GRAY}  {change.name}{ANSI_RESET}')

    # Show validation warnings for unchanged variables with incompatible label values
    unchanged_with_incompatible = [c for c in unchanged if c.incompatible_labels]
    if unchanged_with_incompatible:
        lines.append(f'\n{ANSI_YELLOW}=== Validation warnings (schema unchanged) ==={ANSI_RESET}')
        for change in unchanged_with_incompatible:
            lines.append(f'  {ANSI_YELLOW}\u26a0 {change.name}{ANSI_RESET}')
            lines.append(f'    {ANSI_RED}Incompatible label values:{ANSI_RESET}')
            for compat in change.incompatible_labels:  # type: ignore[union-attr]
                lines.append(f'      - {compat.label}: {compat.error}')

    if diff.orphaned_server_variables:
        lines.append(f'\n{ANSI_GRAY}=== Server-only variables (not in local code) ==={ANSI_RESET}')
        for name in diff.orphaned_server_variables:
            lines.append(f'  {ANSI_GRAY}? {name}{ANSI_RESET}')

    # Show description differences as informational warnings
    if description_diffs:
        lines.append(f'\n{ANSI_CYAN}=== Description differences (informational) ==={ANSI_RESET}')
        lines.append(f'{ANSI_CYAN}Note: Different descriptions may be intentional for different codebases.{ANSI_RESET}')
        for change in description_diffs:
            lines.append(f'  {ANSI_CYAN}! {change.name}{ANSI_RESET}')
            local_desc = change.local_description or '(none)'
            server_desc = change.server_description or '(none)'
            lines.append(f'    Local:  {local_desc}')
            lines.append(f'    Server: {server_desc}')

    # Show reference problems. Cycles always block the push, so they're rendered as red
    # errors (matching `ValidationReport.format`); missing references are non-blocking in
    # non-strict mode, so they're rendered as yellow warnings.
    cycle_set = set(diff.reference_cycles)
    reference_warnings = [e for e in diff.reference_errors if e not in cycle_set]
    if reference_warnings:
        lines.append(f'\n{ANSI_YELLOW}=== Reference errors ==={ANSI_RESET}')
        for warning in reference_warnings:
            lines.append(f'  {ANSI_YELLOW}⚠ {warning}{ANSI_RESET}')
    if diff.reference_cycles:
        lines.append(f'\n{ANSI_RED}=== Reference cycles (block the push) ==={ANSI_RESET}')
        for cycle in diff.reference_cycles:
            lines.append(f'  {ANSI_RED}✗ {cycle}{ANSI_RESET}')

    # Show template-field issues: {{field}} references that don't match the
    # template variable's declared inputs schema.
    if diff.template_field_issues:
        lines.append(f'\n{ANSI_YELLOW}=== Template field issues ==={ANSI_RESET}')
        for issue in diff.template_field_issues:
            lines.append(f'  {ANSI_YELLOW}⚠ {_describe_template_field_issue(issue)}{ANSI_RESET}')

    return '\n'.join(lines)


def _apply_changes(
    provider: VariableProvider,
    diff: VariableDiff,
    server_config: VariablesConfig,
) -> None:
    """Apply the changes using the provider."""
    for change in diff.changes:
        if change.change_type == 'create':
            _create_variable(provider, change)
        elif change.change_type == 'update_schema':  # pragma: no branch
            _update_variable_schema(provider, change, server_config)


def _create_variable(
    provider: VariableProvider,
    change: VariableChange,
) -> None:
    """Create a new variable via the provider."""
    from logfire.variables.config import Rollout, VariableConfig

    # No labels or versions are created - the code default is used when none exist
    # The example field stores the serialized default for use as a template in the UI
    config = VariableConfig(
        name=change.name,
        description=change.local_description,
        labels={},
        rollout=Rollout(labels={}),
        overrides=[],
        json_schema=change.local_schema,
        example=change.initial_value,  # Store the code default as an example for the UI
        template_inputs_schema=change.template_inputs_schema,
    )

    provider.create_variable(config)
    print(f'  {ANSI_GREEN}Created: {change.name}{ANSI_RESET}')


def _update_variable_schema(
    provider: VariableProvider,
    change: VariableChange,
    server_config: VariablesConfig,
) -> None:
    """Update an existing variable's schema via the provider."""
    from logfire.variables.config import VariableConfig

    # Get the existing config to preserve labels, rollout, overrides
    existing = server_config.variables.get(change.name)
    if existing is None:  # pragma: no cover
        # Should not happen, but handle gracefully
        print(f'  {ANSI_RED}Warning: Could not find existing config for {change.name}{ANSI_RESET}')
        return

    # Create updated config with new schema but preserve everything else
    config = VariableConfig(
        name=existing.name,
        description=existing.description,
        labels=existing.labels,
        rollout=existing.rollout,
        overrides=existing.overrides,
        json_schema=change.local_schema,
        template_inputs_schema=change.template_inputs_schema,
    )

    provider.update_variable(change.name, config)
    print(f'  {ANSI_YELLOW}Updated schema: {change.name}{ANSI_RESET}')


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
            targeting_key: Optional key for deterministic label selection (e.g., user ID).
            attributes: Optional attributes for condition-based targeting rules.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).
        """
        raise NotImplementedError  # pragma: no cover

    def get_serialized_value_for_label(
        self,
        variable_name: str,
        label: str,
    ) -> ResolvedVariable[str | None]:
        """Retrieve the serialized value for a specific label of a variable.

        This method bypasses rollout weights and targeting, directly selecting the
        specified label. Used for explicit label selection.

        Args:
            variable_name: The name of the variable to resolve.
            label: The name of the label to select.

        Returns:
            A ResolvedVariable containing the serialized value (or None if not found).

        Note:
            The default implementation uses get_variable_config to look up the label.
            Subclasses may override this for more efficient implementations.
        """
        config = self.get_variable_config(variable_name)
        if config is None:
            return ResolvedVariable(name=variable_name, value=None, reason='unrecognized_variable')

        labeled_value = config.labels.get(label)
        if labeled_value is None:
            # The variable exists but this label doesn't. `reason='resolved'` with value=None was
            # misleading (resolved implies a usable value); report missing_config instead.
            return ResolvedVariable(name=variable_name, value=None, reason='missing_config')

        serialized, version = config.follow_ref(labeled_value)
        return ResolvedVariable(
            name=variable_name,
            value=serialized,
            label=label,
            version=version,
            # A ref that resolves to nothing (e.g. a `code_default` ref the server can't supply) is
            # not a successful resolution — surface missing_config so callers/baggage aren't told a
            # value was used when it wasn't.
            reason='resolved' if serialized is not None else 'missing_config',
        )

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

    def shutdown(self, timeout_millis: float = 5000):
        """Clean up any resources used by the provider.

        Args:
            timeout_millis: The timeout budget in milliseconds for shutdown operations.
        """
        pass

    def start(self, logfire_instance: logfire.Logfire | None) -> None:
        """Start any background tasks for this provider.

        This is called after the provider is created and the Logfire instance is available.
        Providers that need to run background tasks (like polling) should override this method
        to start those tasks, using the provided logfire instance for error logging.

        Args:
            logfire_instance: The Logfire instance to use for error logging, or None if
                variable instrumentation is disabled.
        """
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
        return None  # pragma: no cover

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

    def push_config(  # pragma: no cover
        self,
        config: VariablesConfig,
        *,
        mode: SyncMode = 'merge',
        dry_run: bool = False,
        yes: bool = False,
    ) -> bool:
        """Push a VariablesConfig to this provider.

        This method pushes a VariablesConfig (including labels and rollouts) to the
        provider. For remote providers, version records are created from label
        entries with inline serialized values; `latest_version` is pull/read state
        derived by the server and is not pushed directly. It's useful for:
        - Pushing configs generated or modified locally
        - Pushing configs read from files
        - Partial updates (merge mode) or full replacement (replace mode)

        Args:
            config: The VariablesConfig to push.
            mode: 'merge' updates/creates only variables in config (leaves others unchanged).
                  'replace' makes the server match the config exactly (deletes missing variables).
            dry_run: If True, only show what would change without applying.
            yes: If True, skip confirmation prompt.

        Returns:
            True if changes were applied (or would be applied in dry_run mode), False otherwise.
        """
        if not config.variables:
            print('No variables in config to push.')
            return False

        # Refresh the provider to ensure we have the latest config
        try:
            self.refresh(force=True)
        except Exception as e:
            print(f'{ANSI_YELLOW}Warning: Could not refresh provider: {e}{ANSI_RESET}')

        # Get current variable configs from provider
        try:
            server_config = self.get_all_variables_config()
        except Exception as e:
            print(f'{ANSI_RED}Error fetching current config: {e}{ANSI_RESET}')
            return False

        # Compute changes
        creates: list[str] = []
        updates: list[str] = []
        deletes: list[str] = []
        unchanged: list[str] = []

        for name, var_config in config.variables.items():
            server_var = server_config.variables.get(name)
            if server_var is None:
                creates.append(name)
            elif var_config.model_dump(exclude={'latest_version'}) != server_var.model_dump(exclude={'latest_version'}):
                updates.append(name)
            else:
                unchanged.append(name)

        # In replace mode, variables on server but not in config should be deleted
        if mode == 'replace':
            for name in server_config.variables:
                if name not in config.variables:
                    deletes.append(name)

        # Show diff
        lines: list[str] = []

        if creates:
            lines.append(f'\n{ANSI_GREEN}=== Variables to CREATE ==={ANSI_RESET}')
            for name in creates:
                lines.append(f'  {ANSI_GREEN}+ {name}{ANSI_RESET}')
                var_config = config.variables[name]
                if var_config.description:
                    lines.append(f'    Description: {var_config.description}')
                if var_config.labels:
                    lines.append(f'    Labels: {", ".join(var_config.labels.keys())}')

        if updates:
            lines.append(f'\n{ANSI_YELLOW}=== Variables to UPDATE ==={ANSI_RESET}')
            for name in updates:
                lines.append(f'  {ANSI_YELLOW}~ {name}{ANSI_RESET}')

        if deletes:
            lines.append(f'\n{ANSI_RED}=== Variables to DELETE ==={ANSI_RESET}')
            for name in deletes:
                lines.append(f'  {ANSI_RED}- {name}{ANSI_RESET}')

        if unchanged:
            lines.append(f'\n{ANSI_GRAY}=== No changes needed ({len(unchanged)} variables) ==={ANSI_RESET}')
            for name in unchanged:
                lines.append(f'  {ANSI_GRAY}  {name}{ANSI_RESET}')

        print('\n'.join(lines))

        has_changes = bool(creates or updates or deletes)
        if not has_changes:
            print(f'\n{ANSI_GREEN}No changes needed. Provider is up to date.{ANSI_RESET}')
            return False

        if dry_run:
            print(f'\n{ANSI_YELLOW}Dry run mode - no changes applied.{ANSI_RESET}')
            return True

        # Confirm with user
        if not yes:  # pragma: no cover
            print()
            try:
                response_input = input('Apply these changes? [y/N] ')
            except (EOFError, KeyboardInterrupt):
                print('\nAborted.')
                return False

            if response_input.lower() not in ('y', 'yes'):
                print('Aborted.')
                return False

        # Apply changes
        print('\nApplying changes...')
        try:
            # Build batch update map
            batch: dict[str, VariableConfig | None] = {}
            for name in creates + updates:
                batch[name] = config.variables[name]
            for name in deletes:
                batch[name] = None

            self.batch_update(batch)
        except Exception as e:
            print(f'{ANSI_RED}Error applying changes: {e}{ANSI_RESET}')
            return False

        print(f'\n{ANSI_GREEN}Done! Variables pushed successfully.{ANSI_RESET}')
        return True

    def pull_config(self) -> VariablesConfig:  # pragma: no cover
        """Pull the current variable configuration from the provider.

        This method fetches the complete configuration from the provider,
        useful for generating local copies of the config that can be modified.

        Returns:
            The current VariablesConfig from the provider.
        """
        self.refresh(force=True)
        return self.get_all_variables_config()

    # TODO(next major): consider making strict=True the default and requiring an explicit
    #  opt-out for pushes that publish missing refs or undeclared template fields.
    def push_variables(
        self,
        variables: Sequence[Variable[object]],
        *,
        dry_run: bool = False,
        yes: bool = False,
        strict: bool = False,
    ) -> bool:
        """Push variable definitions to this provider.

        This method syncs local variable definitions (metadata only) with the provider:
        - Creates new variables that don't exist in the provider
        - Updates JSON schemas for existing variables if they've changed
        - Warns about existing label values that are incompatible with new schemas

        Args:
            variables: Variable instances to push.
            dry_run: If True, only show what would change without applying.
            yes: If True, skip confirmation prompt.
            strict: If True, fail if any existing label values are incompatible with new schemas
                or any reference errors are found.

        Returns:
            True if changes were applied (or would be applied in dry_run mode), False otherwise.
        """
        if not variables:
            print('No variables to push. Create variables using logfire.var() first.')
            return False

        # Refresh the provider to ensure we have the latest config
        try:
            self.refresh(force=True)
        except Exception as e:
            print(f'{ANSI_YELLOW}Warning: Could not refresh provider: {e}{ANSI_RESET}')

        # Get current variable configs from provider
        try:
            server_config = self.get_all_variables_config()
        except Exception as e:
            print(f'{ANSI_RED}Error fetching current config: {e}{ANSI_RESET}')
            return False

        # Compute diff
        diff = _compute_diff(variables, server_config)

        # Show diff
        print(_format_diff(diff))

        # Cycles are unconditionally unresolvable (no environment satisfies `A -> B -> A`),
        # so block them even in non-strict mode. Missing references, by contrast, may
        # legitimately resolve in another codebase/environment, so they only hard-fail under
        # strict and are otherwise surfaced as a warning below.
        if diff.reference_cycles:
            print(
                f'\n{ANSI_RED}Error: reference cycle(s) detected.\n'
                f'A cyclic reference can never resolve, so this is blocked even without strict=True. '
                f'Fix the cycle before pushing.{ANSI_RESET}'
            )
            return False

        # `reference_errors` here is missing-reference-only (cycles returned above).
        if diff.reference_errors and strict:
            print(
                f'\n{ANSI_RED}Error: Reference errors found.\n'
                f'Fix these references or set strict=False to proceed anyway.{ANSI_RESET}'
            )
            return False
        elif diff.reference_errors:
            # Non-strict: don't block (the reference may exist elsewhere), but surface the
            # problem as a prominent trailing warning rather than only inside the diff body
            # (parity with the incompatible-labels warning below), so it isn't lost before the
            # success line.
            count = len(diff.reference_errors)
            print(
                f'\n{ANSI_YELLOW}Warning: {count} reference(s) point at variable(s) not found in '
                f'this push (see above). The affected variables will not resolve until those '
                f'exist; re-run with strict=True to block on this.{ANSI_RESET}'
            )

        # Undeclared/mismatched `{{field}}` references: strict blocks, non-strict warns (an
        # undeclared field renders to an empty string at runtime).
        if diff.template_field_issues and strict:
            print(
                f'\n{ANSI_RED}Error: Template field issues found.\n'
                f'Fix the template `{{{{field}}}}` references or update the variable inputs_type, '
                f'or set strict=False to proceed anyway.{ANSI_RESET}'
            )
            return False
        elif diff.template_field_issues:
            count = len(diff.template_field_issues)
            print(
                f'\n{ANSI_YELLOW}Warning: {count} template field issue(s) found (see above). '
                f'Undeclared fields render to an empty string at runtime; re-run with strict=True '
                f'to block on this.{ANSI_RESET}'
            )

        # Check for incompatible label values across all change types
        incompatible_changes = [c for c in diff.changes if c.incompatible_labels]
        if incompatible_changes:
            has_schema_incompatible = any(c.change_type == 'update_schema' for c in incompatible_changes)
            has_unchanged_incompatible = any(c.change_type == 'no_change' for c in incompatible_changes)
            if has_schema_incompatible and has_unchanged_incompatible:
                message = 'Some existing label values are incompatible with the variable types, and some schema changes will make additional values incompatible.'
            elif has_schema_incompatible:
                message = 'Some schema changes will result in label values incompatible with the new schema.'
            else:
                message = 'Some existing label values are incompatible with the variable types (schema unchanged).'
            if strict:
                print(f'\n{ANSI_RED}Error: {message}\nSet strict=False to proceed anyway.{ANSI_RESET}')
                return False
            else:
                print(f'\n{ANSI_YELLOW}Warning: {message}{ANSI_RESET}')

        if not diff.has_changes:
            print(f'\n{ANSI_GREEN}No changes needed. Provider is up to date.{ANSI_RESET}')
            return False

        if dry_run:
            print(f'\n{ANSI_YELLOW}Dry run mode - no changes applied.{ANSI_RESET}')
            return True

        # Confirm with user
        if not yes:  # pragma: no cover
            print()
            try:
                response_input = input('Apply these changes? [y/N] ')
            except (EOFError, KeyboardInterrupt):
                print('\nAborted.')
                return False

            if response_input.lower() not in ('y', 'yes'):
                print('Aborted.')
                return False

        # Apply changes
        print('\nApplying changes...')
        try:
            _apply_changes(self, diff, server_config)
        except Exception as e:
            print(f'{ANSI_RED}Error applying changes: {e}{ANSI_RESET}')
            return False

        # Don't claim a clean "synced successfully" when warnings were applied alongside the
        # changes (unresolved references, undeclared template fields, or incompatible label
        # values in non-strict mode).
        if diff.reference_errors or diff.template_field_issues or incompatible_changes:
            print(
                f'\n{ANSI_YELLOW}Done — changes applied, but with warnings above '
                f'(see the Reference errors / incompatible label sections).{ANSI_RESET}'
            )
        else:
            print(f'\n{ANSI_GREEN}Done! Variables synced successfully.{ANSI_RESET}')
        return True

    def validate_variables(
        self,
        variables: Sequence[Variable[object]],
    ) -> ValidationReport:
        """Validate that provider-side variable label values match local type definitions.

        This method fetches the current variable configuration from the provider and
        validates that all label values can be deserialized to the expected types
        defined in the local Variable instances.

        Args:
            variables: Variable instances to validate.

        Returns:
            A ValidationReport containing any errors found. Use `report.is_valid` to check
            if validation passed, and `report.format()` to get a human-readable summary.

        Example:
            ```python skip="true"
            report = provider.validate_variables(variables)
            if not report.is_valid:
                print(report.format())
                sys.exit(1)
            ```
        """
        if not variables:
            return ValidationReport(
                errors=[],
                variables_checked=0,
                variables_not_on_server=[],
                description_differences=[],
            )

        # Refresh the provider to ensure we have the latest config
        self.refresh(force=True)

        # Get current variable configs from provider
        server_config = self.get_all_variables_config()

        # Find variables not on server
        variables_not_on_server = [v.name for v in variables if v.name not in server_config.variables]

        # Filter to variables that are on the server
        variables_on_server = [v for v in variables if v.name in server_config.variables]

        # Get validation errors
        error_dict = server_config.get_validation_errors(variables_on_server)

        # Build report
        errors: list[LabelValidationError] = []
        for var_name, label_errors in error_dict.items():
            for label, error in label_errors.items():
                errors.append(
                    LabelValidationError(
                        variable_name=var_name,
                        label=label,
                        error=error,
                    )
                )

        # Check for description differences
        description_differences: list[DescriptionDifference] = []
        for variable in variables_on_server:
            server_var = server_config.variables.get(variable.name)
            if server_var is not None:  # pragma: no branch
                # Normalize: treat None and empty string as equivalent
                local_desc = variable.description or None
                server_desc = server_var.description or None
                if local_desc != server_desc:
                    description_differences.append(
                        DescriptionDifference(
                            variable_name=variable.name,
                            local_description=variable.description,
                            server_description=server_var.description,
                        )
                    )

        # Check for reference errors
        reference_errors, reference_cycles = _check_reference_errors(variables, server_config)

        # Validate template variables' `{{field}}` references against their schemas.
        template_field_issues = _collect_template_field_issues(variables, server_config)

        return ValidationReport(
            errors=errors,
            variables_checked=len(variables),
            variables_not_on_server=variables_not_on_server,
            description_differences=description_differences,
            reference_errors=reference_errors,
            reference_cycles=reference_cycles,
            template_field_issues=template_field_issues,
        )

    # --- Variable Types API ---

    def list_variable_types(self) -> dict[str, VariableTypeConfig]:
        """List all variable types from the provider.

        Returns:
            A dictionary mapping type names to their configurations.
        """
        warnings.warn(
            f'{type(self).__name__} does not support variable types',
            stacklevel=2,
        )
        return {}

    def get_variable_type(self, name: str) -> VariableTypeConfig | None:
        """Get a variable type by name.

        Args:
            name: The name of the type to retrieve.

        Returns:
            The VariableTypeConfig if found, None otherwise.
        """
        return self.list_variable_types().get(name)

    def upsert_variable_type(self, config: VariableTypeConfig) -> VariableTypeConfig:
        """Create or update a variable type.

        If a type with the given name exists, it will be updated.
        Otherwise, a new type will be created.

        Args:
            config: The type configuration to upsert.

        Returns:
            The created or updated VariableTypeConfig.
        """
        warnings.warn(
            f'{type(self).__name__} does not persist variable type writes',
            stacklevel=2,
        )
        return config

    def push_variable_types(
        self,
        types: Sequence[type[Any] | tuple[type[Any], str]],
        *,
        dry_run: bool = False,
        yes: bool = False,
        strict: bool = False,
    ) -> bool:
        """Push variable type definitions to this provider.

        This method syncs local type definitions with the provider:
        - Creates new types that don't exist in the provider
        - Updates JSON schemas for existing types if they've changed
        - Warns about schema changes
        - Checks if existing variable label values are compatible with the new schemas

        Args:
            types: Types to push. Items can be:
                - A type (name defaults to __name__ or str(type))
                - A tuple of (type, name) for explicit naming
            dry_run: If True, only show what would change without applying.
            yes: If True, skip confirmation prompt.
            strict: If True, abort when existing label values are incompatible with
                the new type schema.

        Returns:
            True if changes were applied (or would be applied in dry_run mode), False otherwise.

        Example:
            ```python skip="true"
            from pydantic import BaseModel


            class FeatureConfig(BaseModel):
                enabled: bool
                max_items: int = 10


            # Push using __name__ as type name
            provider.push_variable_types([FeatureConfig])

            # Push with explicit name
            provider.push_variable_types([(FeatureConfig, 'my_feature_config')])
            ```
        """
        from pydantic import TypeAdapter

        from logfire.variables.config import VariableTypeConfig, get_default_type_name, get_source_hint

        if not types:
            print('No types to push.')
            return False

        # Refresh the provider to ensure we have the latest config
        try:
            self.refresh(force=True)
        except Exception as e:
            print(f'{ANSI_YELLOW}Warning: Could not refresh provider: {e}{ANSI_RESET}')

        # Get current types from provider
        try:
            server_types = self.list_variable_types()
        except Exception as e:
            print(f'{ANSI_RED}Error fetching current types: {e}{ANSI_RESET}')
            return False

        # Build list of type configs to push, keeping adapters for validation
        type_configs: list[VariableTypeConfig] = []
        type_adapters: dict[str, TypeAdapter[Any]] = {}
        for item in types:
            if isinstance(item, tuple):
                t, name = item
            else:
                t = item
                name = get_default_type_name(t)

            adapter = TypeAdapter(t)
            json_schema = adapter.json_schema()
            source_hint = get_source_hint(t)

            type_adapters[name] = adapter
            type_configs.append(
                VariableTypeConfig(
                    name=name,
                    json_schema=json_schema,
                    source_hint=source_hint,
                )
            )

        # Compute diff
        creates: list[str] = []
        updates: list[str] = []
        unchanged: list[str] = []

        for config in type_configs:
            existing = server_types.get(config.name)
            if existing is None:
                creates.append(config.name)
            elif existing.json_schema != config.json_schema:
                updates.append(config.name)
            else:
                unchanged.append(config.name)

        # Show diff
        print(f'\n{ANSI_BOLD}Variable Types Push Summary{ANSI_RESET}')
        print('=' * 40)

        if creates:
            print(f'\n{ANSI_GREEN}New types ({len(creates)}):{ANSI_RESET}')
            for name in creates:
                print(f'  + {name}')

        if updates:
            print(f'\n{ANSI_YELLOW}Schema updates ({len(updates)}):{ANSI_RESET}')
            for name in updates:
                print(f'  ~ {name}')

        if unchanged:
            print(f'\n{ANSI_DIM}Unchanged ({len(unchanged)}):{ANSI_RESET}')
            for name in unchanged:
                print(f'  = {name}')

        # Check label compatibility for updated types
        incompatible_vars: dict[str, list[tuple[str, LabelCompatibility]]] = {}
        if updates:
            try:
                server_config = self.get_all_variables_config()
                for type_name in updates:
                    adapter = type_adapters[type_name]
                    # Find variables that reference this type
                    for var_config in server_config.variables.values():
                        if var_config.type_name != type_name:
                            continue
                        incompatible = _check_type_label_compatibility(adapter, var_config)
                        if incompatible:
                            var_issues = incompatible_vars.setdefault(type_name, [])
                            for compat in incompatible:
                                var_issues.append((var_config.name, compat))
            except Exception as e:
                print(f'{ANSI_YELLOW}Warning: Could not check label compatibility: {e}{ANSI_RESET}')

        if incompatible_vars:
            print(f'\n{ANSI_YELLOW}=== Label compatibility warnings ==={ANSI_RESET}')
            for type_name, issues in incompatible_vars.items():
                print(f'  {ANSI_YELLOW}Type: {type_name}{ANSI_RESET}')
                for var_name, compat in issues:
                    print(
                        f'    {ANSI_RED}\u26a0 Variable {var_name!r}, label {compat.label!r}: {compat.error}{ANSI_RESET}'
                    )
            message = 'Some existing label values are incompatible with the new type schema.'
            if strict:
                print(f'\n{ANSI_RED}Error: {message}\nSet strict=False to proceed anyway.{ANSI_RESET}')
                return False
            else:
                print(f'\n{ANSI_YELLOW}Warning: {message}{ANSI_RESET}')

        if not creates and not updates:
            print(f'\n{ANSI_GREEN}No changes needed. Types are up to date.{ANSI_RESET}')
            return False

        if dry_run:
            print(f'\n{ANSI_YELLOW}Dry run mode - no changes applied.{ANSI_RESET}')
            return True

        # Confirm with user
        if not yes:  # pragma: no cover
            print()
            try:
                response_input = input('Apply these changes? [y/N] ')
            except (EOFError, KeyboardInterrupt):
                print('\nAborted.')
                return False

            if response_input.lower() not in ('y', 'yes'):
                print('Aborted.')
                return False

        # Apply changes
        print('\nApplying changes...')
        try:
            for config in type_configs:
                if config.name in creates or config.name in updates:
                    self.upsert_variable_type(config)
        except Exception as e:
            print(f'{ANSI_RED}Error applying changes: {e}{ANSI_RESET}')
            return False

        print(f'\n{ANSI_GREEN}Done! Variable types synced successfully.{ANSI_RESET}')
        return True


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
            targeting_key: Optional key for deterministic label selection (ignored).
            attributes: Optional attributes for condition-based targeting rules (ignored).

        Returns:
            A ResolvedVariable with value=None.
        """
        return ResolvedVariable(name=variable_name, value=None, reason='no_provider')

    def get_variable_config(self, name: str) -> VariableConfig | None:
        """Return None for all variable lookups.

        Args:
            name: The name of the variable (ignored).

        Returns:
            Always None since no provider is configured.
        """
        return None

    def push_variables(
        self,
        variables: Sequence[Variable[Any]],
        *,
        dry_run: bool = False,
        yes: bool = False,
        strict: bool = False,
    ) -> bool:
        """No-op implementation that prints a message about missing provider configuration.

        Returns:
            Always False since no provider is configured.
        """
        print('No variable provider configured. Configure a provider using logfire.configure(variables=...).')
        return False

    def validate_variables(
        self,
        variables: Sequence[Variable[Any]],
    ) -> ValidationReport:
        """No-op implementation that returns an empty validation report.

        Returns:
            An empty ValidationReport since there's no provider to validate against.
        """
        return ValidationReport(
            errors=[],
            variables_checked=0,
            variables_not_on_server=[],
            description_differences=[],
        )
