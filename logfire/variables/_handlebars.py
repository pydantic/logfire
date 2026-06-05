from __future__ import annotations

from functools import cache, lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from types import ModuleType

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
except ImportError:
    _ImportedHandlebarsError = _FallbackHandlebarsError

HandlebarsError: type[Exception] = _ImportedHandlebarsError


class HandlebarsDependencyError(ImportError):
    """Raised when a Handlebars feature is used without pydantic-handlebars installed."""


@cache
def _pydantic_handlebars() -> ModuleType:
    """Return the cached `pydantic_handlebars` module, or raise a helpful error.

    The import is cached so every accessor below — `get_environment`,
    `compile_composition_template`, `extract_composition_dependencies`,
    etc. — can grab attributes off the returned module without each one
    repeating its own try/except dance. Failure surfaces once, here, with
    the install hint.
    """
    try:
        import pydantic_handlebars
    except ModuleNotFoundError as exc:
        # Only reframe the error if it's *pydantic_handlebars itself* that's
        # missing. A future version pulling in a new transitive dep that
        # isn't installed would raise `ModuleNotFoundError` with a different
        # `exc.name`, and the user wants to see *that* name in the message
        # rather than a misleading "install pydantic-handlebars" hint.
        if exc.name != 'pydantic_handlebars':
            raise
        raise HandlebarsDependencyError(
            'Handlebars template rendering requires the `pydantic-handlebars` package, '
            'which is installed by the `logfire[variables]` extra.'
        ) from exc
    return pydantic_handlebars


def ensure_handlebars_available() -> None:
    """Raise a helpful error if pydantic-handlebars is unavailable."""
    _pydantic_handlebars()


@cache
def get_environment() -> HandlebarsEnvironment:
    """Return a cached `HandlebarsEnvironment` configured for `@{...}@` composition.

    Uses non-default delimiters so the composition pass leaves any
    `{{...}}` runtime placeholders in the template as plain content; a
    subsequent render pass with the default delimiters consumes those.
    """
    return _pydantic_handlebars().HandlebarsEnvironment(
        open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM
    )


@cache
def get_runtime_environment() -> HandlebarsEnvironment:
    """Return a cached default-delimiter `HandlebarsEnvironment` for `{{...}}` rendering.

    Used by `TemplateVariable.get(inputs)` to render the post-composition
    serialized value against the provided inputs.
    """
    return _pydantic_handlebars().HandlebarsEnvironment()


@cache
def get_safe_string_cls() -> type[str]:
    """Return `pydantic_handlebars.SafeString`.

    Context values are wrapped in it so HTML auto-escaping (off by default
    but enableable) doesn't munge them.
    """
    return _pydantic_handlebars().SafeString


@lru_cache(maxsize=1024)
def compile_composition_template(source: str) -> CompiledTemplate:
    """Return a cached `CompiledTemplate` for *source* under composition delimiters.

    Managed-variable values are typically stable across many resolutions, so
    caching the parsed program lets `Variable._resolve` skip the parse on
    every `get()` call. 1024 is large enough for any realistic number of
    distinct templates in a single process while staying bounded for
    long-running workers. Same rationale for `compile_runtime_template`.
    """
    return get_environment().compile(source)


@lru_cache(maxsize=1024)
def compile_runtime_template(source: str) -> CompiledTemplate:
    """Return a cached `CompiledTemplate` for *source* under default `{{...}}` delimiters."""
    return get_runtime_environment().compile(source)


@lru_cache(maxsize=1024)
def extract_composition_dependencies(template: str) -> frozenset[str]:
    """Return the top-level `@{name}@` references in *template*.

    Cached because cycle / reference validation runs over the same template
    strings multiple times per push or sync. The underlying delegation goes
    to `pydantic_handlebars.extract_dependencies` configured for the
    composition delimiters, so block helpers, dotted paths, and helper
    sub-expressions are handled AST-correctly. A `frozenset` is returned so the
    cached value can't be mutated by a caller and poison later lookups.
    """
    return frozenset(
        _pydantic_handlebars().extract_dependencies(
            template, open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM
        )
    )


def check_template_compatibility(templates: list[str], schema: dict[str, Any]) -> Any:
    """Run pydantic-handlebars schema compatibility checking."""
    return _pydantic_handlebars().check_template_compatibility(templates, schema)
