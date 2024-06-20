from ..constants import ATTRIBUTES_JSON_SCHEMA_KEY as ATTRIBUTES_JSON_SCHEMA_KEY, ATTRIBUTES_LOG_LEVEL_NUM_KEY as ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY as ATTRIBUTES_PENDING_SPAN_REAL_PARENT_KEY, ATTRIBUTES_SPAN_TYPE_KEY as ATTRIBUTES_SPAN_TYPE_KEY, ATTRIBUTES_TAGS_KEY as ATTRIBUTES_TAGS_KEY, DISABLE_CONSOLE_KEY as DISABLE_CONSOLE_KEY, LEVEL_NUMBERS as LEVEL_NUMBERS, LevelName as LevelName, NUMBER_TO_LEVEL as NUMBER_TO_LEVEL, ONE_SECOND_IN_NANOSECONDS as ONE_SECOND_IN_NANOSECONDS
from ..json_formatter import json_args_value_formatter as json_args_value_formatter
from _typeshed import Incomplete
from collections.abc import Sequence
from opentelemetry.sdk.trace import Event as Event, ReadableSpan as ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter
from typing import TextIO

ConsoleColorsValues: Incomplete
TextParts = list[tuple[str, str]]

class SimpleConsoleSpanExporter(SpanExporter):
    """The ConsoleSpanExporter prints spans to the console.

    This simple version does not indent spans based on their parent(s), instead spans are printed as a
    flat list.
    """
    def __init__(self, output: TextIO | None = None, colors: ConsoleColorsValues = 'auto', include_timestamp: bool = True, verbose: bool = False, min_log_level: LevelName = 'info') -> None: ...
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export the spans to the console."""
    def force_flush(self, timeout_millis: int = 0) -> bool:
        """Force flush all spans, does nothing for this exporter."""

class IndentedConsoleSpanExporter(SimpleConsoleSpanExporter):
    """The ConsoleSpanExporter exports spans to the console, indented.

    Spans are intended based simply on how many parents they have. This will work well when spans don't overlap,
    but will be hard to understand when multiple spans are in progress at the same time.
    """
    def __init__(self, output: TextIO | None = None, colors: ConsoleColorsValues = 'auto', include_timestamp: bool = True, verbose: bool = False, min_log_level: LevelName = 'info') -> None: ...

class ShowParentsConsoleSpanExporter(SimpleConsoleSpanExporter):
    '''The ConsoleSpanExporter exports spans to the console, indented with parents displayed where necessary.

    Spans are intended based on how many parents they have, where multiple concurrent spans overlap and therefore
    the previously displayed span is not the parent or sibling of a span, parents are printed (with "dim" color)
    so it\'s easy (or as easy as possible in a terminal) to understand how nested spans are related.
    '''
    def __init__(self, output: TextIO | None = None, colors: ConsoleColorsValues = 'auto', include_timestamp: bool = True, verbose: bool = False, min_log_level: LevelName = 'info') -> None: ...
