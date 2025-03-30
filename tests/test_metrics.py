from __future__ import annotations

import json
from typing import Any, cast

import pytest
import requests
from dirty_equals import IsInt
from inline_snapshot import Is, snapshot
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    MetricsData,
)

import logfire
import logfire._internal.metrics
from logfire._internal.exporters.quiet_metrics import QuietMetricExporter

meter = metrics.get_meter('global_test_meter')

global_test_counter = meter.create_counter(name='global_test_counter')


def test_global_test_counter(metrics_reader: InMemoryMetricReader) -> None:
    global_test_counter.add(1)
    global_test_counter.add(20)
    metrics_reader.collect()
    global_test_counter.add(300)
    global_test_counter.add(4000)

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'global_test_counter',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 300 + 4000,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_create_metric_counter(metrics_reader: InMemoryMetricReader) -> None:
    counter = logfire.metric_counter('counter')
    counter.add(1)
    counter.add(20)
    # Here we only call `.collect()` because it's the public MetricReader API,
    # (e.g. it's called regularly by `PeriodicExportingMetricReader` which is what logfire uses by default)
    # and we want to test the result of calling only 'real' methods.
    # It doesn't return anything so we can't check the results.
    # `get_collected_metrics` below calls `metrics_reader.get_metrics_data()`,
    # but that method only exists on `InMemoryMetricReader`,
    # and it further modifies the internal state of `metrics_reader` so calling it here feels wrong.
    metrics_reader.collect()
    counter.add(300)
    counter.add(4000)

    # The total value doesn't include `1 + 20` because it was collected in the first call to `.collect()`,
    # so only add calls since then are included, hence the line:
    #   'aggregation_temporality': AggregationTemporality.DELTA
    # as opposed to the default `AggregationTemporality.CUMULATIVE`.
    # This is thanks to this setting in the metric reader:
    #   preferred_temporality=METRICS_PREFERRED_TEMPORALITY
    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'counter',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 300 + 4000,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_create_metric_histogram(metrics_reader: InMemoryMetricReader) -> None:
    histogram = logfire.metric_histogram('histogram')
    histogram.record(1)
    histogram.record(20)
    metrics_reader.collect()
    histogram.record(300)
    histogram.record(4000)

    # Here's a bit of explanation behind the produced data.
    # These two numbers define the 'layout' of the exponential histogram buckets for this data.
    # They're specific to this batch of data, i.e. they account for 300 and 4000, not 1 and 20
    offset = 263  # somewhat high because 300 is far from 0
    scale = 5  # meaning we're a *bit* 'zoomed in' because 300 and 4000 are somewhat close in the grand scheme of things
    bucket_counts = [0] * 128
    # 300 goes in 'bucket 0', 4000 goes in 'bucket 119'
    buckets = {0: 300, 119: 4000}
    for i, value in buckets.items():
        bucket_counts[i] = 1  # i.e. 1 value in this bucket
        # These are the bounds of the bucket
        assert 2 ** ((offset + i) / 2**scale) < value < 2 ** ((offset + i + 1) / 2**scale)

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'histogram',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 2,
                            'sum': 4300,
                            'scale': scale,
                            'zero_count': 0,
                            'positive': {'offset': offset, 'bucket_counts': Is(bucket_counts)},
                            'negative': {'offset': 0, 'bucket_counts': [0]},
                            'flags': 0,
                            'min': 300,
                            'max': 4000,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                },
            }
        ]
    )


def test_create_metric_gauge(metrics_reader: InMemoryMetricReader) -> None:
    temperature = logfire.metric_gauge('temperature')
    temperature.set(1)
    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'temperature',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': None,
                            'time_unix_nano': IsInt(),
                            'value': 1,
                            'exemplars': [],
                        }
                    ]
                },
            }
        ]
    )

    # The value is updated, not accumulated. The previous value is overwritten.
    temperature.set(20)
    temperature.set(24)
    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'temperature',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': None,
                            'time_unix_nano': IsInt(),
                            'value': 24,
                            'exemplars': [],
                        }
                    ]
                },
            }
        ]
    )


