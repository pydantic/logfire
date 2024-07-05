from _typeshed import Incomplete
from opentelemetry import context
from opentelemetry.sdk.metrics.export import AggregationTemporality as AggregationTemporality, MetricExportResult, MetricExporter, MetricsData
from opentelemetry.sdk.metrics.view import Aggregation as Aggregation
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExportResult, SpanExporter
from typing import Any, Sequence

class WrapperSpanExporter(SpanExporter):
    """A base class for SpanExporters that wrap another exporter."""
    wrapped_exporter: Incomplete
    def __init__(self, exporter: SpanExporter) -> None: ...
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...
    def force_flush(self, timeout_millis: int = 30000) -> bool: ...
    def shutdown(self) -> None: ...

class WrapperMetricExporter(MetricExporter):
    """A base class for MetricExporters that wrap another exporter."""
    wrapped_exporter: Incomplete
    def __init__(self, exporter: MetricExporter, preferred_temporality: dict[type, AggregationTemporality] | None = None, preferred_aggregation: dict[type, Aggregation] | None = None) -> None: ...
    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: Any) -> MetricExportResult: ...
    def force_flush(self, timeout_millis: float = 10000) -> bool: ...
    def shutdown(self, timeout_millis: float = 30000, **kwargs: Any) -> None: ...

class WrapperSpanProcessor(SpanProcessor):
    """A base class for SpanProcessors that wrap another processor."""
    processor: Incomplete
    def __init__(self, processor: SpanProcessor) -> None: ...
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None: ...
    def on_end(self, span: ReadableSpan) -> None: ...
    def shutdown(self) -> None: ...
    def force_flush(self, timeout_millis: int = 30000) -> bool: ...
