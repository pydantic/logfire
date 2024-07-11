from __future__ import annotations

from typing import Any, Sequence

from opentelemetry import context
from opentelemetry.sdk.metrics.export import AggregationTemporality, MetricExporter, MetricExportResult, MetricsData
from opentelemetry.sdk.metrics.view import Aggregation
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

import logfire


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

    def __init__(
        self,
        exporter: MetricExporter,
        preferred_temporality: dict[type, AggregationTemporality] | None = None,
        preferred_aggregation: dict[type, Aggregation] | None = None,
    ) -> None:
        super().__init__(preferred_temporality=preferred_temporality, preferred_aggregation=preferred_aggregation)  # type: ignore
        self.wrapped_exporter = exporter

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any) -> MetricExportResult:
        return self.wrapped_exporter.export(metrics_data, timeout_millis, **kwargs)  # type: ignore

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return self.wrapped_exporter.force_flush(timeout_millis)

    def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
        self.wrapped_exporter.shutdown(timeout_millis, **kwargs)  # type: ignore


class WrapperSpanProcessor(SpanProcessor):
    """A base class for SpanProcessors that wrap another processor."""

    def __init__(self, processor: SpanProcessor) -> None:
        self.processor = processor

    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        self.processor.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        self.processor.on_end(span)

    def shutdown(self) -> None:
        with logfire.suppress_instrumentation():
            self.processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        with logfire.suppress_instrumentation():
            return self.processor.force_flush(timeout_millis)
