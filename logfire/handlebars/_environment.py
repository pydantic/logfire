"""HandlebarsEnvironment class for managing helpers and rendering."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, overload

from logfire.handlebars._compiler import Compiler
from logfire.handlebars._helpers import get_default_helpers
from logfire.handlebars._parser import parse

F = TypeVar('F', bound=Callable[..., Any])


class HandlebarsEnvironment:
    """An environment for rendering Handlebars templates with custom helpers.

    The environment manages a set of helpers (both built-in and user-registered)
    and provides methods for compiling and rendering templates.

    Example:
        ```python
        env = HandlebarsEnvironment()


        @env.helper
        def shout(value):
            return str(value).upper() + '!!!'


        result = env.render('{{shout name}}', {'name': 'world'})
        assert result == 'WORLD!!!'
        ```
    """

    def __init__(self) -> None:
        self._helpers: dict[str, Any] = get_default_helpers()

    @overload
    def helper(self, fn: F) -> F: ...  # pragma: no cover

    @overload
    def helper(self, fn: str) -> Callable[[F], F]: ...  # pragma: no cover

    def helper(self, fn: F | str) -> F | Callable[[F], F]:
        """Register a helper function.

        Can be used as a decorator (with or without a name argument):

        ```python
        @env.helper
        def my_helper(value):
            return str(value).upper()


        @env.helper('custom-name')
        def my_helper(value):
            return str(value).upper()
        ```

        Args:
            fn: The helper function, or a name string for use as a decorator factory.

        Returns:
            The registered function, or a decorator.
        """
        if isinstance(fn, str):
            name = fn

            def decorator(func: F) -> F:
                self._helpers[name] = func
                return func

            return decorator
        else:
            self._helpers[fn.__name__] = fn
            return fn

    def register_helper(self, name: str, fn: Any) -> None:
        """Register a helper function with an explicit name.

        Args:
            name: The name to register the helper under.
            fn: The helper function.
        """
        self._helpers[name] = fn

    def unregister_helper(self, name: str) -> None:
        """Unregister a helper by name.

        Args:
            name: The name of the helper to remove.

        Raises:
            KeyError: If the helper is not registered.
        """
        if name not in self._helpers:
            raise KeyError(f'Helper not found: {name}')
        del self._helpers[name]

    def compile(self, source: str) -> Callable[[Any], str]:
        """Compile a template string into a reusable callable.

        Args:
            source: The Handlebars template string.

        Returns:
            A callable that takes a context dict and returns a rendered string.
        """
        program = parse(source)
        helpers = dict(self._helpers)

        def template(context: Any = None) -> str:
            ctx: Any = context if context is not None else {}
            compiler = Compiler(helpers=helpers)
            return compiler.render(program, ctx)

        return template

    def render(self, source: str, context: Any = None) -> str:
        """Render a template string with the given context.

        Args:
            source: The Handlebars template string.
            context: The data context for rendering.

        Returns:
            The rendered string.
        """
        template = self.compile(source)
        return template(context if context is not None else {})
