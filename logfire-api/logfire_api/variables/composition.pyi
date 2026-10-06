from collections.abc import Callable
from dataclasses import dataclass, field
from logfire.variables.abstract import ResolutionReason

__all__ = ['MAX_COMPOSITION_DEPTH', 'VariableCompositionError', 'VariableCompositionCycleError', 'ComposedReference', 'expand_references', 'find_references', 'find_references_and_errors', 'has_references']

MAX_COMPOSITION_DEPTH: int

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
    value: str | None
    label: str | None
    version: int | None
    reason: ResolutionReason
    error: str | None = ...
    composed_from: list[ComposedReference] = field(default_factory=list['ComposedReference'])
    fatal: bool = ...
ResolveFn = Callable[[str], tuple[str | None, str | None, int | None, ResolutionReason]]

def has_references(serialized_value: str) -> bool:
    """Quick check for any `@{` in a serialized value.

    Returns `True` whenever the string contains the composition open
    delimiter, regardless of preceding backslashes. The actual
    escape-or-real decision is made by `pydantic_handlebars` at render time
    — distinguishing an escaped `\\@{x}@` from an unescaped `@{x}@` here
    would require a variable-width lookbehind (the renderer counts
    backslash parity to match Handlebars.js semantics) and is unnecessary:
    `extract_composition_dependencies` returns an empty set for escaped-only
    strings, and the renderer correctly leaves the literal text in place.
    """
def expand_references(serialized_value: str, variable_name: str, resolve_fn: ResolveFn, *, strict: bool = False, _visited: tuple[str, ...] = (), _depth: int = 0) -> tuple[str, list[ComposedReference]]:
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
        strict: When `True`, an unresolved `@{ref}@` / `@{ref.field}@` raises
            `HandlebarsRuntimeError` instead of rendering as an empty string.
            The SDK composes provider/override values strictly (so a missing
            reference falls back to the code default) and the code default
            non-strictly (the lenient last resort). Nested expansions inherit
            this flag.
        _visited: Internal - ordered variable names in the current expansion chain.
        _depth: Internal - current recursion depth.

    Returns:
        tuple of (expanded_serialized_value, list_of_composed_references).

    Raises:
        VariableCompositionError: If max depth is exceeded.
        VariableCompositionCycleError: If a circular reference is detected.
        HandlebarsRuntimeError: Under *strict*, if a reference is unresolved.
    """
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
