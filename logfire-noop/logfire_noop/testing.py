"""Testing utilities for Logfire."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import ReadableSpan
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.sdk.trace.id_generator import IdGenerator


import logfire


class TestExporter(SpanExporter):
    """A SpanExporter that stores exported spans in a list for asserting in tests."""

    # NOTE: Avoid test discovery by pytest.
    __test__ = False

    def __init__(self) -> None: ...

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        """Exports a batch of telemetry data."""
        return SpanExportResult.SUCCESS

    def clear(self) -> None:
        """Clears the collected spans."""

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
        return [{}]


@dataclass(repr=True)
class IncrementalIdGenerator(IdGenerator):
    """Generate sequentially incrementing span/trace IDs for testing.

    Trace IDs start at 1 and increment by 1 each time.
    Span IDs start at 1 and increment by 1 each time.
    """

    trace_id_counter = 0
    span_id_counter = 0

    def reset_trace_span_ids(self) -> None:
        """Resets the trace and span ids."""

    def generate_span_id(self) -> int:
        """Generates a span id."""
        return 1

    def generate_trace_id(self) -> int:
        """Generates a trace id."""
        return 1


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
