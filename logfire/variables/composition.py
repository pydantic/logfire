"""Variable composition: expand <<variable_name>> references in serialized values.

This module provides pure functions for expanding variable references in serialized
JSON strings. References use the <<variable_name>> syntax and are expanded by literal
string substitution before Pydantic deserialization.

The composition logic is shared between the SDK (client-side expansion) and the
backend OFREP endpoint (server-side expansion).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

__all__ = (
    'REFERENCE_PATTERN',
    'MAX_COMPOSITION_DEPTH',
    'VariableCompositionError',
    'VariableCompositionCycleError',
    'ComposedReference',
    'expand_references',
    'find_references',
)

# Matches <<valid_python_identifier>> but not \<<...>>
REFERENCE_PATTERN = re.compile(r'(?<!\\)<<([a-zA-Z_][a-zA-Z0-9_]*)>>')

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
ResolveFn = Callable[[str], tuple[str | None, str | None, int | None, str]]


def expand_references(
    serialized_value: str,
    variable_name: str,
    resolve_fn: ResolveFn,
    *,
    _visited: frozenset[str] = frozenset(),
    _depth: int = 0,
) -> tuple[str, list[ComposedReference]]:
    """Expand <<var>> references in a serialized variable value.

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

    def replace_match(match: re.Match[str]) -> str:
        ref_name = match.group(1)

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
            return match.group(0)  # leave <<var>> unexpanded

        # JSON-decode the referenced value. It must be a string for composition.
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
            return match.group(0)

        if not isinstance(raw_value, str):
            composed.append(
                ComposedReference(
                    name=ref_name,
                    value=None,
                    label=ref_label,
                    version=ref_version,
                    reason=ref_reason,
                    error=(
                        f"Referenced variable '{ref_name}' resolved to a {type(raw_value).__name__}, "
                        f'not a string. Only string variables can be used as snippets.'
                    ),
                )
            )
            return match.group(0)

        # Recursively expand references in the referenced value
        try:
            expanded_serialized, nested_composed = expand_references(
                json.dumps(raw_value),
                ref_name,
                resolve_fn,
                _visited=visited,
                _depth=_depth + 1,
            )
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
            return match.group(0)

        expanded_str = json.loads(expanded_serialized)

        composed.append(
            ComposedReference(
                name=ref_name,
                value=expanded_str,
                label=ref_label,
                version=ref_version,
                reason=ref_reason,
                composed_from=nested_composed,
            )
        )

        # Return JSON-escaped content for embedding in the parent JSON string
        return json.dumps(expanded_str)[1:-1]

    expanded = REFERENCE_PATTERN.sub(replace_match, serialized_value)

    # Unescape \<< to << in the serialized JSON.
    # In JSON encoding, a literal backslash is \\, so \<< in user content
    # appears as \\<< in the serialized JSON (two backslash chars + <<).
    expanded = expanded.replace('\\\\<<', '<<')

    return expanded, composed


def find_references(serialized_value: str) -> list[str]:
    """Find all <<variable_name>> references in a serialized value.

    Args:
        serialized_value: The raw JSON-serialized variable value to scan.

    Returns:
        List of unique variable names referenced, in order of first occurrence.
    """
    seen: set[str] = set()
    result: list[str] = []
    for match in REFERENCE_PATTERN.finditer(serialized_value):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result
