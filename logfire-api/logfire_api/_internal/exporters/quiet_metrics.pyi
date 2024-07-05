from .wrapper import WrapperMetricExporter as WrapperMetricExporter
from opentelemetry.sdk.metrics._internal.export import MetricExportResult
from opentelemetry.sdk.metrics._internal.point import MetricsData
from typing import Any

class QuietMetricExporter(WrapperMetricExporter):
    """A MetricExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""
    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: Any) -> MetricExportResult: ...
