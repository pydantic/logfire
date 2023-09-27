from collections.abc import Sequence
from typing import Any

import pytest
from opentelemetry.sdk.metrics._internal.aggregation import AggregationTemporality
from opentelemetry.sdk.metrics._internal.point import MetricsData
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter

from logfire import Logfire
from logfire.config import LogfireConfig


class TestExporter(SpanExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans = list(spans)


class TestMetricExporter(MetricExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(
        self,
        preferred_temporality: dict[type, AggregationTemporality] | None = None,
        preferred_aggregation: dict[type, Any] | None = None,
    ) -> None:
        self.exported_metrics: list[MetricsData] = []
        super().__init__(preferred_temporality, preferred_aggregation)  # type: ignore

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: Any) -> MetricExportResult:
        self.exported_metrics.append(metrics_data)
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30000, **kwargs: Any) -> None:
        ...

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        return super().force_flush(timeout_millis)


@pytest.fixture
def exporter() -> TestExporter:
    return TestExporter()


@pytest.fixture
def metric_exporter() -> TestMetricExporter:
    return TestMetricExporter()


@pytest.fixture
def config(exporter: TestExporter) -> LogfireConfig:
    return LogfireConfig.from_exports(exporter, service_name='logfire-sdk-testing')


@pytest.fixture
def logfire(config: LogfireConfig) -> Logfire:
    return Logfire(config)
