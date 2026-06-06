"""Variable composition: expand `@{variable_name}@` references in serialized values.

This module provides pure functions for expanding variable references in serialized
JSON strings. References use the `@{variable_name}@` syntax and are expanded by
running the value through `pydantic_handlebars` with the composition delimiter
pair, so the full Handlebars syntax is available: simple references, dotted
field reads, block helpers (including with dotted or sub-expression headers like
`@{#if user.active}@`), and helper sub-expressions.

Meanwhile, any `{{runtime}}` placeholders are preserved untouched for later
template rendering.

The composition logic is pure and backend-safe, so server-side evaluation paths
can reuse it when they need the same expansion semantics as SDK resolution.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logfire.variables.abstract import ResolutionReason

__all__ = (
    'MAX_COMPOSITION_DEPTH',
    'VariableCompositionError',
    'VariableCompositionCycleError',
    'ComposedReference',
    'expand_references',
    'find_references',
    'find_references_and_errors',
    'has_references',
)

# Cheap gate used to skip strings with no composition syntax at all. Any
# `@{` (even escaped) routes through pydantic-handlebars, which is where the
# escape semantics live — under `pydantic-handlebars >= 0.2.1` a run of N
# backslashes before `@{` contributes `N // 2` literal `\`s and lets parity
# decide whether the mustache renders. Doing that count in a regex would
# need a variable-width lookbehind we can't portably write on 3.10/3.11, and
# is unnecessary now that the renderer is the single source of truth.
_HAS_OPEN_DELIM = '@{'

# Interpolation-reference matcher used by the unresolved-reference protection
# helpers. An unresolved name is left ABSENT from the render context so it is
# falsy in control positions (`@{#if name}@` takes the else branch), matching
# standard Handlebars. That alone would make a bare or dotted *interpolation*
# (`@{name}@` / `@{name.field}@`) render to an empty string, so each such
# interpolation is replaced with a sentinel pre-render and restored afterwards
# to keep its literal source text visible. Block/helper tags (`@{#if name}@`,
# `@{else}@`, `@{/if}@`, …) deliberately do not match, so they render with the
# name absent (falsy). The dotted suffix is optional so bare `@{name}@` matches
# too.
_INTERP_REF_TEXT = re.compile(r'(?<!\\)@\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}@')


MAX_COMPOSITION_DEPTH = 20


class VariableCompositionError(Exception):
    """Error during variable composition (reference expansion)."""


class VariableCompositionCycleError(VariableCompositionError):
    """Circular reference detected during variable composition."""


@dataclass
class ComposedReference:
    """Metadata about a single `@{reference}@` that was encountered during expansion.

    This is a lightweight dataclass used to track composition results without
    depending on ResolvedVariable, making it reusable from both the SDK and backend.
    """

    name: str
    """Name of the referenced variable."""
    value: str | None
    """Expanded raw string value, or None if unresolved."""
    label: str | None
    """Label of the referenced variable's resolution."""
    version: int | None
    """Version of the referenced variable's resolution."""
    reason: ResolutionReason
    """How the referenced variable was resolved."""
    error: str | None = None
    """Error message if the reference could not be expanded."""
    composed_from: list[ComposedReference] = field(default_factory=list['ComposedReference'])
    """Nested references that were expanded within this reference."""
    fatal: bool = False
    """Whether *error* is a fatal composition failure.

    Fatal failures (a cycle or depth overflow) are structural — the value can't be
    meaningfully composed at all — so a consumer should discard the value and fall back.
    Non-fatal failures (an unresolved/missing reference, or a referenced variable with a
    malformed value) are *soft*: an unresolved reference is treated as missing — its bare
    `@{ref}@` / `@{ref.field}@` interpolation is left in place as literal text, while in a
    control position (`@{#if ref}@`, `@{#each ref}@`) it reads as falsy like standard
    Handlebars — and the rest of the value still renders, so the partially-composed value
    is usable. Always `False` when *error* is `None`.
    """


# resolve_fn signature: (ref_name) -> (serialized_value, label, version, reason)
ResolveFn = Callable[[str], tuple[str | None, str | None, int | None, ResolutionReason]]


