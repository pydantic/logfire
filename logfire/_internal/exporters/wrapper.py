from typing import Any, Sequence

from opentelemetry.sdk.metrics._internal.export import MetricExporter, MetricExportResult
from opentelemetry.sdk.metrics._internal.point import MetricsData
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


class WrapperMetricExporter(MetricExporter):
    """A base class for MetricExporters that wrap another exporter."""

    def __init__(self, exporter: MetricExporter, **kwargs: Any) -> None:
        super().__init__(**kwargs)  # type: ignore
        self.wrapped_exporter = exporter

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        return self.wrapped_exporter.export(metrics_data, timeout_millis, **kwargs)  # type: ignore

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self.wrapped_exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        self.wrapped_exporter.shutdown(timeout_millis, **kwargs)  # type: ignore
