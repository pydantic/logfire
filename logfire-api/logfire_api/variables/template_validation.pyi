from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

__all__ = ['TemplateFieldIssue', 'TemplateValidationResult', 'validate_template_composition', 'detect_composition_cycles', 'extract_template_strings']

@dataclass
class TemplateFieldIssue:
    """A `{{field}}` reference that doesn't match a template variable's `template_inputs_schema`."""
    field_name: str
    found_in_variable: str
    found_in_label: str | None
    reference_path: list[str]
    root_variable: str

@dataclass
class TemplateValidationResult:
    """Result of template composition validation."""
    issues: list[TemplateFieldIssue] = field(default_factory=list[TemplateFieldIssue])

def extract_template_strings(serialized_json: str) -> list[str]:
    """Extract all string values from serialized JSON that contain `{{...}}` templates."""
def validate_template_composition(variable_name: str, template_inputs_schema: dict[str, Any], get_all_serialized_values: Callable[[str], dict[str | None, str]]) -> TemplateValidationResult:
    """Validate that `{{field}}` references in a template variable match its schema.

    Walks the composition graph starting from *variable_name*, collecting all
    template strings from the variable's values and its `@{ref}@` dependencies,
    then uses AST-based schema checking via `check_template_compatibility` to
    find incompatible field references.

    Args:
        variable_name: Name of the template variable to validate.
        template_inputs_schema: JSON Schema describing the expected template inputs.
        get_all_serialized_values: Function that returns `{label_or_none: serialized_json}`
            for any variable name. Each key is the label that serves that value; the
            `None` key is the code default, and `'latest'` is the latest version.

    Returns:
        A :class:`TemplateValidationResult` with any issues found.
    """
def detect_composition_cycles(variable_name: str, new_references: set[str], get_all_references: Callable[[str], set[str]]) -> list[str] | None:
    """Check if adding *new_references* to *variable_name* would create a cycle.

    Args:
        variable_name: The variable being updated.
        new_references: Set of variable names directly referenced by the new value.
        get_all_references: Function that returns all variable names referenced by
            any value of the given variable name.

    Returns:
        The cycle path (e.g., `['A', 'B', 'C', 'A']`) if a cycle is detected,
        or `None` if no cycle exists.
    """
