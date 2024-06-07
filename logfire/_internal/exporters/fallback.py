from __future__ import annotations

from typing import Sequence

import requests
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from ..utils import logger


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
            self.fallback.export(spans)
            if isinstance(e, requests.exceptions.RequestException):
                logger.warning('Error sending spans to Logfire: %s', e)
                return SpanExportResult.FAILURE
            else:
                raise
        if res is not SpanExportResult.SUCCESS:  # pragma: no branch
            self.fallback.export(spans)
        return res

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # pragma: no cover
        return self.exporter.force_flush(timeout_millis) and self.fallback.force_flush(timeout_millis)

    def shutdown(self) -> None:
        self.exporter.shutdown()
        self.fallback.shutdown()
