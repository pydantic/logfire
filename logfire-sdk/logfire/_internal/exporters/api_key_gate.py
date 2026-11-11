"""Exporters that stop sending telemetry with an API key that Logfire rejects as a write token.

`logfire.configure()` uses the API key as the write token when no write token is configured.
Many API keys do not have the `project:write_otlp` scope, e.g. a key used only to query data.
The token check then warns once, and these exporters drop the telemetry for that key.
So a rejected key does not log a failed export for every batch.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import LogRecordExporter, LogRecordExportResult
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from .wrapper import WrapperLogExporter, WrapperMetricExporter, WrapperSpanExporter

VERDICT_TIMEOUT_SECONDS = 15
"""How long an export waits for the token check. The check request itself times out after 10 seconds."""


class ApiKeyWriteAccess:
    """The result of the token check for an API key that is used as a write token."""

    def __init__(self) -> None:
        self._settled = threading.Event()
        self._rejected = False

    def reject(self) -> None:
        """Record that Logfire rejected the API key as a write token."""
        self._rejected = True
        self._settled.set()

    def settle(self) -> None:
        """Record that the check finished. A key that the check did not reject stays allowed."""
        self._settled.set()

    def allows_export(self) -> bool:
        """Wait for the check, then tell if exports can use the key.

        If the check does not finish in time, the export continues.
        The exporters then report any failure as they do for a write token.
        """
        self._settled.wait(VERDICT_TIMEOUT_SECONDS)
        return not self._rejected


class ApiKeyGatedSpanExporter(WrapperSpanExporter):
    def __init__(self, exporter: SpanExporter, access: ApiKeyWriteAccess) -> None:
        super().__init__(exporter)
        self.access = access

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if not self.access.allows_export():
            return SpanExportResult.FAILURE
        return super().export(spans)


class ApiKeyGatedLogExporter(WrapperLogExporter):
    def __init__(self, exporter: LogRecordExporter, access: ApiKeyWriteAccess) -> None:
        super().__init__(exporter)
        self.access = access

    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult:
        if not self.access.allows_export():
            return LogRecordExportResult.FAILURE
        return super().export(batch)


class ApiKeyGatedMetricExporter(WrapperMetricExporter):
    def __init__(self, exporter: MetricExporter, access: ApiKeyWriteAccess, **kwargs: Any) -> None:
        super().__init__(exporter, **kwargs)
        self.access = access

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        if not self.access.allows_export():
            return MetricExportResult.FAILURE
        return super().export(metrics_data, timeout_millis, **kwargs)
