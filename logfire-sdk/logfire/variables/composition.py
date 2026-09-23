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
    malformed value) are *soft*: under non-strict composition the missing reference renders
    as an empty string (interpolation) or falsy (control position), exactly like standard
    Handlebars, and the rest of the value still renders, so the partially-composed value is
    usable. (Under *strict* composition the renderer raises instead, before any
    `ComposedReference` is returned — strict callers learn of the miss from the exception.)
    Always `False` when *error* is `None`.
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
    strict: bool = False,
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
            continue

        # Recursively expand references within the resolved value.
        nested_composed: list[ComposedReference] = []
        if has_references(ref_serialized):
            try:
                expanded_serialized, nested_composed = expand_references(
                    ref_serialized,
                    ref_name,
                    resolve_fn,
                    strict=strict,
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

    # A fatal nested failure (a cycle or depth overflow) means the value can't be
    # meaningfully composed, so skip rendering and return the un-rendered value with the
    # `composed` tree intact. The caller discards the value and falls back, but inspects
    # `composed` for the failure attribution. Skipping the render also avoids a *strict*
    # render raising `HandlebarsRuntimeError` on the now-absent cyclic key, which would
    # otherwise mask the structural error behind a generic missing-reference one.
    if _has_fatal_composition_error(composed):
        return serialized_value, composed

    # Unresolved names are intentionally left ABSENT from `context`. Under
    # non-strict rendering Handlebars then treats them as missing — `@{name}@`
    # interpolation renders as an empty string and `@{#if name}@` takes the
    # else branch — matching standard Handlebars. Under *strict* rendering the
    # renderer raises `HandlebarsRuntimeError` for the missing key instead, so
    # the caller can fall back to the code default.
    rendered = _render_value(decoded, context, strict=strict)

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


def _has_fatal_composition_error(composed: list[ComposedReference]) -> bool:
    """Return whether *composed* (recursively) contains a fatal failure (cycle / depth overflow)."""
    for ref in composed:
        if ref.error is not None and ref.fatal:
            return True
        if _has_fatal_composition_error(ref.composed_from):
            return True
    return False


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
    from logfire.variables._handlebars import extract_composition_dependencies

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


def _render_value(value: Any, context: dict[str, Any], *, strict: bool) -> Any:
    """Recursively walk a decoded JSON value, rendering strings through Handlebars.

    Unresolved variable names are absent from *context*. Under non-strict
    rendering the renderer treats them as missing — `@{name}@` renders empty
    and `@{#if name}@` takes the else branch, matching standard Handlebars.
    Under *strict* rendering the renderer instead raises
    `HandlebarsRuntimeError`, which the caller turns into a fall back to the
    code default.
    Strings without any composition delimiter pass straight through; strings
    that contain `@{` (escaped or not) route through the renderer, which
    handles the backslash-parity escape rule.
    """
    if isinstance(value, str):
        if not has_references(value):
            return value

        from logfire.variables._handlebars import compile_composition_template

        return compile_composition_template(value, strict).render(context)
    if isinstance(value, dict):
        return {
            k: _render_value(v, context, strict=strict)
            for k, v in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, list):
        return [_render_value(v, context, strict=strict) for v in value]  # pyright: ignore[reportUnknownVariableType]
    return value
