from __future__ import annotations

import sys
from collections.abc import Iterator, Sequence
from pathlib import Path

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

import logfire

output_path = Path(sys.argv[1])


class FileExporter(SpanExporter):
    def __init__(self) -> None:
        self.shutdown_called = False

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self.shutdown_called:
            output_path.write_text('export after shutdown')
        else:
            output_path.write_text('\n'.join(span.name for span in spans))
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        self.shutdown_called = True


def open_span_in_suspended_generator() -> Iterator[None]:
    with logfire.span('open span at shutdown'):
        yield


logfire.configure(send_to_logfire=False, console=False, inspect_arguments=False)
logfire.configure(
    send_to_logfire=False,
    console=False,
    inspect_arguments=False,
    additional_span_processors=[SimpleSpanProcessor(FileExporter())],
)
generator = open_span_in_suspended_generator()
next(generator)
