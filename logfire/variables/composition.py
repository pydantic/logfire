"""Variable composition: expand `@{variable_name}@` references in serialized values.

This module provides pure functions for expanding variable references in serialized
JSON strings. References use the `@{variable_name}@` syntax and are expanded using
a Handlebars-compatible subset: simple references, dotted field reads, and block
helpers whose condition/iterable is a top-level referenced variable.

Meanwhile, any `{{runtime}}` placeholders are preserved untouched for later
template rendering.

The composition logic is shared between the SDK (client-side expansion) and the
backend OFREP endpoint (server-side expansion).
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
    'has_references',
)

# Matches unescaped @{ (not preceded by \). Used as a cheap gate so we only
# parse strings that actually contain composition syntax. Real reference
# extraction goes through `pydantic_handlebars.extract_dependencies` so block
# helpers, dotted paths, and subexpressions are all handled AST-correctly.
_HAS_REFERENCE = re.compile(r'(?<!\\)@\{')

# Dotted-reference matcher used by the unresolved-reference protection
# helpers — those need a textual hook so the literal `@{name.field}@` source
# substring can be replaced with a sentinel and restored after rendering.
_DOTTED_REF_TEXT = re.compile(r'(?<!\\)@\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+)\}@')


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
    composed_from: list[ComposedReference] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    """Nested references that were expanded within this reference."""


# resolve_fn signature: (ref_name) -> (serialized_value, label, version, reason)
ResolveFn = Callable[[str], tuple[str | None, str | None, int | None, ResolutionReason]]


def has_references(serialized_value: str) -> bool:
    """Quick check for any unescaped `@{` in a serialized value."""
    return _HAS_REFERENCE.search(serialized_value) is not None


def expand_references(
    serialized_value: str,
    variable_name: str,
    resolve_fn: ResolveFn,
    *,
    _visited: tuple[str, ...] = (),
    _depth: int = 0,
) -> tuple[str, list[ComposedReference]]:
    """Expand `@{var}@` references in a serialized variable value.

    Uses the Handlebars engine so that `@{}@` supports simple references,
    dotted field reads, and block helpers whose condition/iterable is a
    top-level referenced variable while preserving `{{runtime}}` placeholders
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

    # Collect all unique base variable names referenced anywhere in the decoded value.
    all_ref_names = _collect_ref_names(decoded)
    if not all_ref_names:
        # No references at all — return unchanged (but still unescape \@{ → @{).
        expanded = _unescape_serialized(serialized_value)
        return expanded, composed

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
                composed.append(
                    ComposedReference(
                        name=ref_name,
                        value=None,
                        label=ref_label,
                        version=ref_version,
                        reason=ref_reason,
                        error=str(e),
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

    # For unresolved variable names, add a self-referential context entry so that
    # Handlebars renders @{name}@ back as literal "@{name}@".
    for name in unresolved_names:
        context[name] = f'@{{{name}}}@'

    # Walk the decoded value and render each string through the reference-syntax Handlebars engine.
    rendered = _render_value(decoded, context, unresolved_names)

    result_serialized = json.dumps(rendered)
    return result_serialized, composed


def find_references(serialized_value: str) -> list[str]:
    """Find all top-level `@{variable_name}@` references in a serialized value.

    Walks the decoded JSON value and runs each string containing composition
    syntax through `pydantic_handlebars.extract_dependencies`, so block
    helpers (`@{#if var}@`), dotted paths (`@{var.field}@`), and
    subexpressions (`@{lookup obj key}@`) are all picked up correctly.

    Args:
        serialized_value: The raw JSON-serialized variable value to scan.

    Returns:
        List of unique top-level variable names referenced, in order of
        first occurrence.
    """
    return _collect_ref_names(_safe_json_load(serialized_value))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_json_load(serialized_value: str) -> Any:
    """JSON-decode *serialized_value*, returning ``None`` on failure."""
    try:
        return json.loads(serialized_value)
    except (json.JSONDecodeError, TypeError):
        return None


def _collect_ref_names(value: Any) -> list[str]:
    """Recursively walk a decoded JSON value and collect unique top-level reference names.

    For each string the AST-aware
    ``pydantic_handlebars.extract_dependencies`` picks the authoritative set
    of real references (so block helpers, dotted paths, subexpressions are
    handled correctly and Handlebars helper names are excluded). Names from
    that set are added to the result list ordered by their first textual
    occurrence in the source string, giving deterministic output across
    `dict` iteration orders.
    """
    from logfire.variables._handlebars import extract_composition_dependencies

    seen: set[str] = set()
    result: list[str] = []

    def _walk(v: Any) -> None:
        if isinstance(v, str):
            if not has_references(v):
                return
            valid = extract_composition_dependencies(v)
            if not valid:
                return
            for name in _order_by_first_position(valid, v):
                if name not in seen:
                    seen.add(name)
                    result.append(name)
        elif isinstance(v, dict):
            for val in v.values():  # pyright: ignore[reportUnknownVariableType]
                _walk(val)
        elif isinstance(v, list):
            for item in v:  # pyright: ignore[reportUnknownVariableType]
                _walk(item)

    _walk(value)
    return result


def _order_by_first_position(names: set[str], source: str) -> list[str]:
    """Order *names* by their first whole-word occurrence in *source*.

    Used to give `find_references` deterministic, source-order output for a
    set produced by `extract_composition_dependencies`. Names that don't
    appear textually in the source — which shouldn't happen for refs
    returned by the AST walker, but is defensive — sort to the end of the
    list in alphabetical order so output remains stable.
    """
    positions: dict[str, int] = {}
    for name in names:
        # Use a word-boundary search so e.g. `key` doesn't match inside `keyword`.
        pattern = re.compile(rf'\b{re.escape(name)}\b')
        match = pattern.search(source)
        positions[name] = match.start() if match is not None else len(source) + sum(map(ord, name))
    return sorted(names, key=lambda n: positions[n])


def _render_value(value: Any, context: dict[str, Any], unresolved_names: set[str]) -> Any:
    """Recursively walk a decoded JSON value, rendering strings through Handlebars.

    Unresolved variable names are present in *context* as their literal
    ``@{name}@`` text so the renderer preserves them in the output. Dotted
    accesses against unresolved names are pre-protected so they retain the
    full ``@{name.field}@`` source rather than rendering as empty.
    """
    if isinstance(value, str):
        if not has_references(value):
            # Unescape \@{ to @{ for non-reference strings.
            return value.replace('\\@{', '@{')
        from logfire.variables.reference_syntax import render_once

        protected_value, protected_refs = _protect_unresolved_dotted_refs(value, unresolved_names)
        rendered = render_once(protected_value, context) if has_references(protected_value) else protected_value
        return _restore_unresolved_refs(rendered, protected_refs)
    if isinstance(value, dict):
        return {
            k: _render_value(v, context, unresolved_names)
            for k, v in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, list):
        return [_render_value(v, context, unresolved_names) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def _protect_unresolved_dotted_refs(value: str, unresolved_names: set[str]) -> tuple[str, dict[str, str]]:
    """Replace unresolved dotted reference tags with sentinels before Handlebars rendering.

    With native ``@{...}@`` rendering, an unresolved name's literal text
    placeholder in the context only retains the bare ``@{name}@`` form —
    dotted accesses like ``@{name.field}@`` would resolve against the
    string and produce empty output. To keep the original dotted source
    visible we substitute a sentinel pre-render and restore it after.
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

    return _DOTTED_REF_TEXT.sub(replace, value), protected_refs


def _restore_unresolved_refs(value: str, protected_refs: dict[str, str]) -> str:
    """Restore unresolved reference sentinels after Handlebars rendering."""
    for sentinel, ref in protected_refs.items():
        value = value.replace(sentinel, ref)
    return value


def _unescape_serialized(serialized: str) -> str:
    r"""Unescape `\@{` to `@{` in a JSON-serialized string.

    In JSON encoding, a literal backslash is `\\`, so `\@{` in user content
    appears as `\\@{` in the serialized JSON.
    """
    return serialized.replace('\\\\@{', '@{')