def test_create_metric_gauge_old_opentelemetry_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logfire._internal.metrics, 'Gauge', None)
    with pytest.raises(RuntimeError) as exc_info:
        logfire.metric_gauge('gauge')
    assert str(exc_info.value) == snapshot("""\
Gauge is not available in this version of OpenTelemetry SDK.
You should upgrade to 1.23.0 or newer:
   pip install opentelemetry-sdk>=1.23.0\
""")


def test_create_metric_up_down_counter(metrics_reader: InMemoryMetricReader) -> None:
    counter = logfire.metric_up_down_counter('up_down_counter')
    counter.add(1)
    counter.add(20)
    metrics_reader.collect()
    counter.add(300)
    counter.add(4000)

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'up_down_counter',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 4321,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.CUMULATIVE,
                    'is_monotonic': False,
                },
            }
        ]
    )


def test_create_metric_counter_callback(metrics_reader: InMemoryMetricReader) -> None:
    observation = Observation(21)

    def observable_counter(options: CallbackOptions):
        yield observation

    logfire.metric_counter_callback('counter_callback', callbacks=[observable_counter])

    metrics_reader.collect()
    # Observable callbacks should report the cumulative total, not deltas.
    observation = Observation(4321)

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'counter_callback',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 4300,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_create_metric_gauge_callback(metrics_reader: InMemoryMetricReader) -> None:
    observations = [Observation(1), Observation(20)]

    def observable_gauge(options: CallbackOptions):
        return observations

    logfire.metric_gauge_callback('gauge_callback', callbacks=[observable_gauge])

    metrics_reader.collect()
    observations = [Observation(300), Observation(4000)]

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'gauge_callback',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': None,
                            'time_unix_nano': IsInt(),
                            'value': 4000,
                            'exemplars': [],
                        }
                    ]
                },
            }
        ]
    )


def test_create_metric_up_down_counter_callback(metrics_reader: InMemoryMetricReader) -> None:
    observation = Observation(21)

    def observable_counter(options: CallbackOptions):
        yield observation

    logfire.metric_up_down_counter_callback('up_down_counter_callback', callbacks=[observable_counter])

    metrics_reader.collect()
    # Observable callbacks should report the cumulative total, not deltas.
    observation = Observation(4321)

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'up_down_counter_callback',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 4321,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.CUMULATIVE,
                    'is_monotonic': False,
                },
            }
        ]
    )


def get_collected_metrics(metrics_reader: InMemoryMetricReader) -> list[dict[str, Any]]:
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    [resource_metric] = exported_metrics['resource_metrics']
    return [metric for scope_metric in resource_metric['scope_metrics'] for metric in scope_metric['metrics']]


def test_quiet_metric_exporter(caplog: pytest.LogCaptureFixture) -> None:
    force_flush_called = False
    shutdown_called = False

    class ConnectionErrorExporter(MetricExporter):
        def export(
            self, metrics_data: MetricsData, timeout_millis: float = 10_000, **kwargs: Any
        ) -> MetricExportResult:
            raise requests.exceptions.ConnectionError('Test connection error')

        def force_flush(self, timeout_millis: float = 10_000) -> bool:
            nonlocal force_flush_called
            force_flush_called = True
            return True

        def shutdown(self, timeout_millis: float = 30_000, **kwargs: Any) -> None:
            nonlocal shutdown_called
            shutdown_called = True

    exporter = QuietMetricExporter(ConnectionErrorExporter())
    result = exporter.export(MetricsData([]))
    assert result == MetricExportResult.FAILURE
    assert not caplog.messages

    assert not force_flush_called
    assert not shutdown_called
    exporter.force_flush()
    exporter.shutdown()
    assert force_flush_called
    assert shutdown_called
