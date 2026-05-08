"""Template validation: check ``{{field}}`` references against ``template_inputs_schema``.

This module validates that Handlebars ``{{field}}`` references in template variable
values (including composed ``@{ref}@`` dependencies) match the declared
``template_inputs_schema``. It uses ``pydantic_handlebars.check_template_compatibility``
for full AST-based schema checking (nested paths, block scopes, helpers).

It also provides cycle detection for composition graphs.

Used by both the SDK and the backend for pre-write validation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from logfire.variables._handlebars import check_template_compatibility
from logfire.variables.composition import find_references

__all__ = (
    'TemplateFieldIssue',
    'TemplateValidationResult',
    'validate_template_composition',
    'detect_composition_cycles',
    'find_template_fields',
)

# Matches {{identifier}} — simple Handlebars variable references.
# Excludes block helpers ({{#if}}), closing tags ({{/if}}), partials ({{> name}}),
# comments ({{! text}}), and triple-stache ({{{raw}}}).
TEMPLATE_FIELD_PATTERN = re.compile(r'\{\{\s*([a-zA-Z_]\w*)\s*\}\}')


@dataclass
class TemplateFieldIssue:
    """A ``{{field}}`` reference that doesn't match the variable's ``template_inputs_schema``."""

    field_name: str
    """The template field name (e.g., ``user_name`` from ``{{user_name}}``)."""
    found_in_variable: str
    """Name of the variable whose value contains this field reference."""
    found_in_label: str | None
    """Label of the value where the field was found, or ``None`` for the latest version."""
    reference_path: list[str]
    """Composition path from the root variable to ``found_in_variable``."""


@dataclass
class TemplateValidationResult:
    """Result of template composition validation."""

    issues: list[TemplateFieldIssue] = field(default_factory=list[TemplateFieldIssue])


def find_template_fields(text: str) -> set[str]:
    """Find all ``{{field}}`` references in a string.

    Returns:
        Set of field names found in the text.
    """
    return set(TEMPLATE_FIELD_PATTERN.findall(text))


def _extract_template_strings(serialized_json: str) -> list[str]:
    """Extract all string values from serialized JSON that contain ``{{...}}`` templates."""
    try:
        decoded = json.loads(serialized_json)
    except (json.JSONDecodeError, TypeError):
        # If it's not valid JSON, treat the raw string as a potential template
        if '{{' in serialized_json:
            return [serialized_json]
        return []
    return _collect_template_strings(decoded)


def _collect_template_strings(value: Any) -> list[str]:
    """Recursively collect strings containing ``{{...}}`` from a decoded JSON value."""
    if isinstance(value, str):
        return [value] if '{{' in value else []
    if isinstance(value, dict):
        result: list[str] = []
        for v in value.values():  # pyright: ignore[reportUnknownVariableType]
            result.extend(_collect_template_strings(v))
        return result
    if isinstance(value, list):
        result = []
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            result.extend(_collect_template_strings(item))
        return result
    return []


def validate_template_composition(
    variable_name: str,
    template_inputs_schema: dict[str, Any],
    get_all_serialized_values: Callable[[str], dict[str | None, str]],
) -> TemplateValidationResult:
    """Validate that ``{{field}}`` references in a template variable match its schema.

    Walks the composition graph starting from *variable_name*, collecting all
    template strings from the variable's values and its ``@{ref}@`` dependencies,
    then uses AST-based schema checking via ``check_template_compatibility`` to
    find incompatible field references.

    Args:
        variable_name: Name of the template variable to validate.
        template_inputs_schema: JSON Schema describing the expected template inputs.
        get_all_serialized_values: Function that returns ``{label_or_none: serialized_json}``
            for any variable name.  ``None`` key represents the latest version.

    Returns:
        A :class:`TemplateValidationResult` with any issues found.
    """
    issues: list[TemplateFieldIssue] = []
    seen_issues: set[tuple[str, str, str | None]] = set()

    def _collect(name: str, path: list[str], visited: frozenset[str]) -> None:
        if name in visited:
            return
        visited = visited | {name}

        for label, serialized_value in get_all_serialized_values(name).items():
            templates = _extract_template_strings(serialized_value)
            if not templates:
                for ref in find_references(serialized_value):
                    _collect(ref, path + [ref], visited)
                continue

            result = check_template_compatibility(templates, template_inputs_schema)
            for issue in result.issues:
                if issue.severity != 'error':
                    continue
                key = (issue.field_path, name, label)
                if key not in seen_issues:
                    seen_issues.add(key)
                    issues.append(
                        TemplateFieldIssue(
                            field_name=issue.field_path,
                            found_in_variable=name,
                            found_in_label=label,
                            reference_path=list(path),
                        )
                    )

            for ref in find_references(serialized_value):
                _collect(ref, path + [ref], visited)

    _collect(variable_name, [], frozenset())

    return TemplateValidationResult(issues=issues)


def detect_composition_cycles(
    variable_name: str,
    new_references: set[str],
    get_all_references: Callable[[str], set[str]],
) -> list[str] | None:
    """Check if adding *new_references* to *variable_name* would create a cycle.

    Args:
        variable_name: The variable being updated.
        new_references: Set of variable names directly referenced by the new value.
        get_all_references: Function that returns all variable names referenced by
            any value of the given variable name.

    Returns:
        The cycle path (e.g., ``['A', 'B', 'C', 'A']``) if a cycle is detected,
        or ``None`` if no cycle exists.
    """
    for ref in sorted(new_references):  # sort for deterministic results
        path = _find_cycle(variable_name, ref, get_all_references, frozenset())
        if path is not None:
            return path
    return None


def _find_cycle(
    target: str,
    current: str,
    get_all_references: Callable[[str], set[str]],
    visited: frozenset[str],
    path: list[str] | None = None,
) -> list[str] | None:
    """DFS to find a path from *current* back to *target*."""
    if path is None:
        path = [target, current]

    if current == target:
        return path

    if current in visited:
        return None

    visited = visited | {current}

    for ref in sorted(get_all_references(current)):  # sort for deterministic results
        result = _find_cycle(target, ref, get_all_references, visited, path + [ref])
        if result is not None:
            return result

    return None
