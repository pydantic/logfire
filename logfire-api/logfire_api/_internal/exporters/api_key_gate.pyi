from .wrapper import WrapperLogExporter as WrapperLogExporter, WrapperMetricExporter as WrapperMetricExporter, WrapperSpanExporter as WrapperSpanExporter
from _typeshed import Incomplete
from collections.abc import Sequence
from opentelemetry.sdk._logs import ReadableLogRecord as ReadableLogRecord
from opentelemetry.sdk._logs.export import LogRecordExportResult, LogRecordExporter
from opentelemetry.sdk.metrics.export import MetricExportResult, MetricExporter, MetricsData
from opentelemetry.sdk.trace import ReadableSpan as ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter
from typing import Any

VERDICT_TIMEOUT_SECONDS: int

class ApiKeyWriteAccess:
    """The result of the token check for an API key that is used as a write token."""
    def __init__(self) -> None: ...
    def reject(self) -> None:
        """Record that Logfire rejected the API key as a write token."""
    def settle(self) -> None:
        """Record that the check finished. A key that the check did not reject stays allowed."""
    def allows_export(self) -> bool:
        """Wait for the check, then tell if exports can use the key.

        If the check does not finish in time, the export continues.
        The exporters then report any failure as they do for a write token.
        """

class ApiKeyGatedSpanExporter(WrapperSpanExporter):
    access: Incomplete
    def __init__(self, exporter: SpanExporter, access: ApiKeyWriteAccess) -> None: ...
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...

class ApiKeyGatedLogExporter(WrapperLogExporter):
    access: Incomplete
    def __init__(self, exporter: LogRecordExporter, access: ApiKeyWriteAccess) -> None: ...
    def export(self, batch: Sequence[ReadableLogRecord]) -> LogRecordExportResult: ...

class ApiKeyGatedMetricExporter(WrapperMetricExporter):
    access: Incomplete
    def __init__(self, exporter: MetricExporter, access: ApiKeyWriteAccess, **kwargs: Any) -> None: ...
    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: Any) -> MetricExportResult: ...
