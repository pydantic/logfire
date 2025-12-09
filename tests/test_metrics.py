from __future__ import annotations

from typing import Any

import pytest
import requests
from dirty_equals import IsInt
from inline_snapshot import Is, snapshot
from opentelemetry import metrics
from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics import Counter, Histogram
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    InMemoryMetricReader,
    MetricExporter,
    MetricExportResult,
    MetricsData,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View

import logfire
from logfire._internal.config import METRICS_PREFERRED_TEMPORALITY
from logfire._internal.exporters.quiet_metrics import QuietMetricExporter
from logfire._internal.exporters.test import TestExporter
from logfire.testing import get_collected_metrics

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


def test_metrics_in_spans(exporter: TestExporter):
    tokens = logfire.metric_counter('tokens')

    with logfire.span('span'):
        tokens.add(100, attributes=dict(model='gpt4'))
        with logfire.span('nested_span'):
            tokens.add(200, attributes=dict(model='gpt4'))
            tokens.add(500, attributes=dict(model='gemini-2.5'))
        tokens.add(999)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'nested_span',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_metrics.py',
                    'code.function': 'test_metrics_in_spans',
                    'code.lineno': 123,
                    'logfire.msg_template': 'nested_span',
                    'logfire.msg': 'nested_span',
                    'logfire.span_type': 'span',
                    'logfire.metrics': {
                        'tokens': {
                            'details': [
                                {'attributes': {'model': 'gpt4'}, 'total': 200},
                                {'attributes': {'model': 'gemini-2.5'}, 'total': 500},
                            ],
                            'total': 700,
                        }
                    },
                },
            },
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_metrics.py',
                    'code.function': 'test_metrics_in_spans',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                    'logfire.metrics': {
                        'tokens': {
                            'details': [
                                {'attributes': {'model': 'gpt4'}, 'total': 300},
                                {'attributes': {'model': 'gemini-2.5'}, 'total': 500},
                                {'attributes': {}, 'total': 999},
                            ],
                            'total': 1799,
                        }
                    },
                },
            },
        ]
    )


def test_metrics_in_spans_disabled(exporter: TestExporter):
    # This method of setting collect_in_spans is a hack because using logfire.configure for this is annoying,
    # this way of doing it isn't guaranteed to work forever.
    metrics_options = logfire.DEFAULT_LOGFIRE_INSTANCE.config.metrics
    assert isinstance(metrics_options, logfire.MetricsOptions)
    metrics_options.collect_in_spans = False

    # operation.cost is special cased to always be collected regardless of config
    cost = logfire.metric_counter('operation.cost')
    tokens = logfire.metric_counter('tokens')  # not collected

    with logfire.span('span'):
        tokens.add(100)
        cost.add(200)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_metrics.py',
                    'code.function': 'test_metrics_in_spans_disabled',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                    'logfire.metrics': {
                        'operation.cost': {
                            'details': [{'attributes': {}, 'total': 200}],
                            'total': 200,
                        }
                    },
                },
            }
        ]
    )


def test_metrics_in_non_recording_spans(exporter: TestExporter, config_kwargs: dict[str, Any]):
    metrics_reader = InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)
    logfire.configure(
        **config_kwargs,
        sampling=logfire.SamplingOptions(head=0),
        metrics=logfire.MetricsOptions(
            additional_readers=[metrics_reader],
        ),
    )
    tokens = logfire.metric_counter('tokens')

    with logfire.span('span'):
        tokens.add(100, attributes=dict(model='gpt4'))

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == []

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'tokens',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {'model': 'gpt4'},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 100,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            }
        ]
    )


def test_reconfigure(caplog: pytest.LogCaptureFixture):
    for _ in range(3):
        logfire.configure(send_to_logfire=False, console=False)
        meter.create_histogram('foo', unit='x', description='bar', explicit_bucket_boundaries_advisory=[1, 2, 3])
    # Previously a bug caused a warning to be logged when reconfiguring the metrics
    assert not caplog.messages

    # For comparison, this logs a warning because the advisory is different (unset)
    meter.create_histogram('foo', unit='x', description='bar')
    assert caplog.messages


def test_metrics_options_default_views() -> None:
    """Test that MetricsOptions.DEFAULT_VIEWS is accessible as a class variable."""
    # DEFAULT_VIEWS should be accessible as a class variable
    assert logfire.MetricsOptions.DEFAULT_VIEWS is not None
    assert len(logfire.MetricsOptions.DEFAULT_VIEWS) == 2

    # Each element should be a View
    for view in logfire.MetricsOptions.DEFAULT_VIEWS:
        assert isinstance(view, View)


def test_metrics_options_default_views_unchanged() -> None:
    """Test that default views are used when not explicitly provided."""
    options = logfire.MetricsOptions()
    assert options.views is logfire.MetricsOptions.DEFAULT_VIEWS


