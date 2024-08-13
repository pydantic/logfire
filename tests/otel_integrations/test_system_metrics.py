from __future__ import annotations

from inline_snapshot import snapshot
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import logfire
import logfire._internal.metrics
from logfire._internal.integrations.system_metrics import Config, parse_config
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
            'system.cpu.utilization',
            'system.memory.utilization',
            'system.swap.usage',
            'system.thread_count',
        ]
    )
    SystemMetricsInstrumentor().uninstrument()  # type: ignore


def test_single_system_metric_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics('system.cpu.time')
    assert get_collected_metric_names(metrics_reader) == [
        'system.cpu.time',
    ]
    SystemMetricsInstrumentor().uninstrument()  # type: ignore


def test_list_with_basic_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics(['basic', 'system.cpu.time'])
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'system.cpu.time',
            'system.cpu.utilization',
            'system.memory.utilization',
            'system.swap.usage',
            'system.thread_count',
        ]
    )
    SystemMetricsInstrumentor().uninstrument()  # type: ignore


def test_all_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics('all')
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'process.open_file_descriptor.count',
            'process.runtime.cpython.context_switches',
            'process.runtime.cpython.cpu.utilization',
            'process.runtime.cpython.cpu_time',
            'process.runtime.cpython.gc_count',
            'process.runtime.cpython.memory',
            'process.runtime.cpython.thread_count',
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


def test_dict_with_basic_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    config: Config = {
        'basic': None,
        'system.cpu.time': None,
        'system.cpu.utilization': ['idle'],
    }
    assert parse_config(config) == snapshot(
        {
            'system.thread_count': None,
            'system.cpu.utilization': [
                'idle',
            ],
            'system.memory.utilization': [
                'total',
                'available',
                'used',
                'free',
                'active',
                'inactive',
                'buffers',
                'cached',
                'shared',
                'wired',
                'slab',
            ],
            'system.swap.usage': [
                'used',
                'free',
            ],
            'system.cpu.time': [
                'idle',
                'user',
                'system',
                'irq',
                'softirq',
                'nice',
                'iowait',
                'steal',
                'interrupt',
                'dpc',
            ],
        }
    )
    logfire.instrument_system_metrics(config)
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'system.cpu.time',
            'system.cpu.utilization',
            'system.memory.utilization',
            'system.swap.usage',
            'system.thread_count',
        ]
    )
    SystemMetricsInstrumentor().uninstrument()  # type: ignore
