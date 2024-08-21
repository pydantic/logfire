from __future__ import annotations

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import logfire
import logfire._internal.metrics
from logfire._internal.integrations.system_metrics import get_base_config
from tests.test_metrics import get_collected_metrics


def get_collected_metric_names(metrics_reader: InMemoryMetricReader) -> list[str]:
    try:
        return sorted(
            {
                metric['name']
                for metric in get_collected_metrics(metrics_reader)
                if metric['name'] != 'system.network.connections'
            }
        )
    finally:
        SystemMetricsInstrumentor().uninstrument()  # type: ignore


def test_default_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics()
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'process.runtime.cpython.cpu.utilization',
            'system.cpu.simple_utilization',
            'system.memory.utilization',
            'system.swap.utilization',
        ]
    )


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


def test_custom_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics({'system.memory.utilization': ['available']}, base=None)
    assert get_collected_metric_names(metrics_reader) == ['system.memory.utilization']


def test_basic_base():
    assert get_base_config('basic') == {
        'process.runtime.cpu.utilization': None,
        'system.cpu.simple_utilization': None,
        'system.memory.utilization': ['available'],
        'system.swap.utilization': ['used'],
    }, 'Docs need to be updated if this test fails'


def test_full_base():
    config = get_base_config('full')
    config.pop('system.network.connections', None)
    assert config == {
        'system.cpu.simple_utilization': None,
        'system.cpu.time': ['idle', 'user', 'system', 'irq', 'softirq', 'nice', 'iowait', 'steal', 'interrupt', 'dpc'],
        'system.cpu.utilization': [
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
        'system.memory.usage': [
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
            'total',
        ],
        'system.memory.utilization': [
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
        'system.swap.usage': ['used', 'free'],
        'system.swap.utilization': ['used'],
        'system.disk.io': ['read', 'write'],
        'system.disk.operations': ['read', 'write'],
        'system.disk.time': ['read', 'write'],
        'system.network.dropped.packets': ['transmit', 'receive'],
        'system.network.packets': ['transmit', 'receive'],
        'system.network.errors': ['transmit', 'receive'],
        'system.network.io': ['transmit', 'receive'],
        'system.thread_count': None,
        'process.runtime.memory': ['rss', 'vms'],
        'process.runtime.cpu.time': ['user', 'system'],
        'process.runtime.gc_count': None,
        'process.runtime.thread_count': None,
        'process.runtime.cpu.utilization': None,
        'process.runtime.context_switches': ['involuntary', 'voluntary'],
        'process.open_file_descriptor.count': None,
    }, 'Docs and the MetricName type need to be updated if this test fails'


def test_empty_base():
    assert get_base_config(None) == {}


def test_invalid_base():
    with pytest.raises(ValueError):
        get_base_config('invalid')  # type: ignore
