from __future__ import annotations

from typing import Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


class FallbackSpanExporter(SpanExporter):
    def __init__(
        self,
        exporter: SpanExporter,
        fallback: SpanExporter,
    ) -> None:
        self.exporter = exporter
        self.fallback = fallback

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            res = self.exporter.export(spans)
        except Exception:
            self.fallback.export(spans)
            raise
        if res is not SpanExportResult.SUCCESS:
            self.fallback.export(spans)
        return res

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.exporter.force_flush(timeout_millis) and self.fallback.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self.exporter.shutdown()
        self.fallback.shutdown()
