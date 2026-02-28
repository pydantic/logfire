"""Pure Python implementation of the Handlebars template language."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from logfire.handlebars._compiler import Compiler, HelperFunc, HelperOptions, Scope
from logfire.handlebars._environment import HandlebarsEnvironment
from logfire.handlebars._exceptions import HandlebarsError, HandlebarsParseError, HandlebarsRuntimeError
from logfire.handlebars._utils import SafeString, escape_expression

__all__ = [
    'compile',
    'render',
    'SafeString',
    'HandlebarsError',
    'HandlebarsParseError',
    'HandlebarsRuntimeError',
    'HandlebarsEnvironment',
    'HelperFunc',
    'HelperOptions',
    'Compiler',
    'Scope',
    'escape_expression',
]

# Default environment for module-level functions
_default_env = HandlebarsEnvironment()


class _CompiledTemplate:
    """A compiled Handlebars template."""

    def __init__(self, fn: Callable[..., str]) -> None:
        self._fn = fn

    def __call__(self, context: dict[str, Any] | None = None) -> str:
        """Render the template with the given context."""
        return self._fn(context if context is not None else {})


def render(source: str, context: dict[str, Any] | None = None) -> str:
    """Render a Handlebars template string with the given context.

    This is a convenience function that uses a default environment with
    all built-in helpers registered.

    Args:
        source: The Handlebars template string.
        context: The data context for rendering.

    Returns:
        The rendered string.

    Example:
        ```python
        result = render('Hello {{name}}!', {'name': 'World'})
        assert result == 'Hello World!'
        ```
    """
    return _default_env.render(source, context if context is not None else {})


def compile(source: str) -> _CompiledTemplate:
    """Compile a Handlebars template string into a reusable callable.

    Args:
        source: The Handlebars template string.

    Returns:
        A callable that takes a context dict and returns a rendered string.

    Example:
        ```python
        template = compile('Hello {{name}}!')
        result = template({'name': 'World'})
        assert result == 'Hello World!'
        ```
    """
    return _CompiledTemplate(_default_env.compile(source))
