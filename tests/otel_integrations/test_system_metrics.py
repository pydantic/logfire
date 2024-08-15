from __future__ import annotations

from inline_snapshot import snapshot
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import logfire
import logfire._internal.metrics
from tests.test_metrics import get_collected_metrics


def get_collected_metric_names(metrics_reader: InMemoryMetricReader) -> list[str]:
    return sorted(
        {
            metric['name']
            for metric in get_collected_metrics(metrics_reader)
            if metric['name'] != 'system.network.connections'
        }
    )


def test_default_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics()
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'system.cpu.simple_utilization',
            'system.memory.utilization',
            'system.swap.utilization',
        ]
    )
    SystemMetricsInstrumentor().uninstrument()  # type: ignore


def test_all_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics(base='full')
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'process.open_file_descriptor.count',
            'process.runtime.cpython.context_switches',
            'process.runtime.cpython.cpu.utilization',
            'process.runtime.cpython.cpu_time',
            'process.runtime.cpython.gc_count',
            'process.runtime.cpython.memory',
            'process.runtime.cpython.thread_count',
            'system.cpu.simple_utilization',
            'system.cpu.time',
            'system.cpu.utilization',
            'system.disk.io',
            'system.disk.operations',
            'system.disk.time',
            'system.memory.usage',
            'system.memory.utilization',
            'system.network.dropped_packets',
            'system.network.errors',
            'system.network.io',
            'system.network.packets',
            'system.swap.usage',
            'system.swap.utilization',
            'system.thread_count',
        ]
    )
    SystemMetricsInstrumentor().uninstrument()  # type: ignore
