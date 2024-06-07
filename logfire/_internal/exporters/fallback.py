from __future__ import annotations

from typing import Sequence

import requests
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
        except Exception as e:
            if isinstance(e, requests.exceptions.RequestException):
                # Silence the exception so that OTEL doesn't log a huge traceback.
                # Rely on OTLPExporterHttpSession to log this kind of error periodically.
                return SpanExportResult.FAILURE
            else:
                # Only write to fallback file if this isn't already being retried by OTLPExporterHttpSession.
                self.fallback.export(spans)
                raise
        if res is not SpanExportResult.SUCCESS:  # pragma: no branch
            self.fallback.export(spans)
        return res

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
        return self.exporter.force_flush(timeout_millis) and self.fallback.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self.exporter.shutdown()
        self.fallback.shutdown()
