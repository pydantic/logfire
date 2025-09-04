from __future__ import annotations

import ast
import builtins
import functools
import inspect
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Any

import executing

from logfire import Logfire
from logfire._internal.ast_utils import ArgumentsInspector, get_node_source_text
from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.scrubbing import MessageValueCleaner
from logfire._internal.utils import handle_internal_errors

FALLBACK_ATTRIBUTE_KEY = 'logfire.print_args'


def instrument_print(logfire_instance: Logfire) -> AbstractContextManager[None]:
    """Instruments the built-in `print` function to send logs to **Logfire**.

    Args:
        logfire_instance: The Logfire instance to use.
    """
    original_print = builtins.print
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='print')
    scrubber = logfire_instance.config.scrubber

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
            value_cleaner = MessageValueCleaner(scrubber, check_keys=True)
            attributes: dict[str, Any]
            if call_node is None:
                attributes = {FALLBACK_ATTRIBUTE_KEY: args}
                message_parts = [value_cleaner.clean_value(FALLBACK_ATTRIBUTE_KEY, str(arg)) for arg in args]
            else:
                attributes, message_parts = _get_magic_attributes(call_node, args, inspector.ex.source, value_cleaner)
            attributes[ATTRIBUTES_MESSAGE_KEY] = sep.join(message_parts)
            attributes.update(value_cleaner.extra_attrs())
            logfire_instance.log('info', 'print', attributes)

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

    return uninstrument_context()


def _get_magic_attributes(
    call_node: ast.Call, args: tuple[Any, ...], source: executing.Source, value_cleaner: MessageValueCleaner
):
    result: dict[str, Any] = {}
    ast_args = list(call_node.args)
    runtime_args = list(args)

    def _process_end():
        """Helper to process non-starred args from the end of the lists."""
        message_parts: list[str] = []
        while ast_args and not isinstance(ast_args[-1], ast.Starred):
            node = ast_args.pop()
            value = runtime_args.pop()
            if _is_literal(node):
                message_parts.append(value_cleaner.truncate(str(value)))
            else:
                node_source = get_node_source_text(node, source)
                message_parts.append(value_cleaner.clean_value(node_source, str(value)))
                result[node_source] = value
        return message_parts

    ast_args.reverse()
    runtime_args.reverse()
    message_parts_start = _process_end()

    if not runtime_args:
        return result, message_parts_start

    ast_args.reverse()
    runtime_args.reverse()
    message_parts_end = _process_end()
    message_parts_end.reverse()

    if len(ast_args) == 1:
        assert isinstance(ast_args[0], ast.Starred)
        middle_key = get_node_source_text(ast_args[0].value, source)
    else:
        middle_key = FALLBACK_ATTRIBUTE_KEY

    result[middle_key] = runtime_args
    message_parts_middle = [value_cleaner.clean_value(middle_key, str(arg)) for arg in runtime_args]

    return result, message_parts_start + message_parts_middle + message_parts_end


@functools.lru_cache(maxsize=1024)
def _is_literal(node: ast.expr):
    try:
        ast.literal_eval(node)
        return True
    except Exception:
        return False


class PrintArgumentsInspector(ArgumentsInspector):
    def heuristic_main_nodes(self) -> Iterator[ast.AST]:
        yield from self.ex.statements

    def heuristic_call_node_filter(self, node: ast.Call) -> bool:
        return bool(node.args)

    def warn_inspect_arguments_middle(self):
        return f'Using `{FALLBACK_ATTRIBUTE_KEY}` as the fallback attribute key for all print arguments.'
