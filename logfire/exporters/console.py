"""Console exporter for OpenTelemetry.

Inspired by https://opentelemetry-python.readthedocs.io/en/latest/_modules/opentelemetry/sdk/trace/export.html#ConsoleSpanExporter
"""
from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, TextIO, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.util import types as otel_types
from rich.columns import Columns
from rich.console import Console, Group
from rich.markup import escape as rich_escape
from rich.syntax import Syntax
from rich.text import Text

from .._constants import (
    ATTRIBUTES_LOG_LEVEL_NAME_KEY,
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY,
    ATTRIBUTES_SPAN_TYPE_KEY,
    ATTRIBUTES_TAGS_KEY,
    LEVEL_NUMBERS,
)
from .._json_formatter import json_args_value_formatter

_NANOSECONDS_PER_SECOND = 1_000_000_000
ConsoleColorsValues = Literal['auto', 'always', 'never']
_WARN_LEVEL = LEVEL_NUMBERS['warn']
_ERROR_LEVEL = LEVEL_NUMBERS['error']


class SimpleConsoleSpanExporter(SpanExporter):
    """The ConsoleSpanExporter prints spans to the console.

    This simple version does not indent spans based on their parent(s), instead spans are printed as a
    flat list.
    """

    def __init__(
        self,
        output: TextIO = sys.stdout,
        colors: ConsoleColorsValues = 'auto',
        include_timestamp: bool = True,
        verbose: bool = False,
    ) -> None:
        if colors == 'auto':
            force_terminal = None
        else:
            force_terminal = colors == 'always'
        self._console = Console(file=output, force_terminal=force_terminal, highlight=False)
        self._include_timestamp = include_timestamp
        # timestamp len('12:34:56.789') 12 + space (1)
        self._timestamp_indent = 13 if include_timestamp else 0
        self._verbose = verbose

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export the spans to the console."""
        for span in spans:
            self._log_span(span)

        return SpanExportResult.SUCCESS

    def _log_span(self, span: ReadableSpan) -> None:
        """Print a summary of the span, this method can be overridden to customize how spans are displayed.

        In this simple case we just print the span if its type is not "span" - e.g. the message at the end of a span.
        """
        span_type = span.attributes and span.attributes.get(ATTRIBUTES_SPAN_TYPE_KEY, 'span')
        # only print for "pending_span" (received at the start of a span) and "log" (spans with no duration)
        if span_type != 'span':
            self._print_span(span)

    def _print_span(self, span: ReadableSpan, indent: int = 0) -> str:
        """Build up a summary of the span, including bbcode formatting for rich, then print it.

        Returns:
            the formatted message or span name.
        """
        if self._include_timestamp:
            ts = datetime.fromtimestamp((span.start_time or 0) / _NANOSECONDS_PER_SECOND, tz=timezone.utc)
            # ugly though it is, `[:-3]` is the simplest way to convert microseconds -> milliseconds
            ts_str = f'{ts:%H:%M:%S.%f}'[:-3]
            line = f'[green]{ts_str}[/green] '
        else:
            line = ''

        if indent:
            line += indent * '  '

        if span.attributes:
            formatted_message: str | None = span.attributes.get(ATTRIBUTES_MESSAGE_KEY)  # type: ignore
            msg = formatted_message or span.name
            level: int = span.attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY) or 0  # type: ignore
        else:
            msg = span.name
            level = 0

        # escape the message so stuff like `[red]...` doesn't affect how the message is shown
        escaped_msg = rich_escape(msg)

        if level >= _ERROR_LEVEL:
            # add the message in red if it's an error or worse
            line += f'[red]{escaped_msg}[/red]'
        elif level >= _WARN_LEVEL:
            # add the message in yellow if it's a warning
            line += f'[yellow]{escaped_msg}[/yellow]'
        else:
            line += escaped_msg

        if tags := span.attributes and span.attributes.get(ATTRIBUTES_TAGS_KEY):
            tags_str = ','.join(cast('list[str]', tags))
            line += f' [cyan]\\[{rich_escape(tags_str)}][/cyan]'
        self._console.print(line)
        self._print_details(span, indent)
        return msg

    def _print_details(self, span: ReadableSpan, indent: int) -> None:
        """Print details for the span if `self._verbose` is True.

        The following details are printed:
        * filename and line number
        * the log level name
        * logfire arguments
        """
        if not self._verbose or not span.attributes:
            return

        indent_str = (self._timestamp_indent + indent * 2) * ' '

        file_location = span.attributes.get('code.filepath')
        if file_location:
            lineno = span.attributes.get('code.lineno')
            if lineno:
                file_location += f':{lineno}'  # type: ignore

        # TODO(Samuel) This is an ugly work around until have arguments JSON Schema (#940) which tell us exactly
        # which attributes are arguments
        arguments: dict[str, Any] = {}
        for k, v in span.attributes.items():
            if '.' not in k:
                if k.endswith('_JSON'):
                    arguments[k[:-5]] = json.loads(cast(str, v))
                else:
                    arguments[k] = v

        log_level = span.attributes.get(ATTRIBUTES_LOG_LEVEL_NAME_KEY) or ''

        if file_location or log_level:
            self._console.print(f'{indent_str}[blue]│[/blue] [cyan]{file_location}[/cyan] {log_level}')
        if arguments:
            chunks: list[Columns] = []
            if arguments:
                for k, v in arguments.items():
                    key = Text(f'{k}=', style='blue')
                    value_code = json_args_value_formatter(v)
                    value = Syntax(value_code, 'python', background_color='default')
                    barrier = Text(('│ \n' * (value_code.count('\n') + 1))[:-1], style='blue')
                    chunks.append(Columns((indent_str, barrier, key, value), padding=(0, 0)))

            self._console.print(Group(*chunks))

    def force_flush(self, timeout_millis: int = 0) -> bool:
        """Force flush all spans, does nothing for this exporter."""
        return True


class IndentedConsoleSpanExporter(SimpleConsoleSpanExporter):
    """The ConsoleSpanExporter exports spans to the console, indented.

    Spans are intended based simply on how many parents they have. This will work well when spans don't overlap,
    but will be hard to understand when multiple spans are in progress at the same time.
    """

    def __init__(
        self,
        output: TextIO = sys.stdout,
        colors: ConsoleColorsValues = 'auto',
        include_timestamp: bool = True,
        verbose: bool = False,
    ) -> None:
        super().__init__(output, colors, include_timestamp, verbose)
        # lookup from span ID to indent level
        self._indent_level: dict[int, int] = {}

    def _log_span(self, span: ReadableSpan) -> None:
        """Get the span indent based on `self._indent_level`, then print the span with that indent."""
        attributes = span.attributes or {}
        span_type = attributes.get(ATTRIBUTES_SPAN_TYPE_KEY, 'span')
        if span_type == 'span':
            # this is the end of a span, remove it from `self._indent_level` and don't print
            if span.context:
                self._indent_level.pop(span.context.span_id, None)
            return

        if span_type == 'pending_span':
            parent_id = _pending_span_parent(attributes)
            indent = self._indent_level.get(parent_id, 0) if parent_id else 0

            # block_span_id will be the parent_id for all subsequent spans and logs in this block
            if block_span_id := span.parent.span_id if span.parent else None:
                self._indent_level[block_span_id] = indent + 1
        else:
            # this is a log, we just get the indent level from the parent span
            parent_id = span.parent.span_id if span.parent else None
            indent = self._indent_level.get(parent_id, 0) if parent_id else 0

        self._print_span(span, indent)


class ShowParentsConsoleSpanExporter(SimpleConsoleSpanExporter):
    """The ConsoleSpanExporter exports spans to the console, indented with parents displayed where necessary.

    Spans are intended based on how many parents they have, where multiple concurrent spans overlap and therefore
    the previously displayed span is not the parent or sibling of a span, parents are printed (with "dim" color)
    so it's easy (or as easy as possible in a terminal) to understand how nested spans are related.
    """

    def __init__(
        self,
        output: TextIO = sys.stdout,
        colors: ConsoleColorsValues = 'auto',
        include_timestamp: bool = True,
        verbose: bool = False,
    ) -> None:
        super().__init__(output, colors, include_timestamp, verbose)

        # lookup from span_id to `(indent, span message, parent id)`
        self._span_history: dict[int, tuple[int, str, int]] = {}
        # current open span ids
        self._span_stack: list[int] = []

    def _log_span(self, span: ReadableSpan) -> None:
        """Print any parent spans which aren't in the current stack of displayed spans, then print this span."""
        attributes = span.attributes or {}
        span_type = attributes.get(ATTRIBUTES_SPAN_TYPE_KEY, 'span')
        if span_type == 'span':
            # this is the end of a span, remove it from `self._span_history` and `self._span_stack`, don't print
            if span.context:
                self._span_history.pop(span.context.span_id, None)
                if self._span_stack and self._span_stack[-1] == span.context.span_id:
                    self._span_stack.pop()
            return

        if span_type == 'pending_span':
            parent_id = _pending_span_parent(attributes)
            self._print_parent_stack(parent_id)

            indent = len(self._span_stack)
            msg = self._print_span(span, indent)

            if block_span_id := span.parent and span.parent.span_id:
                self._span_history[block_span_id] = (indent, msg, parent_id or 0)
                self._span_stack.append(block_span_id)
        else:
            # this is a log
            parent_id = span.parent.span_id if span.parent else None
            self._print_parent_stack(parent_id)

            self._print_span(span, len(self._span_stack))

    def _print_parent_stack(self, parent_id: int | None) -> None:
        """Print "intermediate" parent spans - e.g., spans which are not parents of the currently displayed span.

        Also build up `self._span_stack` to correctly represent the path to the current span.
        """
        # (indent, msg, parent_id)
        parents: list[tuple[int, str, int]] = []
        clear_stack = True
        # find a stack of parent spans until we reach a span in self._span_stack
        while parent_id:
            try:
                indent, line, grand_parent_id = self._span_history[parent_id]
            except KeyError:
                break
            else:
                try:
                    stack_index = self._span_stack.index(parent_id)
                except ValueError:
                    parents.append((indent, line, parent_id))
                    parent_id = grand_parent_id
                else:
                    self._span_stack = self._span_stack[: stack_index + 1]
                    clear_stack = False
                    break

        # if we haven't got to a span in self._span_stack, clear self._span_stack
        if clear_stack:
            self._span_stack.clear()

        # parentis are currently in the reverse order as they were built from innermost first, hence
        # iterate over them reversed, and print them
        for indent, msg, parent_id in reversed(parents):
            total_indent = self._timestamp_indent + indent * 2
            self._console.print(f'{" " * total_indent}{msg}', style='dim', markup=False)
            if parent_id:
                self._span_stack.append(parent_id)


def _pending_span_parent(attributes: Mapping[str, otel_types.AttributeValue]) -> int | None:
    """Pending span marks the start of a span.

    Since they're nested within another span we haven't seen yet,
    we have to do a trick of getting the 'logfire.pending_parent_id' attribute to get the parent indent.

    Note that returning `0` is equivalent to returning `None` since top level spans get
    `ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY` encoded from `0`.
    """
    if parent_id_str := attributes.get(ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY):
        return int(parent_id_str, 16)  # type: ignore