def has_references(serialized_value: str) -> bool:
    r"""Quick check for any `@{` in a serialized value.

    Returns `True` whenever the string contains the composition open
    delimiter, regardless of preceding backslashes. The actual
    escape-or-real decision is made by `pydantic_handlebars` at render time
    — distinguishing an escaped `\@{x}@` from an unescaped `@{x}@` here
    would require a variable-width lookbehind (the renderer counts
    backslash parity to match Handlebars.js semantics) and is unnecessary:
    `extract_composition_dependencies` returns an empty set for escaped-only
    strings, and the renderer correctly leaves the literal text in place.
    """
    return _HAS_OPEN_DELIM in serialized_value


def expand_references(
    serialized_value: str,
    variable_name: str,
    resolve_fn: ResolveFn,
    *,
    _visited: tuple[str, ...] = (),
    _depth: int = 0,
) -> tuple[str, list[ComposedReference]]:
    """Expand `@{var}@` references in a serialized variable value.

    Uses the Handlebars engine so `@{}@` supports the full Handlebars
    syntax — simple references, dotted field reads, block helpers (including
    with dotted or sub-expression headers like `@{#if user.active}@`), and
    helper sub-expressions — while preserving `{{runtime}}` placeholders
    untouched.

    Args:
        serialized_value: The raw JSON-serialized variable value.
        variable_name: Name of the variable being expanded (for cycle detection).
        resolve_fn: Function that resolves a variable name to
            (serialized_value, label, version, reason).
        _visited: Internal - ordered variable names in the current expansion chain.
        _depth: Internal - current recursion depth.

    Returns:
        tuple of (expanded_serialized_value, list_of_composed_references).

    Raises:
        VariableCompositionError: If max depth is exceeded.
        VariableCompositionCycleError: If a circular reference is detected.
    """
    if _depth > MAX_COMPOSITION_DEPTH:
        raise VariableCompositionError(
            f'Maximum composition depth ({MAX_COMPOSITION_DEPTH}) exceeded '
            f"while expanding '{variable_name}'. This likely indicates a circular reference."
        )

    if variable_name in _visited:
        raise VariableCompositionCycleError(f'Circular reference detected: {" -> ".join(_visited)} -> {variable_name}')

    visited = (*_visited, variable_name)
    composed: list[ComposedReference] = []

    # JSON-decode the serialized value so we can work with actual strings.
    decoded = _safe_json_load(serialized_value)
    if decoded is None and serialized_value.strip() != 'null':
        # The string isn't valid JSON at all — bail out rather than try to
        # render an invalid value.
        return serialized_value, composed

    # Collect all unique base variable names referenced anywhere in the decoded
    # value. Sorted so composition resolution order is deterministic — which
    # `composed_from` entry surfaces first, which error gets reported when
    # several refs fail, etc. shouldn't depend on set-iteration order. If there
    # are none we still walk the structure through `_render_value` — the value
    # may contain only escape sequences (`\@{x}@` etc.) that need to be
    # processed through the renderer to produce the literal output.
    all_ref_names = sorted(_collect_ref_names(decoded))

    # Resolve each unique variable name and recursively expand nested references.
    context: dict[str, Any] = {}
    unresolved_names: set[str] = set()

    for ref_name in all_ref_names:
        ref_serialized, ref_label, ref_version, ref_reason = resolve_fn(ref_name)

        if ref_serialized is None:
            composed.append(
                ComposedReference(
                    name=ref_name,
                    value=None,
                    label=ref_label,
                    version=ref_version,
                    reason=ref_reason,
                    error=f"Referenced variable '{ref_name}' could not be resolved.",
                )
            )
            unresolved_names.add(ref_name)
            continue

        # JSON-decode the referenced value.
        try:
            raw_value = json.loads(ref_serialized)
        except (json.JSONDecodeError, TypeError):
            composed.append(
                ComposedReference(
                    name=ref_name,
                    value=None,
                    label=ref_label,
                    version=ref_version,
                    reason=ref_reason,
                    error=f"Referenced variable '{ref_name}' has a non-JSON serialized value.",
                )
            )
            unresolved_names.add(ref_name)
            continue

        # Recursively expand references within the resolved value.
        nested_composed: list[ComposedReference] = []
        if has_references(ref_serialized):
            try:
                expanded_serialized, nested_composed = expand_references(
                    ref_serialized,
                    ref_name,
                    resolve_fn,
                    _visited=visited,
                    _depth=_depth + 1,
                )
                raw_value = json.loads(expanded_serialized)
            except VariableCompositionError as e:
                # A cycle or depth overflow within the referenced value: this is a
                # structural (fatal) failure, not a benign missing reference.
                composed.append(
                    ComposedReference(
                        name=ref_name,
                        value=None,
                        label=ref_label,
                        version=ref_version,
                        reason=ref_reason,
                        error=str(e),
                        fatal=True,
                    )
                )
                unresolved_names.add(ref_name)
                continue

        # Build the ComposedReference for this variable.
        value_str: str | None
        if isinstance(raw_value, str):
            value_str = raw_value
        else:
            value_str = json.dumps(raw_value)

        composed.append(
            ComposedReference(
                name=ref_name,
                value=value_str,
                label=ref_label,
                version=ref_version,
                reason=ref_reason,
                composed_from=nested_composed,
            )
        )

        context[ref_name] = raw_value

    # Unresolved names are intentionally left ABSENT from `context`: Handlebars
    # then treats them as falsy/missing in control positions — `@{#if missing}@`
    # takes the else branch, `@{#each missing}@` renders empty — matching
    # standard Handlebars semantics rather than silently selecting a branch.
    # Their bare/dotted *interpolation* occurrences are preserved as literal
    # `@{name}@` text by `_render_value` (sentinel-protect), so a missing
    # reference stays visible in the output.
    rendered = _render_value(decoded, context, unresolved_names)

    # ensure_ascii=False so non-ASCII characters survive as themselves in the serialized result
    # rather than being \u-escaped — the decoded value is identical either way, but consumers that
    # compare or display the serialized string shouldn't see surprise escaping introduced by
    # composition.
    result_serialized = json.dumps(rendered, ensure_ascii=False)
    return result_serialized, composed


