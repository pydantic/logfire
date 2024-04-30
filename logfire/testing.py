"""Testing utilities for Logfire."""

from __future__ import annotations

import os
import random
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, cast

import pytest
from opentelemetry import trace
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.trace.id_generator import IdGenerator
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes

import logfire

from ._internal.constants import (
    ATTRIBUTES_SPAN_TYPE_KEY,
    ONE_SECOND_IN_NANOSECONDS,
    RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
)


class TestExporter(SpanExporter):
    """A SpanExporter that stores exported spans in a list for asserting in tests."""

    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None:
        self.exported_spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Exports a batch of telemetry data."""
        self.exported_spans.extend(spans)
        return SpanExportResult.SUCCESS

    def clear(self) -> None:
        """Clears the collected spans."""
        self.exported_spans = []

    def exported_spans_as_dict(
        self,
        fixed_line_number: int | None = 123,
        strip_filepaths: bool = True,
        include_resources: bool = False,
        include_package_versions: bool = False,
        include_instrumentation_scope: bool = False,
        _include_pending_spans: bool = False,
        _strip_function_qualname: bool = True,
    ) -> list[dict[str, Any]]:
        """The exported spans as a list of dicts.

        Args:
            fixed_line_number: The line number to use for all spans.
            strip_filepaths: Whether to strip the filepaths from the exported spans.
            include_resources: Whether to include the resource attributes in the exported spans.
            include_package_versions: Whether to include the package versions in the exported spans.
            include_instrumentation_scope: Whether to include the instrumentation scope in the exported spans.

        Returns:
            A list of dicts representing the exported spans.
        """

        def process_attribute(name: str, value: Any) -> Any:
            if name == 'code.filepath' and strip_filepaths:
                try:
                    return Path(value).name
                except ValueError:  # pragma: no cover
                    return value
            if name == 'code.lineno' and fixed_line_number is not None:
                return fixed_line_number
            if name == 'code.function':
                if sys.version_info >= (3, 11) and _strip_function_qualname:
                    return value.split('.')[-1]
            if name == ResourceAttributes.PROCESS_PID:
                assert value == os.getpid()
                return 1234
            if name == ResourceAttributes.SERVICE_INSTANCE_ID:
                if re.match(r'^[0-9a-f]{32}$', value):
                    return '0' * 32
            return value

        def build_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any] | None:
            if attributes is None:  # pragma: no branch
                return None  # pragma: no cover
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
            if event.attributes:  # pragma: no branch
                res['attributes'] = attributes = dict(event.attributes)
                if SpanAttributes.EXCEPTION_STACKTRACE in attributes:
                    last_line = next(  # pragma: no branch
                        line.strip()
                        for line in reversed(
                            cast(str, event.attributes[SpanAttributes.EXCEPTION_STACKTRACE]).split('\n')
                        )
                        if line.strip()
                    )
                    attributes[SpanAttributes.EXCEPTION_STACKTRACE] = last_line
            return res

        def build_instrumentation_scope(span: ReadableSpan) -> dict[str, Any]:
            if include_instrumentation_scope:
                return {'instrumentation_scope': span.instrumentation_scope and span.instrumentation_scope.name}
            else:
                return {}

        def build_span(span: ReadableSpan) -> dict[str, Any]:
            context = span.context or trace.INVALID_SPAN_CONTEXT
            res: dict[str, Any] = {
                'name': span.name,
                'context': {
                    'trace_id': context.trace_id,
                    'span_id': context.span_id,
                    'is_remote': context.is_remote,
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
                **build_instrumentation_scope(span),
                'attributes': build_attributes(span.attributes),
            }
            if span.events:
                res['events'] = [build_event(event) for event in span.events]
            if include_resources:
                resource_attributes = build_attributes(span.resource.attributes)
                res['resource'] = {
                    'attributes': resource_attributes,
                }
            return res

        spans = [build_span(span) for span in self.exported_spans]
        return [
            span
            for span in spans
            if _include_pending_spans is True
            or (span.get('attributes', {}).get(ATTRIBUTES_SPAN_TYPE_KEY, 'span') != 'pending_span')
        ]


@dataclass(repr=True)
class IncrementalIdGenerator(IdGenerator):
    """Generate sequentially incrementing span/trace IDs for testing.

    Trace IDs start at 1 and increment by 1 each time.
    Span IDs start at 1 and increment by 1 each time.
    """

    trace_id_counter = 0
    span_id_counter = 0

    def reset_trace_span_ids(self) -> None:  # pragma: no cover
        """Resets the trace and span ids."""
        self.trace_id_counter = 0
        self.span_id_counter = 0

    def generate_span_id(self) -> int:
        """Generates a span id."""
        self.span_id_counter += 1
        if self.span_id_counter > 2**64 - 1:  # pragma: no branch
            raise OverflowError('Span ID overflow')  # pragma: no cover
        return self.span_id_counter

    def generate_trace_id(self) -> int:
        """Generates a trace id."""
        self.trace_id_counter += 1
        if self.trace_id_counter > 2**128 - 1:  # pragma: no branch
            raise OverflowError('Trace ID overflow')  # pragma: no cover
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
        """Generates a random span id."""
        return self.random.getrandbits(64)

    def generate_trace_id(self) -> int:
        """Generates a random trace id."""
        return self.random.getrandbits(128)


# Making this a dataclass causes errors in the process pool end-to-end tests
class TimeGenerator:
    """Generate incrementing timestamps for testing.

    Timestamps are in nanoseconds, start at 1_000_000_000, and increment by 1_000_000_000 (1 second) each time.
    """

    def __init__(self, ns_time: int = 0):
        self.ns_time = ns_time

    def __call__(self) -> int:  # noqa: D102
        self.ns_time += ONE_SECOND_IN_NANOSECONDS
        return self.ns_time

    def __repr__(self) -> str:
        return f'TimeGenerator(ns_time={self.ns_time})'


@dataclass
class CaptureLogfire:
    """A dataclass that is holds both span exporter and metric renderer.

    This is used as the return type of `capfire` fixture.
    """

    exporter: TestExporter
    """The `TestExporter` instance."""
    metrics_reader: InMemoryMetricReader
    """The `InMemoryMetricReader` instance."""


@pytest.fixture
def capfire() -> CaptureLogfire:
    """A fixture that returns a CaptureLogfire instance."""
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

    return CaptureLogfire(exporter=exporter, metrics_reader=metrics_reader)
