from __future__ import annotations

import ast
import builtins
import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from logfire import Logfire
from logfire._internal.ast_utils import ArgumentsInspector
from logfire._internal.utils import handle_internal_errors


def instrument_print(logfire_instance: Logfire):
    """Instruments the built-in `print` function to send logs to **Logfire**.

    Args:
        logfire_instance: The Logfire instance to use.
    """
    original_print = builtins.print

    def _instrumented_print(*args: Any, sep: str | None = None, **kwargs: Any) -> None:
        """The wrapper function that will replace builtins.print."""
        original_print(*args, sep=sep, **kwargs)
        if not args:
            return

        if sep is None:
            sep = ' '

        with handle_internal_errors:
            frame = inspect.currentframe()
            assert frame, 'Could not get current frame'
            frame = frame.f_back
            assert frame, 'Could not get caller frame'

            inspector = PrintArgumentsInspector(frame)
            call_node = inspector.get_call_node()
            if call_node is None:
                return

            attributes = _get_magic_args_dict(call_node, args)
            attributes['logfire.msg'] = sep.join(str(arg) for arg in args)
            logfire_instance.log(
                'info',
                'print() called',
                attributes=attributes,
            )

    builtins.print = _instrumented_print

    @contextmanager
    def uninstrument_context():
        # The user isn't required (or even expected) to use this context manager,
        # which is why the instrumenting and patching has already happened before this point.
        # It exists mostly for tests, and just in case users want it.
        try:
            yield
        finally:
            builtins.print = original_print

    return uninstrument_context


def _get_magic_args_dict(call_node: ast.Call, args: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    ast_args = list(call_node.args)
    runtime_args = list(args)

    def _process_end():
        """Helper to process non-starred args from the end of the lists."""
        while ast_args and not isinstance(ast_args[-1], ast.Starred):
            result[ast.unparse(ast_args.pop())] = runtime_args.pop()

    _process_end()

    if not runtime_args:
        return result

    ast_args.reverse()
    runtime_args.reverse()
    _process_end()

    runtime_args.reverse()

    if len(ast_args) == 1:
        assert isinstance(ast_args[0], ast.Starred)
        key = ast.unparse(ast_args[0].value)
    else:
        key = '*args'

    result[key] = tuple(runtime_args)
    return result


class PrintArgumentsInspector(ArgumentsInspector):
    def heuristic_main_nodes(self) -> Iterator[ast.AST]:
        yield from self.ex.statements

    def heuristic_call_node_filter(self, node: ast.Call) -> bool:
        return bool(node.args)

    def warn_inspect_arguments_middle(self):
        return 'Using `logfire.print_args` as the fallback attribute key for all print arguments.'
