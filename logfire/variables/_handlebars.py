from __future__ import annotations

from collections.abc import Callable
from functools import cache, lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic_handlebars import CompiledTemplate, HandlebarsEnvironment


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


@lru_cache(maxsize=1024)
def compile_composition_template(source: str) -> CompiledTemplate:
    """Return a cached `CompiledTemplate` for *source* compiled with composition delimiters.

    Managed-variable values are typically stable across many resolutions —
    the same `@{...}@` template is rendered once per `get()` call. Caching
    the parsed program avoids reparsing each time
    `HandlebarsEnvironment.render(source, context)` is called (which by
    itself does the parse on every call). 1024 is large enough for any
    realistic number of distinct templates in a single process while
    staying bounded for long-running workers.
    """
    return get_environment().compile(source)


@cache
def _extract_dependencies_fn() -> Callable[..., set[str]]:
    """Cached lookup of `pydantic_handlebars.extract_dependencies`."""
    try:
        from pydantic_handlebars import extract_dependencies
    except ModuleNotFoundError as exc:  # pragma: no cover
        if exc.name == 'pydantic_handlebars':
            raise _dependency_error() from exc
        raise
    return extract_dependencies


def extract_composition_dependencies(template: str) -> set[str]:
    """Return the top-level `@{name}@` references in *template*.

    Delegates to `pydantic_handlebars.extract_dependencies` configured for
    the composition delimiters, so block helpers / dotted paths / etc. are
    handled AST-correctly.
    """
    return _extract_dependencies_fn()(template, open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM)


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
