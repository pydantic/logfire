"""Testing utilities for Logfire. See [the guide](https://logfire.pydantic.dev/docs/reference/advanced/testing/) for examples."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import Any, cast

import pytest
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator

import logfire

from ._internal.config import METRICS_PREFERRED_TEMPORALITY
from ._internal.constants import ONE_SECOND_IN_NANOSECONDS
from ._internal.exporters.test import TestExporter, TestLogExporter
from ._internal.utils import SeededRandomIdGenerator

__all__ = [
    'capfire',
    'CaptureLogfire',
    'IncrementalIdGenerator',
    'SeededRandomIdGenerator',
    'TimeGenerator',
    'TestExporter',
    'TestLogExporter',
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
    """A dataclass that holds a span exporter, log exporter, and metric reader.

    This is used as the return type of `capfire` fixture.
    """

    exporter: TestExporter
    """The span exporter."""
    metrics_reader: InMemoryMetricReader
    """The metric reader."""
    log_exporter: TestLogExporter
    """The log exporter."""
    id_generator: IncrementalIdGenerator
    """The id generator used by `capfire`."""
    ns_timestamp_generator: TimeGenerator
    """The timestamp generator used by `capfire`."""

    def get_collected_metrics(self):
        """Get the collected metrics as a list of dictionaries."""
        return get_collected_metrics(self.metrics_reader)

    def reconfigure(self, **kwargs: Any) -> None:
        """Reconfigure logfire from within a test, merging `kwargs` with the `capfire` defaults.

        `additional_span_processors`, `advanced.log_record_processors`, and `metrics.additional_readers`
        extend the capfire defaults. Other kwargs replace them. Pass `metrics=False` to disable metrics.

        `exporter`, `log_exporter`, `id_generator`, and `ns_timestamp_generator` are reused as the base
        values for the merge; if the user overrides `id_generator` or `ns_timestamp_generator` via
        `advanced=`, the corresponding attribute on `self` is updated to reflect the new value.

        `metrics_reader` is always replaced with a fresh `InMemoryMetricReader` (OTel forbids reusing one
        across `MeterProvider` instances), so pre-reconfigure metrics are not queryable afterwards.
        """
        advanced = kwargs.pop('advanced', None)
        metrics = kwargs.pop('metrics', None)
        additional_span_processors = kwargs.pop('additional_span_processors', None)

        self.metrics_reader = InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)

        base_advanced = logfire.AdvancedOptions(
            id_generator=self.id_generator,
            ns_timestamp_generator=self.ns_timestamp_generator,
            log_record_processors=[SimpleLogRecordProcessor(self.log_exporter)],
        )
        base_metrics = logfire.MetricsOptions(additional_readers=[self.metrics_reader])

        if advanced is None:
            merged_advanced = base_advanced
        else:
            merged_advanced = _merge_dataclass(base_advanced, advanced, 'log_record_processors')
            self.id_generator = merged_advanced.id_generator
            self.ns_timestamp_generator = merged_advanced.ns_timestamp_generator

        if metrics is None:
            merged_metrics = base_metrics
        elif metrics is False:
            merged_metrics = False
        else:
            merged_metrics = _merge_dataclass(base_metrics, metrics, 'additional_readers')

        base_processors = [SimpleSpanProcessor(self.exporter)]
        if additional_span_processors is None:
            merged_processors = base_processors
        else:
            merged_processors = [*base_processors, *additional_span_processors]

        logfire.configure(
            send_to_logfire=kwargs.pop('send_to_logfire', False),
            console=kwargs.pop('console', False),
            advanced=merged_advanced,
            additional_span_processors=merged_processors,
            metrics=merged_metrics,
            **kwargs,
        )


def _merge_dataclass(default: Any, user: Any, extend_field: str) -> Any:
    """Merge `user` into `default`, extending the `extend_field` list and overriding other non-default fields.

    A field on `user` is treated as "overriding" only when its value differs from the field's dataclass
    default. A user cannot explicitly reset a field to its default value (the override is silently
    skipped). Identity-comparison fields (e.g. `ns_timestamp_generator`) look "set" when the user passes
    a *different* object, but are silently skipped when the user passes the exact default object.
    """
    overrides: dict[str, Any] = {extend_field: [*getattr(default, extend_field), *getattr(user, extend_field)]}
    for f in dataclasses.fields(user):
        if f.name == extend_field:
            continue
        user_val = getattr(user, f.name)
        if f.default is not dataclasses.MISSING:
            if user_val != f.default:
                overrides[f.name] = user_val
        elif f.default_factory is not dataclasses.MISSING:
            if user_val != f.default_factory():
                overrides[f.name] = user_val
        else:  # pragma: no cover
            # No AdvancedOptions or MetricsOptions field is required today; this branch is a
            # defensive guard for future fields without a default.
            overrides[f.name] = user_val
    return dataclasses.replace(default, **overrides)


@pytest.fixture
def capfire() -> CaptureLogfire:
    """A fixture that returns a CaptureLogfire instance."""
    exporter = TestExporter()
    metrics_reader = InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)
    time_generator = TimeGenerator()
    log_exporter = TestLogExporter(time_generator)
    id_generator = IncrementalIdGenerator()
    logfire.configure(
        send_to_logfire=False,
        console=False,
        advanced=logfire.AdvancedOptions(
            id_generator=id_generator,
            ns_timestamp_generator=time_generator,
            log_record_processors=[SimpleLogRecordProcessor(log_exporter)],
        ),
        additional_span_processors=[SimpleSpanProcessor(exporter)],
        metrics=logfire.MetricsOptions(additional_readers=[metrics_reader]),
    )

    return CaptureLogfire(
        exporter=exporter,
        metrics_reader=metrics_reader,
        log_exporter=log_exporter,
        id_generator=id_generator,
        ns_timestamp_generator=time_generator,
    )


def get_collected_metrics(metrics_reader: InMemoryMetricReader) -> list[dict[str, Any]]:
    """Get the collected metrics as a list of dictionaries."""
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())
    [resource_metric] = exported_metrics['resource_metrics']
    return [metric for scope_metric in resource_metric['scope_metrics'] for metric in scope_metric['metrics']]
