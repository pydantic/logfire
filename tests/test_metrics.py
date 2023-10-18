import json
from typing import cast

from opentelemetry.sdk.metrics.export import InMemoryMetricReader, MetricsData


def test_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    exported_metrics = json.loads(cast(MetricsData, metrics_reader.get_metrics_data()).to_json())  # type: ignore
    # insert_assert(exported_metrics)

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
