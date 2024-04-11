from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class WrapperSpanExporter(SpanExporter):
    """A base class for SpanExporters that wrap another exporter."""

    def __init__(self, exporter: SpanExporter) -> None:
        self.wrapped_exporter = exporter

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return self.wrapped_exporter.export(spans)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.wrapped_exporter.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self.wrapped_exporter.shutdown()
