from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import datetime
from typing import IO

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from rich.console import Console


class ConsoleSpanExporter(SpanExporter):
    def __init__(
        self,
        out: IO[str] = sys.stdout,
    ) -> None:
        self._out = out
        self._console = Console(file=out)
        super().__init__()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            start_time = datetime.fromtimestamp(span.start_time / 1e9) if span.start_time else ''
            end_time = datetime.fromtimestamp(span.end_time / 1e9) if span.end_time else ''
            output = f'{span.name}: {start_time} {end_time}'
            self._console.print(output)
        self._out.flush()
        return SpanExportResult.SUCCESS

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


if __name__ == '__main__':
    from time import sleep

    from opentelemetry import trace
    from opentelemetry.sdk.trace import Resource, TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider(resource=Resource(attributes={'service.name': 'test'}))
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
