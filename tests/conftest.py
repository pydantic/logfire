from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest
from opentelemetry.sdk.metrics._internal.aggregation import AggregationTemporality
from opentelemetry.sdk.metrics._internal.point import MetricsData
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator

from logfire import Logfire
from logfire.config import LogfireConfig


class TestExporter(SpanExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans.extend(spans)

    def exported_spans_as_dict(self, *, full_attributes: bool = False) -> list[dict[str, Any]]:
        def build_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if attributes is None:
                return None
            elif full_attributes:
                return dict(attributes)

            # FIXME(Samuel) this seems confusion and unnecessary, we should just use the full attributes
            #   and use dirty-equals where attributes are non-deterministic, e.g. make full_attributes=True universal
            out: dict[str, Any] = {}
            if 'code.namespace' in attributes:
                out['code.namespace'] = attributes['code.namespace']
            if 'code.function' in attributes:
                out['code.function'] = attributes['code.function']
            if 'code.lineno' in attributes:
                out['code.lineno'] = attributes['code.lineno']
            if 'code.filepath' in attributes:
                # remove the prefix so that we can easily assert in tests
                out['code.filepath'] = str(Path(str(attributes['code.filepath'])).relative_to(Path('.').absolute()))
            if 'logfire.start_parent_id' in attributes:
                out['logfire.start_parent_id'] = attributes['logfire.start_parent_id']
            if 'logfire.log_type' in attributes:
                out['logfire.log_type'] = attributes['logfire.log_type']

            return out

        return [
            {
                'name': span.name,
                'context': {
                    'trace_id': span.context.trace_id,
                    'span_id': span.context.span_id,
                    'is_remote': span.context.is_remote,
                },
                'parent': {
                    'trace_id': span.parent.trace_id,
                    'span_id': span.parent.span_id,
                    'is_remote': span.parent.is_remote,
                }
                if span.parent
                else None,
                'start_time': span.start_time,
                'end_time': span.end_time,
                'attributes': build_attributes(span.attributes),
            }
            for span in self.exported_spans
        ]


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


@dataclass(repr=True)
class IncrementalIdGenerator(IdGenerator):
    """Generate sequentially incrementing span/trace IDs for testing."""

    trace_id_counter = 0
    span_id_counter = 0

    def reset_trace_span_ids(self) -> None:
        self.trace_id_counter = 0
        self.span_id_counter = 0

    def generate_span_id(self) -> int:
        self.span_id_counter += 1
        return self.span_id_counter

    def generate_trace_id(self) -> int:
        self.trace_id_counter += 1
        return self.trace_id_counter


INCREMENTAL_ID_GENERATOR = IncrementalIdGenerator()


@pytest.fixture(autouse=True)
def id_generator() -> IncrementalIdGenerator:
    INCREMENTAL_ID_GENERATOR.reset_trace_span_ids()
    return INCREMENTAL_ID_GENERATOR


@dataclass(repr=True)
class TimeGenerator:
    ns_time: int = 0

    def __call__(self) -> int:
        self.ns_time += 1
        return self.ns_time


TIME_GENERATOR = TimeGenerator()


@pytest.fixture(autouse=True)
def time_generator() -> TimeGenerator:
    TIME_GENERATOR.ns_time = 0
    return TIME_GENERATOR


@pytest.fixture
def exporter() -> TestExporter:
    return TestExporter()


@pytest.fixture
def metric_exporter() -> TestMetricExporter:
    return TestMetricExporter()


@pytest.fixture
def config(
    exporter: TestExporter, id_generator: IncrementalIdGenerator, time_generator: TimeGenerator
) -> LogfireConfig:
    return LogfireConfig.from_processors(
        SimpleSpanProcessor(exporter),
        service_name='logfire-sdk-testing',
        id_generator=id_generator,
        ns_time_generator=time_generator,
    )


@pytest.fixture
def logfire(config: LogfireConfig) -> Logfire:
    return Logfire(config)
