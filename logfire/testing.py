from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator


class TestExporter(SpanExporter):
    """A SpanExporter that stores exported spans in a list for asserting in tests."""

    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans.extend(spans)

    def exported_spans_as_dict(
        self,
        fixed_line_number: int | None = 123,
        strip_filepaths: bool = True,
    ) -> list[dict[str, Any]]:
        def process_attribute(name: str, value: Any) -> Any:
            if name == 'code.filepath' and strip_filepaths:
                try:
                    return Path(value).name
                except ValueError:
                    return value
            if name == 'code.lineno' and fixed_line_number is not None:
                return fixed_line_number
            return value

        def build_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if attributes is None:
                return None
            return {k: process_attribute(k, v) for k, v in attributes.items()}

        def build_event(event: Event) -> dict[str, Any]:
            return {
                'name': event.name,
                'attributes': build_attributes(event.attributes),
                'timestamp': event.timestamp,
            }

        def build_span(span: ReadableSpan) -> dict[str, Any]:
            res: dict[str, Any] = {
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
            if span.events:
                res['events'] = [build_event(event) for event in span.events]
            return res

        return [build_span(span) for span in self.exported_spans]


@dataclass(repr=True)
class IncrementalIdGenerator(IdGenerator):
    """Generate sequentially incrementing span/trace IDs for testing.

    Trace IDs start at 1 and increment by 1 each time.
    Span IDs start at 1 and increment by 1 each time.
    """

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


ONE_NANOSECOND = 1_000_000_000


@dataclass(repr=True)
class TimeGenerator:
    """Generate incrementing timestamps for testing.

    Timestamps are in nanoseconds, start at 1_000_000_000, and increment by 1_000_000_000 (1 second) each time.
    """

    ns_time: int = 0

    def __call__(self) -> int:
        self.ns_time += ONE_NANOSECOND
        return self.ns_time
