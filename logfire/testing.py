from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, TypeVar, cast

from opentelemetry.sdk.metrics._internal.aggregation import AggregationTemporality
from opentelemetry.sdk.metrics._internal.point import MetricsData
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator

T = TypeVar('T')


class KeyAwareDefaultDict(Dict[T, T]):
    def __missing__(self, key: T) -> T:
        return key


class TestExporter(SpanExporter):
    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans.extend(spans)

    def exported_spans_as_dict(  # noqa: C901
        self,
        fixed_line_number: int | None = 123,
        strip_filepaths: bool = True,
        map_times: bool = True,
        map_span_ids: bool = True,
        map_trace_ids: bool = True,
    ) -> list[dict[str, Any]]:
        # build a list of all trace, span ids and times
        # order them by the start time of the span
        # then map them to incrementing integers
        # this way we can easily assert on the order of spans
        def get_logfire_start_parent_id(span: ReadableSpan) -> int | None:
            if span.attributes is None:
                return None
            return cast(int | None, span.attributes.get('logfire.start_parent_id'))

        span_ids = [
            span_id
            for span in self.exported_spans
            for span_id in [
                span.context.span_id,
                span.parent.span_id if span.parent else None,
                get_logfire_start_parent_id(span),
            ]
            if span_id is not None
        ]

        trace_ids = [
            trace_id
            for span in self.exported_spans
            for trace_id in [span.context.trace_id, span.parent.trace_id if span.parent else None]
            if trace_id is not None
        ]

        span_start_times: dict[int, int] = {}
        trace_start_times: dict[int, int] = {}

        for span in self.exported_spans:
            if span.start_time:
                span_id = span.context.span_id
                span_start_times[span_id] = min(span.start_time, span_start_times.get(span_id, span.start_time))
                trace_id = span.context.trace_id
                trace_start_times[trace_id] = min(span.start_time, trace_start_times.get(trace_id, span.start_time))

        if map_span_ids:
            span_id_mapping = {
                span_id: i
                for i, span_id in enumerate(
                    sorted(
                        set(span_ids), key=lambda span_id: (span_start_times.get(span_id, 0), span_ids.index(span_id))
                    )
                )
            }
        else:
            span_id_mapping = KeyAwareDefaultDict[int]()

        if map_trace_ids:
            trace_id_mapping = {
                trace_id: i
                for i, trace_id in enumerate(
                    sorted(
                        set(trace_ids),
                        key=lambda trace_id: (span_start_times.get(trace_id, 0), trace_ids.index(trace_id)),
                    )
                )
            }
        else:
            trace_id_mapping = KeyAwareDefaultDict[int]()

        if map_times:
            times = sorted(
                [time for span in self.exported_spans for time in [span.start_time, span.end_time] if time is not None]
                + [event.timestamp for span in self.exported_spans for event in span.events]
            )
            time_mapping = {time: i for i, time in enumerate(times)}
        else:
            time_mapping = KeyAwareDefaultDict[int]()

        def process_attribute(name: str, value: Any) -> Any:
            if name == 'code.filepath' and strip_filepaths:
                try:
                    return Path(value).name
                except ValueError:
                    return value
            if name == 'code.lineno' and fixed_line_number is not None:
                return fixed_line_number
            if name == 'logfire.start_parent_id':
                return span_id_mapping[value]
            return value

        def build_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if attributes is None:
                return None
            return {k: process_attribute(k, v) for k, v in attributes.items()}

        def build_event(event: Event) -> dict[str, Any]:
            return {
                'name': event.name,
                'attributes': build_attributes(event.attributes),
                'timestamp': time_mapping[event.timestamp],
            }

        def build_span(span: ReadableSpan) -> dict[str, Any]:
            res: dict[str, Any] = {
                'name': span.name,
                'context': {
                    'trace_id': trace_id_mapping[span.context.trace_id],
                    'span_id': span_id_mapping[span.context.span_id],
                    'is_remote': span.context.is_remote,
                },
                'parent': {
                    'trace_id': trace_id_mapping[span.parent.trace_id],
                    'span_id': span_id_mapping[span.parent.span_id],
                    'is_remote': span.parent.is_remote,
                }
                if span.parent
                else None,
                'start_time': time_mapping[span.start_time] if span.start_time else None,
                'end_time': time_mapping[span.end_time] if span.end_time else None,
                'attributes': build_attributes(span.attributes),
            }
            if span.events:
                res['events'] = [build_event(event) for event in span.events]
            return res

        return [build_span(span) for span in self.exported_spans]


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
        return None

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


@dataclass(repr=True)
class TimeGenerator:
    ns_time: int = 0

    def __call__(self) -> int:
        self.ns_time += 1
        return self.ns_time
