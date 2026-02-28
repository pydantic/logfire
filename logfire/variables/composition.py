"""Variable composition: expand <<variable_name>> references in serialized values.

This module provides pure functions for expanding variable references in serialized
JSON strings. References use the ``<<variable_name>>`` syntax and are expanded using
the Handlebars engine via character-swap, giving ``<<>>`` the full power of
Handlebars: ``<<#if>>``, ``<<#each>>``, ``<<#unless>>``, ``<<#with>>``, etc.

Meanwhile, any ``{{runtime}}`` placeholders are preserved untouched for later
template rendering.

The composition logic is shared between the SDK (client-side expansion) and the
backend OFREP endpoint (server-side expansion).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple  # noqa: UP035

from logfire.handlebars.angle_bracket import render_once

__all__ = (
    'MAX_COMPOSITION_DEPTH',
    'VariableCompositionError',
    'VariableCompositionCycleError',
    'ComposedReference',
    'expand_references',
    'find_references',
    'has_references',
)

# Matches unescaped << (not preceded by \).
# In JSON-serialized strings, a real backslash is \\, so \\<< is an escaped ref.
_HAS_ANGLE = re.compile(r'(?<!\\)<<')

# Simple references: <<identifier>> or <<identifier.field.subfield>>
_SIMPLE_REF = re.compile(r'(?<!\\)<<([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)>>')

# Block helper references: <<#helper identifier ...>> — extracts the first identifier after the helper name.
_BLOCK_REF = re.compile(r'(?<!\\)<<#\w+\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s|>>)')

# Handlebars keywords that should never be treated as variable references.
# These are valid in <<keyword>> syntax but are Handlebars built-ins.
_HBS_KEYWORDS = frozenset({'else', 'this'})

MAX_COMPOSITION_DEPTH = 20


class VariableCompositionError(Exception):
    """Error during variable composition (reference expansion)."""


class VariableCompositionCycleError(VariableCompositionError):
    """Circular reference detected during variable composition."""


@dataclass
class ComposedReference:
    """Metadata about a single <<reference>> that was encountered during expansion.

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
    reason: str
    """Resolution reason (e.g., 'resolved', 'unrecognized_variable')."""
    error: str | None = None
    """Error message if the reference could not be expanded."""
    composed_from: list[ComposedReference] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    """Nested references that were expanded within this reference."""


# resolve_fn signature: (ref_name) -> (serialized_value, label, version, reason)
ResolveFn = Callable[[str], Tuple[Optional[str], Optional[str], Optional[int], str]]  # noqa: UP006


def has_references(serialized_value: str) -> bool:
    """Quick check for any unescaped ``<<`` in a serialized value."""
    return _HAS_ANGLE.search(serialized_value) is not None


def expand_references(
    serialized_value: str,
    variable_name: str,
    resolve_fn: ResolveFn,
    *,
    _visited: frozenset[str] = frozenset(),
    _depth: int = 0,
) -> tuple[str, list[ComposedReference]]:
    """Expand <<var>> references in a serialized variable value.

    Uses the Handlebars engine via character-swap so that ``<<>>`` supports the
    full Handlebars feature set (``<<#if>>``, ``<<#each>>``, etc.) while
    preserving ``{{runtime}}`` placeholders untouched.

    Args:
        serialized_value: The raw JSON-serialized variable value.
        variable_name: Name of the variable being expanded (for cycle detection).
        resolve_fn: Function that resolves a variable name to
            (serialized_value, label, version, reason).
        _visited: Internal - set of variable names in the current expansion chain.
        _depth: Internal - current recursion depth.

    Returns:
        Tuple of (expanded_serialized_value, list_of_composed_references).

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

    visited = _visited | {variable_name}
    composed: list[ComposedReference] = []

    # JSON-decode the serialized value so we can work with actual strings.
    try:
        decoded = json.loads(serialized_value)
    except (json.JSONDecodeError, TypeError):
        return serialized_value, composed

    # Collect all unique base variable names referenced anywhere in the decoded value.
    all_ref_names = _collect_ref_names(decoded)
    if not all_ref_names:
        # No references at all — return unchanged (but still unescape \<< → <<).
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

        # Recursively expand references within the resolved value (if it's a string).
        nested_composed: list[ComposedReference] = []
        if isinstance(raw_value, str) and has_references(json.dumps(raw_value)):
            try:
                expanded_serialized, nested_composed = expand_references(
                    json.dumps(raw_value),
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
    # Handlebars renders <<name>> back as literal "<<name>>". The _protect_value
    # function in render_once will entity-encode the <> characters in the value,
    # preventing the swap from consuming them.
    for name in unresolved_names:
        context[name] = f'<<{name}>>'

    # Walk the decoded value and render each string through the Handlebars swap engine.
    rendered = _render_value(decoded, context)

    result_serialized = json.dumps(rendered)
    return result_serialized, composed


def find_references(serialized_value: str) -> list[str]:
    """Find all <<variable_name>> references in a serialized value.

    Detects both simple ``<<var>>`` and block ``<<#helper var>>`` patterns.
    For dotted references like ``<<var.field>>``, only the base variable name
    (first segment) is returned. This ensures correct cycle detection and
    reference graph building.

    Args:
        serialized_value: The raw JSON-serialized variable value to scan.

    Returns:
        List of unique variable names referenced, in order of first occurrence.
    """
    seen: set[str] = set()
    result: list[str] = []

    # Simple references: <<var>> or <<var.field>>
    for match in _SIMPLE_REF.finditer(serialized_value):
        full_ref = match.group(1)
        var_name = full_ref.split('.')[0]
        if var_name not in seen and var_name not in _HBS_KEYWORDS:
            seen.add(var_name)
            result.append(var_name)

    # Block helper references: <<#if var>>, <<#each var>>, etc.
    for match in _BLOCK_REF.finditer(serialized_value):
        var_name = match.group(1)
        if var_name not in seen and var_name not in _HBS_KEYWORDS:
            seen.add(var_name)
            result.append(var_name)

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_ref_names(value: Any) -> list[str]:
    """Recursively walk a decoded JSON value and collect all unique base variable names."""
    seen: set[str] = set()
    result: list[str] = []

    def _walk(v: Any) -> None:
        if isinstance(v, str):
            for match in _SIMPLE_REF.finditer(v):
                full_ref = match.group(1)
                name = full_ref.split('.')[0]
                if name not in seen and name not in _HBS_KEYWORDS:
                    seen.add(name)
                    result.append(name)
            for match in _BLOCK_REF.finditer(v):
                name = match.group(1)
                if name not in seen and name not in _HBS_KEYWORDS:
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


def _render_value(value: Any, context: dict[str, Any]) -> Any:
    """Recursively walk a decoded JSON value, rendering strings through Handlebars.

    Unresolved variable names should already be present in the context as their
    literal ``<<name>>`` text so that Handlebars preserves them.
    """
    if isinstance(value, str):
        if not has_references(value):
            # Unescape \<< to << for non-reference strings.
            return value.replace('\\<<', '<<')
        return render_once(value, context)
    if isinstance(value, dict):
        return {k: _render_value(v, context) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, list):
        return [_render_value(v, context) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value


def _unescape_serialized(serialized: str) -> str:
    r"""Unescape ``\<<`` to ``<<`` in a JSON-serialized string.

    In JSON encoding, a literal backslash is ``\\``, so ``\<<`` in user content
    appears as ``\\<<`` in the serialized JSON.
    """
    return serialized.replace('\\\\<<', '<<')
