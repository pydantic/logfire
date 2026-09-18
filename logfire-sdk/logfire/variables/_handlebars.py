from __future__ import annotations

from functools import cache, lru_cache

from pydantic_handlebars import CompiledTemplate, HandlebarsEnvironment, extract_dependencies

# The reference-syntax composition pass consumes ``@{...}@`` placeholders and
# leaves any ``{{...}}`` runtime placeholders untouched for a subsequent
# rendering pass (handled by ``TemplateVariable.get(inputs)``).
COMPOSITION_OPEN_DELIM = '@{'
COMPOSITION_CLOSE_DELIM = '}@'


@cache
def get_environment(strict: bool = False) -> HandlebarsEnvironment:
    """Return a cached `HandlebarsEnvironment` configured for `@{...}@` composition.

    Uses non-default delimiters so the composition pass leaves any
    `{{...}}` runtime placeholders in the template as plain content; a
    subsequent render pass with the default delimiters consumes those.

    When *strict* is `True`, the environment raises `HandlebarsRuntimeError`
    for any `@{ref}@` (or dotted `@{ref.field}@`) that doesn't resolve, rather
    than rendering it as an empty string. Composition uses the strict
    environment for provider/override values (so a missing reference triggers a
    fall back to the code default) and the non-strict one for the code default
    itself (the lenient last resort, where a missing reference renders empty).
    """
    return HandlebarsEnvironment(open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM, strict=strict)


@cache
def get_runtime_environment() -> HandlebarsEnvironment:
    """Return a cached default-delimiter `HandlebarsEnvironment` for `{{...}}` rendering.

    Used by `TemplateVariable.get(inputs)` to render the post-composition
    serialized value against the provided inputs.
    """
    return HandlebarsEnvironment()


@lru_cache(maxsize=1024)
def compile_composition_template(source: str, strict: bool = False) -> CompiledTemplate:
    """Return a cached `CompiledTemplate` for *source* under composition delimiters.

    Managed-variable values are typically stable across many resolutions, so
    caching the parsed program lets `Variable._resolve` skip the parse on
    every `get()` call. 1024 is large enough for any realistic number of
    distinct templates in a single process while staying bounded for
    long-running workers. Same rationale for `compile_runtime_template`.

    *strict* selects the strict vs non-strict composition environment (see
    `get_environment`); the two are cached separately.
    """
    return get_environment(strict).compile(source)


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
        extract_dependencies(template, open_delim=COMPOSITION_OPEN_DELIM, close_delim=COMPOSITION_CLOSE_DELIM)
    )
