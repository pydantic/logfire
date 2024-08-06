"""Testing utilities for Logfire."""

from __future__ import annotations

import random
from dataclasses import dataclass

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator

import logfire

from ._internal.constants import ONE_SECOND_IN_NANOSECONDS
from ._internal.exporters.test import TestExporter

__all__ = [
    'capfire',
    'CaptureLogfire',
    'IncrementalIdGenerator',
    'SeededRandomIdGenerator',
    'TimeGenerator',
    'TestExporter',
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
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        additional_metric_readers=[metrics_reader],
    )

    return CaptureLogfire(exporter=exporter, metrics_reader=metrics_reader)
