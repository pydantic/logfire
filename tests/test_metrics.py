import json
from typing import cast

from opentelemetry.metrics import CallbackOptions, Observation
from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData

import logfire


def test_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore

    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    # collected metrics vary by platform, etc.
    # assert that we at least collected _some_ of the metrics we expect
    assert metrics_collected.issuperset(
        {
            'system.swap.usage',
            'system.disk.operations',
            'system.memory.usage',
            'system.cpu.utilization',
        }
    ), metrics_collected


def test_create_metric_counter(metrics_reader: InMemoryMetricReader) -> None:
    counter = logfire.metric_counter('counter')
    counter.add(1)

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'counter' in metrics_collected


def test_create_metric_histogram(metrics_reader: InMemoryMetricReader) -> None:
    histogram = logfire.metric_histogram('histogram')
    histogram.record(1)

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'histogram' in metrics_collected


def test_create_metric_up_down_counter(metrics_reader: InMemoryMetricReader) -> None:
    up_down_counter = logfire.metric_up_down_counter('up_down_counter')
    up_down_counter.add(1)

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'up_down_counter' in metrics_collected


def test_create_metric_counter_callback(metrics_reader: InMemoryMetricReader) -> None:
    def observable_counter(options: CallbackOptions):
        yield Observation(1)

    logfire.metric_counter_callback('counter_callback', callbacks=[observable_counter])

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'counter_callback' in metrics_collected


def test_create_metric_gauge_callback(metrics_reader: InMemoryMetricReader) -> None:
    def observable_gauge(options: CallbackOptions):
        yield Observation(1)

    logfire.metric_gauge_callback('gauge_callback', callbacks=[observable_gauge])

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'gauge_callback' in metrics_collected


def test_create_metric_up_down_counter_callback(metrics_reader: InMemoryMetricReader) -> None:
    def observable_up_down_counter(options: CallbackOptions):
        yield Observation(1)

    logfire.metric_up_down_counter_callback('up_down_counter_callback', callbacks=[observable_up_down_counter])

    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    metrics_collected = {
        metric['name']
        for resource_metric in exported_metrics['resource_metrics']
        for scope_metric in resource_metric['scope_metrics']
        for metric in scope_metric['metrics']
    }

    assert 'up_down_counter_callback' in metrics_collected
