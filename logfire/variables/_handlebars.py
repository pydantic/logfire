from __future__ import annotations

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic_handlebars import HandlebarsEnvironment


# The reference-syntax composition pass consumes ``@{...}@`` placeholders and
# leaves any ``{{...}}`` runtime placeholders untouched for a subsequent
# rendering pass (handled by ``TemplateVariable.get(inputs)``).
COMPOSITION_OPEN_DELIM = '@{'
COMPOSITION_CLOSE_DELIM = '}@'


class _FallbackHandlebarsError(Exception):
    """Fallback exception class used when pydantic-handlebars is unavailable."""


try:
    from pydantic_handlebars import HandlebarsError as _ImportedHandlebarsError
except ImportError:  # pragma: no cover
    _ImportedHandlebarsError = _FallbackHandlebarsError

HandlebarsError: type[Exception] = _ImportedHandlebarsError


class HandlebarsDependencyError(ImportError):
    """Raised when a Handlebars feature is used without pydantic-handlebars installed."""


def _dependency_error() -> HandlebarsDependencyError:
    return HandlebarsDependencyError(
        'Handlebars template rendering requires the `pydantic-handlebars` package, '
        'which is installed by the `logfire[variables]` extra.'
    )


def ensure_handlebars_available() -> None:
    """Raise a helpful error if pydantic-handlebars is unavailable."""
    get_environment()


@cache
def get_environment() -> HandlebarsEnvironment:
    """Return a cached `HandlebarsEnvironment` configured for `@{...}@` composition.

    Uses non-default delimiters so the composition pass leaves any
    `{{...}}` runtime placeholders in the template as plain content; a
    subsequent render pass with the default delimiters consumes those.
    """
    try:
        from pydantic_handlebars import HandlebarsEnvironment
    except ModuleNotFoundError as exc:  # pragma: no cover
        if exc.name == 'pydantic_handlebars':
            raise _dependency_error() from exc
        raise
    return HandlebarsEnvironment(open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM)


@cache
def get_handlebars_renderer() -> tuple[type[str], Callable[..., str]]:
    """Return pydantic-handlebars SafeString and module-level render function."""
    try:
        from pydantic_handlebars import SafeString, render
    except ModuleNotFoundError as exc:  # pragma: no cover
        if exc.name == 'pydantic_handlebars':
            raise _dependency_error() from exc
        raise
    return SafeString, render


def extract_composition_dependencies(template: str) -> set[str]:
    """Return the top-level `@{name}@` references in *template*.

    Delegates to `pydantic_handlebars.extract_dependencies` configured for
    the composition delimiters, so block helpers / dotted paths / etc. are
    handled AST-correctly. When `pydantic-handlebars` is unavailable (i.e.
    Python 3.9, where the `[variables]` extra omits the dependency), falls
    back to a regex-based approximation that recognises simple
    `@{name}@` / `@{name.field}@` / `@{#helper name}@` forms — sufficient
    for the cycle/reference checks the SDK runs at sync time, but not for
    actual composition rendering (which raises on Python 3.9).
    """
    try:
        from pydantic_handlebars import extract_dependencies
    except ModuleNotFoundError as exc:
        if exc.name == 'pydantic_handlebars':
            return _fallback_extract_dependencies(template)
        raise  # pragma: no cover
    return extract_dependencies(template, open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM)


# Conservative fallback regexes used only when `pydantic-handlebars` is not
# installed (Python 3.9): match simple identifiers / dotted-paths and the
# first identifier inside `@{#helper x ...}@` headers.
_FALLBACK_SIMPLE_REF = re.compile(r'(?<!\\)@\{([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}@')
_FALLBACK_BLOCK_REF = re.compile(r'(?<!\\)@\{[#~]\s*\w+\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:[.\s}/])')
# Names that look like context references but are Handlebars built-ins.
_FALLBACK_RESERVED = frozenset({'this', 'else', 'if', 'unless', 'each', 'with', 'lookup', 'log'})


def _fallback_extract_dependencies(template: str) -> set[str]:
    refs: set[str] = set()
    for match in _FALLBACK_SIMPLE_REF.finditer(template):
        head = match.group(1).split('.', 1)[0]
        if head not in _FALLBACK_RESERVED:
            refs.add(head)
    for match in _FALLBACK_BLOCK_REF.finditer(template):
        name = match.group(1)
        if name not in _FALLBACK_RESERVED:
            refs.add(name)
    return refs


@cache
def _get_template_compatibility_checker() -> Callable[[list[str], dict[str, Any]], Any]:
    """Return pydantic-handlebars schema compatibility checker, or raise a helpful error."""
    try:
        from pydantic_handlebars import check_template_compatibility as _check_template_compatibility
    except ModuleNotFoundError as exc:  # pragma: no cover
        if exc.name == 'pydantic_handlebars':
            raise _dependency_error() from exc
        raise
    return _check_template_compatibility


def check_template_compatibility(templates: list[str], schema: dict[str, Any]) -> Any:
    """Run pydantic-handlebars schema compatibility checking."""
    return _get_template_compatibility_checker()(templates, schema)
