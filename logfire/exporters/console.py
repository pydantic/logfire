"""Console exporter for OpenTelemetry.

Inspired by https://opentelemetry-python.readthedocs.io/en/latest/_modules/opentelemetry/sdk/trace/export.html#ConsoleSpanExporter
"""
from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime
from typing import IO, Any, cast

import structlog
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import format_span_id
from rich.console import Console
from structlog.typing import EventDict, WrappedLogger


class DefaultProcessor:
    def __call__(self, _: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
        span = cast(ReadableSpan, event_dict.pop('span'))

        if event_dict.pop('verbose', False):
            event_dict['span_id'] = format_span_id(span.context.span_id)
            if span.attributes and (span_type := span.attributes.get('logfire.log_type')):
                event_dict['span_type'] = span_type
            if span.parent and (parent_id := span.parent.span_id):
                event_dict['parent_id'] = format_span_id(parent_id)
            if span.attributes and (start_parent_id := span.attributes.get('logfire.start_parent_id')):
                event_dict['start_parent_id'] = start_parent_id

        start_time = str(datetime.fromtimestamp(span.start_time / 1e9))  # type: ignore
        event_dict['timestamp'] = start_time

        return event_dict


class ConsoleRenderer(structlog.dev.ConsoleRenderer):
    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> str:
        indent = cast(int, event_dict.pop('indent', 0))
        message = super().__call__(logger, name, event_dict)
        return indent * '  ' + message


structlog.configure(
    processors=[
        DefaultProcessor(),
        structlog.processors.StackInfoRenderer(),
        ConsoleRenderer(sort_keys=False),
    ],
    context_class=dict,
)

log = structlog.get_logger()


class ConsoleSpanExporter(SpanExporter):
    def __init__(
        self,
        output: IO[str] = sys.stdout,
        verbose: bool = True,
    ) -> None:
        self._output = output
        self._console = Console(file=output)
        self._verbose = verbose
        self._indent_level: dict[Any, int] = {None: 0}

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in sorted(spans, key=lambda span: _key_sort_span(span)):
            parent_id = span.parent and format_span_id(span.parent.span_id)
            start_parent_id = span.attributes and span.attributes.get('logfire.start_parent_id')
            span_type = span.attributes and span.attributes.get('logfire.log_type')
            if span_type == 'start_span':
                indent = self._indent_level.get(start_parent_id, 0)
                self._indent_level[parent_id] = self._indent_level[start_parent_id] + 1
            elif span_type == 'log':
                indent = self._indent_level.get(parent_id, 0)
            else:
                indent = 0

            if span.attributes is None or span_type != 'real_span':
                log.info(event=span.name, span=span, verbose=self._verbose, indent=indent)
        self._output.flush()
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _key_sort_span(span: ReadableSpan) -> tuple[int, int]:
    span_type: str = span.attributes.get('logfire.log_type')  # type: ignore
    span_value = {'real_span': 2, 'start_span': 1, 'log': 0}.get(span_type, 0)
    return (span.start_time or 0, span_value)


if __name__ == '__main__':
    from time import sleep

    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider(resource=Resource(attributes={SERVICE_NAME: 'test'}))
    processor = SimpleSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
    for _ in range(5):
        with tracer.start_as_current_span('rootSpan'):
            with tracer.start_as_current_span('childSpan'):
                sleep(0.1)
            sleep(0.1)
        sleep(1)
