"""Testing utilities for Logfire."""
from __future__ import annotations

import json
import random
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator

import logfire
from logfire._constants import ATTRIBUTES_SPAN_TYPE_KEY, RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS


class TestExporter(SpanExporter):
    """A SpanExporter that stores exported spans in a list for asserting in tests."""

    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> None:  # type: ignore[override]
        self.exported_spans.extend(spans)

    def clear(self) -> None:
        self.exported_spans = []

    def exported_spans_as_dict(  # noqa: C901
        self,
        fixed_line_number: int | None = 123,
        strip_filepaths: bool = True,
        include_resources: bool = False,
        include_package_versions: bool = False,
        _include_start_spans: bool = False,
        _strip_function_qualname: bool = True,
    ) -> list[dict[str, Any]]:
        """The exported spans as a list of dicts.

        Args:
            fixed_line_number: The line number to use for all spans.
            strip_filepaths: Whether to strip the filepaths from the exported spans.
            include_resources: Whether to include the resource attributes in the exported spans.
            include_package_versions: Whether to include the package versions in the exported spans.

        Returns:
            A list of dicts representing the exported spans.
        """

        def process_attribute(name: str, value: Any) -> Any:
            if name == 'code.filepath' and strip_filepaths:
                try:
                    return Path(value).name
                except ValueError:
                    return value
            if name == 'code.lineno' and fixed_line_number is not None:
                return fixed_line_number
            if name == 'code.function':
                if sys.version_info >= (3, 11) and _strip_function_qualname:
                    return value.split('.')[-1]
            return value

        def build_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if attributes is None:
                return None
            attributes = {
                k: process_attribute(k, v)
                for k, v in attributes.items()
                if k != RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS or include_package_versions
            }
            if 'telemetry.sdk.version' in attributes:
                attributes['telemetry.sdk.version'] = '0.0.0'
            return attributes

        def build_event(event: Event) -> dict[str, Any]:
            res: dict[str, Any] = {
                'name': event.name,
                'timestamp': event.timestamp,
            }
            if event.attributes:
                res['attributes'] = attributes = dict(event.attributes)
                if 'exception.stacktrace' in attributes:
                    last_line = next(
                        line.strip()
                        for line in reversed(cast(str, event.attributes['exception.stacktrace']).split('\n'))
                        if line.strip()
                    )
                    attributes['exception.stacktrace'] = last_line
                if 'exception.logfire.trace' in attributes:
                    trace = json.loads(cast(str, attributes['exception.logfire.trace']))
                    stacks = trace['stacks']
                    for stack in stacks:
                        for frame in stack['frames']:
                            frame['filename'] = Path(frame['filename']).name
                            frame['lineno'] = fixed_line_number
                    attributes['exception.logfire.trace'] = json.dumps(trace)
            return res

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
            if include_resources:
                res['resource'] = {
                    'attributes': build_attributes(span.resource.attributes),
                }
            return res

        spans = [build_span(span) for span in self.exported_spans]
        return [
            span
            for span in spans
            if _include_start_spans is True
            or (span.get('attributes', {}).get(ATTRIBUTES_SPAN_TYPE_KEY, 'span') != 'start_span')
        ]


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
        if self.span_id_counter > 2**64 - 1:
            raise OverflowError('Span ID overflow')
        return self.span_id_counter

    def generate_trace_id(self) -> int:
        self.trace_id_counter += 1
        if self.trace_id_counter > 2**128 - 1:
            raise OverflowError('Trace ID overflow')
        return self.trace_id_counter


@dataclass(repr=True)
class SeededRandomIdGenerator(IdGenerator):
    """Generate random span/trace IDs from a random seed for deterministic tests.

    Trace IDs are 64-bit integers.
    Span IDs are 32-bit integers.
    """

    seed: int = 0

    def __post_init__(self) -> None:
        self.random = random.Random(self.seed)

    def generate_span_id(self) -> int:
        return self.random.getrandbits(64)

    def generate_trace_id(self) -> int:
        return self.random.getrandbits(128)


ONE_NANOSECOND = 1_000_000_000


# Making this a dataclass causes errors in the process pool end-to-end tests
class TimeGenerator:
    """Generate incrementing timestamps for testing.

    Timestamps are in nanoseconds, start at 1_000_000_000, and increment by 1_000_000_000 (1 second) each time.
    """

    def __init__(self, ns_time: int = 0):
        self.ns_time = ns_time

    def __call__(self) -> int:
        self.ns_time += ONE_NANOSECOND
        return self.ns_time

    def __repr__(self) -> str:
        return f'TimeGenerator(ns_time={self.ns_time})'


@dataclass
class LogfireTestExporter:
    exporter: TestExporter
    metrics_reader: InMemoryMetricReader


@pytest.fixture
def logfire_test_exporter() -> LogfireTestExporter:
    """A fixture that returns a LogfireTestExporter instance."""
    exporter = TestExporter()
    metrics_reader = InMemoryMetricReader()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        id_generator=IncrementalIdGenerator(),
        ns_timestamp_generator=TimeGenerator(),
        processors=[SimpleSpanProcessor(exporter)],
        metric_readers=[metrics_reader],
    )

    return LogfireTestExporter(exporter=exporter, metrics_reader=metrics_reader)