def find_references(serialized_value: str) -> list[str]:
    """Find all top-level `@{variable_name}@` references in a serialized value.

    Walks the decoded JSON value and runs each string containing composition
    syntax through `pydantic_handlebars.extract_dependencies`, so block
    helpers (`@{#if var}@`), dotted paths (`@{var.field}@`), and
    subexpressions (`@{lookup obj key}@`) are all picked up correctly. A string
    whose `@{...}@` syntax can't be parsed is skipped (contributes no
    references) so this never raises; use `find_references_and_errors` to also
    surface those parse failures.

    Args:
        serialized_value: The raw JSON-serialized variable value to scan.

    Returns:
        Sorted (alphabetical) list of unique top-level variable names referenced.
    """
    return sorted(_collect_ref_names(_safe_json_load(serialized_value)))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_json_load(serialized_value: str) -> Any:
    """JSON-decode *serialized_value*, returning ``None`` on failure."""
    try:
        return json.loads(serialized_value)
    except (json.JSONDecodeError, TypeError):
        return None


def _collect_ref_names(value: Any) -> set[str]:
    """Recursively walk a decoded JSON value and collect unique top-level reference names.

    For each string the AST-aware
    ``pydantic_handlebars.extract_dependencies`` picks the authoritative set
    of real references (so block helpers, dotted paths, subexpressions are
    handled correctly and Handlebars helper names are excluded). Strings whose
    `@{...}@` syntax can't be parsed are skipped (see `_walk_references`), so
    dependency discovery never raises — resolution must stay total on untrusted
    values. Use `find_references_and_errors` when you also need those parse
    failures surfaced.
    """
    refs, _errors = _walk_references(value)
    return refs