def test_extend_default_views_with_attribute_filter(
    metrics_reader: InMemoryMetricReader, config_kwargs: dict[str, Any]
) -> None:
    """Test extending DEFAULT_VIEWS with a custom view that filters attributes.

    Verifies that:
    1. The custom view is applied (attributes are filtered)
    2. The default views still apply (histogram uses exponential bucket aggregation)
    """
    metrics_reader = InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)

    # Create a view that only keeps 'important' attribute for our custom counter
    custom_view = View(
        instrument_type=Counter,
        instrument_name='filtered_counter',
        attribute_keys={'important'},  # Only keep this attribute
    )

    logfire.configure(
        **config_kwargs,
        metrics=logfire.MetricsOptions(
            additional_readers=[metrics_reader],
            views=[*logfire.MetricsOptions.DEFAULT_VIEWS, custom_view],
        ),
    )

    # Test the custom view works
    counter = logfire.metric_counter('filtered_counter')
    counter.add(100, attributes={'important': 'yes', 'not_important': 'should_be_filtered'})

    # Also emit a histogram to verify default views still apply
    histogram = logfire.metric_histogram('test_histogram')
    histogram.record(50)

    collected = get_collected_metrics(metrics_reader)
    # Sort by name for consistent ordering
    collected = sorted(collected, key=lambda m: m['name'])

    assert collected == snapshot(
        [
            # Custom view applied: only 'important' attribute is present (not_important filtered out)
            {
                'name': 'filtered_counter',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {'important': 'yes'},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 100,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                    'is_monotonic': True,
                },
            },
            # Default view still applies: histogram uses exponential bucket aggregation
            # (has 'scale', 'positive', 'negative' instead of 'bucket_counts' and 'explicit_bounds')
            {
                'name': 'test_histogram',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 1,
                            'sum': 50,
                            'scale': IsInt(),
                            'zero_count': 0,
                            'positive': {'offset': IsInt(), 'bucket_counts': [1]},
                            'negative': {'offset': 0, 'bucket_counts': [0]},
                            'flags': 0,
                            'min': 50,
                            'max': 50,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                },
            },
        ]
    )


def test_replace_default_views(metrics_reader: InMemoryMetricReader, config_kwargs: dict[str, Any]) -> None:
    """Test replacing DEFAULT_VIEWS entirely with custom views.

    Verifies that:
    1. The custom view is applied (explicit bucket boundaries)
    2. The default views do NOT apply (other histogram uses OTel default, not exponential)
    """
    metrics_reader = InMemoryMetricReader(preferred_temporality=METRICS_PREFERRED_TEMPORALITY)

    # Replace default views with a custom histogram view using explicit buckets
    # (instead of the default exponential bucket histogram)
    custom_view = View(
        instrument_type=Histogram,
        instrument_name='custom_histogram',
        aggregation=ExplicitBucketHistogramAggregation(boundaries=[10, 50, 100, 500]),
    )

    logfire.configure(
        **config_kwargs,
        metrics=logfire.MetricsOptions(
            additional_readers=[metrics_reader],
            views=[custom_view],  # Completely replace default views
        ),
    )

    # Emit to the custom histogram (matched by our view)
    custom_histogram = logfire.metric_histogram('custom_histogram')
    custom_histogram.record(25)
    custom_histogram.record(75)
    custom_histogram.record(200)

    # Emit to another histogram NOT matched by our view
    # This should use OTel's default aggregation (explicit buckets), NOT exponential
    # buckets from DEFAULT_VIEWS (since we replaced them)
    other_histogram = logfire.metric_histogram('other_histogram')
    other_histogram.record(50)

    collected = get_collected_metrics(metrics_reader)
    # Sort by name for consistent ordering
    collected = sorted(collected, key=lambda m: m['name'])

    # Both histograms use explicit bucket aggregation (not exponential from DEFAULT_VIEWS)
    # - custom_histogram: uses our custom boundaries [10, 50, 100, 500]
    # - other_histogram: uses OTel's default boundaries (since DEFAULT_VIEWS was replaced)
    assert collected == snapshot(
        [
            # Custom view applied: explicit bucket histogram with our boundaries
            # 25 is in bucket 1 (10-50), 75 is in bucket 2 (50-100), 200 is in bucket 3 (100-500)
            {
                'name': 'custom_histogram',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 3,
                            'sum': 300,
                            'bucket_counts': [0, 1, 1, 1, 0],
                            'explicit_bounds': [10, 50, 100, 500],
                            'min': 25,
                            'max': 200,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                },
            },
            # DEFAULT_VIEWS is NOT applied: uses OTel's default explicit bucket aggregation
            # (has 'bucket_counts' and 'explicit_bounds', NOT 'scale'/'positive'/'negative')
            {
                'name': 'other_histogram',
                'description': '',
                'unit': '',
                'data': {
                    'data_points': [
                        {
                            'attributes': {},
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 1,
                            'sum': 50,
                            'bucket_counts': [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
                            'explicit_bounds': [
                                0.0,
                                5.0,
                                10.0,
                                25.0,
                                50.0,
                                75.0,
                                100.0,
                                250.0,
                                500.0,
                                750.0,
                                1000.0,
                                2500.0,
                                5000.0,
                                7500.0,
                                10000.0,
                            ],
                            'min': 50,
                            'max': 50,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': AggregationTemporality.DELTA,
                },
            },
        ]
    )
