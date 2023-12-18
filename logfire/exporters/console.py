"""Console exporter for OpenTelemetry.

Inspired by https://opentelemetry-python.readthedocs.io/en/latest/_modules/opentelemetry/sdk/trace/export.html#ConsoleSpanExporter
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal, TextIO, cast

import structlog
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import format_span_id
from structlog.dev import ConsoleRenderer
from structlog.typing import EventDict, WrappedLogger

from .._constants import ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_SPAN_TYPE_KEY, ATTRIBUTES_TAGS_KEY, SpanTypeType

_NANOSECONDS_PER_SECOND = 1_000_000_000
ConsoleColorsValues = Literal['auto', 'always', 'never']


class _DefaultProcessor:
    def __init__(self, include_timestamp: bool, verbose: bool) -> None:
        self._include_timestamp = include_timestamp
        self._verbose = verbose

    def __call__(self, _: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        span = cast(ReadableSpan, event_dict.pop('span'))
        if self._verbose:
            event_dict['span_id'] = format_span_id(span.context.span_id)
            if span.attributes:
                if span_type := span.attributes.get(ATTRIBUTES_SPAN_TYPE_KEY):
                    event_dict['span_type'] = span_type
                if tags := span.attributes.get(ATTRIBUTES_TAGS_KEY):
                    event_dict['tags'] = tags
            if span.parent and (parent_id := span.parent.span_id):
                event_dict['parent_id'] = format_span_id(parent_id)
        assert span.start_time is not None
        if self._include_timestamp:
            start_time = datetime.fromtimestamp(span.start_time // _NANOSECONDS_PER_SECOND, tz=timezone.utc).strftime(
                '%Y-%m-%d %H:%M:%S'
            )
            event_dict['timestamp'] = start_time

        return event_dict


class _ConsoleRenderer(ConsoleRenderer):
    def __init__(self, *args: Any, indent_spans: bool, **kwargs: Any):
        self._indent_spans = indent_spans
        super().__init__(*args, **kwargs)

    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> str:
        indent = cast(int, event_dict.pop('indent', 0))
        message = super().__call__(logger, name, event_dict)
        return indent * '  ' + message if self._indent_spans else message


class ConsoleSpanExporter(SpanExporter):
    """The ConsoleSpanExporter exports spans to the console."""

    def __init__(
        self,
        output: TextIO = sys.stdout,
        colors: ConsoleColorsValues | None = 'auto',
        indent_spans: bool = True,
        include_timestamp: bool = True,
        verbose: bool = False,
        max_spans_in_state: int = 50_000,
    ) -> None:
        self._log = structlog.wrap_logger(
            structlog.PrintLogger(output),
            processors=[
                _DefaultProcessor(include_timestamp=include_timestamp, verbose=verbose),
                structlog.processors.StackInfoRenderer(),
                _ConsoleRenderer(
                    sort_keys=False,
                    colors=(colors == 'always') or (colors == 'auto' and output.isatty()),
                    indent_spans=indent_spans,
                ),
            ],
            context_class=dict,
        ).info
        self._indent_level: dict[int, int] = {}
        self._max_spans_in_state = max_spans_in_state

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Export the spans to the console."""
        sort_mapping = {'span': 2, 'pending_span': 1, 'log': 0}
        spans_and_metadata = [(span, _get_span_type(span), _get_span_parent_id(span)) for span in spans]
        for span, span_type, parent_id in sorted(
            spans_and_metadata, key=lambda x: (x[0].start_time or 0, sort_mapping.get(x[1], 0))
        ):
            if parent_id:
                indent = self._indent_level.get(parent_id, 0)
            else:
                indent = 0
            self._indent_level[span.context.span_id] = indent + 1
            # remove old indent levels, making use of the fact that dicts are ordered
            # this may be slow but avoids locks or race conditions, change if needed
            while len(self._indent_level) > self._max_spans_in_state:
                del self._indent_level[next(iter(self._indent_level))]

            if span_type != 'pending_span':
                self._log(event=_get_span_name(span), span=span, indent=indent)
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 0) -> bool:
        """Force flush all spans."""
        return True


def _get_span_parent_id(span: ReadableSpan) -> int | None:
    return cast('int | None', span.parent.span_id) if span.parent else None


def _get_span_type(span: ReadableSpan) -> SpanTypeType:
    return cast(SpanTypeType, span.attributes.get(ATTRIBUTES_SPAN_TYPE_KEY, 'span')) if span.attributes else 'span'


def _get_span_name(span: ReadableSpan) -> str:
    if not span.attributes:
        return span.name
    formatted_message = cast('str | None', span.attributes.get(ATTRIBUTES_MESSAGE_KEY))
    return formatted_message or span.name
