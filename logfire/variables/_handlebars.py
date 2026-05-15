from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Any


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
        'which is only installed by the `logfire[variables]` extra on Python 3.10 and later.'
    )


def ensure_handlebars_available() -> None:
    """Raise a helpful error if pydantic-handlebars is unavailable."""
    get_handlebars_renderer()


@cache
def get_handlebars_renderer() -> tuple[type[str], Callable[..., str]]:
    """Return pydantic-handlebars SafeString and render, or raise a helpful error."""
    try:
        from pydantic_handlebars import SafeString, render
    except ImportError as exc:  # pragma: no cover
        raise _dependency_error() from exc
    return SafeString, render


@cache
def _get_template_compatibility_checker() -> Callable[[list[str], dict[str, Any]], Any]:
    """Return pydantic-handlebars schema compatibility checker, or raise a helpful error."""
    try:
        from pydantic_handlebars import check_template_compatibility as _check_template_compatibility
    except ImportError as exc:  # pragma: no cover
        raise _dependency_error() from exc
    return _check_template_compatibility


def check_template_compatibility(templates: list[str], schema: dict[str, Any]) -> Any:
    """Run pydantic-handlebars schema compatibility checking."""
    return _get_template_compatibility_checker()(templates, schema)