def _walk_references(value: Any) -> tuple[set[str], list[str]]:
    """Walk a decoded JSON value, returning ``(reference names, parse-error messages)``.

    Each string containing composition syntax is passed to the AST-aware
    ``pydantic_handlebars.extract_dependencies``. A malformed template
    (``@{#if x}@`` with no close) or a reserved name (``@{true}@``) makes the
    extractor raise — a ``HandlebarsError`` or, for reserved names, a bare
    ``AssertionError``. Rather than propagate (which would crash
    push / validate / resolve), the offending string is recorded as a parse
    error and contributes no references.
    """
    from logfire.variables._handlebars import HandlebarsDependencyError, extract_composition_dependencies

    refs: set[str] = set()
    errors: list[str] = []

    # Iterative walk (explicit stack) rather than recursion: the decoded value comes from arbitrary
    # server config and can nest arbitrarily deep, which would otherwise raise RecursionError out of
    # push / validate / resolve.
    stack: list[Any] = [value]
    while stack:
        v = stack.pop()
        if isinstance(v, str):
            if has_references(v):
                try:
                    refs.update(extract_composition_dependencies(v))
                except HandlebarsDependencyError as e:
                    # pydantic-handlebars isn't installed, so `@{...}@` composition can't be parsed
                    # at all. Surface the clear install hint rather than a misleading "could not be
                    # parsed" message (which would otherwise appear once per composition value).
                    errors.append(str(e))
                except Exception as e:
                    # `extract_dependencies` raises HandlebarsError on malformed templates and a
                    # bare AssertionError on reserved names, so catch broadly. The value is recorded
                    # as a parse error instead of crashing dependency discovery.
                    errors.append(f'value {v!r} could not be parsed as a composition template: {e}')
        elif isinstance(v, dict):
            stack.extend(v.values())  # pyright: ignore[reportUnknownArgumentType]
        elif isinstance(v, list):
            stack.extend(v)  # pyright: ignore[reportUnknownArgumentType]
    return refs, errors


def find_references_and_errors(serialized_value: str) -> tuple[list[str], list[str]]:
    """Find references AND parse-error messages in a serialized value.

    Like `find_references`, but also returns a message for every string whose
    `@{...}@` syntax can't be parsed (malformed template, reserved name). Used by
    push / validate so a malformed value is surfaced as a loud error rather than
    silently skipped the way `find_references` does (it skips them so resolution
    can degrade gracefully).

    Returns:
        ``(sorted unique reference names, parse-error messages)``.
    """
    refs, errors = _walk_references(_safe_json_load(serialized_value))
    return sorted(refs), errors


def _render_value(value: Any, context: dict[str, Any], unresolved_names: set[str]) -> Any:
    """Recursively walk a decoded JSON value, rendering strings through Handlebars.

    Unresolved variable names are absent from *context*, so the renderer treats
    them as falsy/missing — `@{#if missing}@` takes the else branch and a
    missing name in a control/helper position renders empty, matching standard
    Handlebars. To keep an unresolved *interpolation* visible, its bare and
    dotted occurrences (`@{name}@` / `@{name.field}@`) are sentinel-protected
    before rendering and restored afterwards, so their literal source survives
    rather than rendering empty.
    Strings without any composition delimiter pass straight through; strings
    that contain `@{` (escaped or not) route through the renderer, which
    handles the backslash-parity escape rule.
    """
    if isinstance(value, str):
        if not has_references(value):
            return value
        from logfire.variables.reference_syntax import render_once

        protected_value, protected_refs = _protect_unresolved_interpolations(value, unresolved_names)
        rendered = render_once(protected_value, context)
        return _restore_unresolved_refs(rendered, protected_refs)
    if isinstance(value, dict):
        return {
            k: _render_value(v, context, unresolved_names)
            for k, v in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, list):
        return [_render_value(v, context, unresolved_names) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def _protect_unresolved_interpolations(value: str, unresolved_names: set[str]) -> tuple[str, dict[str, str]]:
    """Replace unresolved-name interpolation tags with sentinels before Handlebars rendering.

    Unresolved names are left out of the render context so they read as falsy
    in control positions (`@{#if name}@` takes the else branch). That alone
    would make a bare or dotted *interpolation* (`@{name}@` / `@{name.field}@`)
    render to an empty string, so we substitute a sentinel for each such
    interpolation pre-render and restore it after, keeping the literal source
    visible. Block/helper tags (`@{#if name}@`, `@{#each name}@`, …) are
    intentionally not matched, so they render with the name absent (falsy).
    """
    if not unresolved_names:
        return value, {}

    protected_refs: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        full_ref = match.group(1)
        if full_ref.split('.')[0] not in unresolved_names:
            return match.group(0)
        sentinel = f'\x00logfire-unresolved-ref-{len(protected_refs)}-{id(value)}\x00'
        protected_refs[sentinel] = match.group(0)
        return sentinel

    return _INTERP_REF_TEXT.sub(replace, value), protected_refs


def _restore_unresolved_refs(value: str, protected_refs: dict[str, str]) -> str:
    """Restore unresolved reference sentinels after Handlebars rendering."""
    for sentinel, ref in protected_refs.items():
        value = value.replace(sentinel, ref)
    return value
