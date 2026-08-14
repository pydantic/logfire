from __future__ import annotations

import logging
from typing import NamedTuple

import psutil
import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import logfire
from logfire._internal.integrations import system_metrics
from logfire._internal.integrations.system_metrics import get_base_config
from tests.test_metrics import get_collected_metrics


class Partition(NamedTuple):
    device: str
    mountpoint: str
    fstype: str
    opts: str


class PartitionWithLimits(NamedTuple):
    device: str
    mountpoint: str
    fstype: str
    opts: str
    maxfile: int
    maxpath: int


class Usage(NamedTuple):
    total: int
    used: int
    free: int
    percent: float


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
        SystemMetricsInstrumentor().uninstrument()


def process_disk_io_supported() -> bool:
    io_counters = getattr(psutil.Process(), 'io_counters', None)
    if io_counters is None:
        return False
    try:
        io_counters()
    except (AttributeError, NotImplementedError, PermissionError):
        return False
    return True


def test_default_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics()
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'process.cpu.utilization',
            'system.cpu.simple_utilization',
            'system.memory.utilization',
            'system.swap.utilization',
        ]
    )


def test_all_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics(base='full')
    collected_metric_names = get_collected_metric_names(metrics_reader)
    if process_disk_io_supported():
        collected_metric_names.pop(collected_metric_names.index('process.disk.io'))

    assert collected_metric_names == snapshot(
        [
            'cpython.gc.collected_objects',
            'cpython.gc.collections',
            'cpython.gc.uncollectable_objects',
            'process.context_switches',
            'process.cpu.core_utilization',
            'process.cpu.time',
            'process.cpu.utilization',
            'process.memory.usage',
            'process.memory.virtual',
            'process.open_file_descriptor.count',
            'process.runtime.cpython.gc_count',
            'process.thread.count',
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


def test_measure_process_runtime_cpu_utilization(metrics_reader: InMemoryMetricReader) -> None:
    # This metric is now deprecated by OTEL, but there isn't a strong reason to stop allowing it when requested
    logfire.instrument_system_metrics({'process.runtime.cpu.utilization': None}, base=None)  # type: ignore
    assert get_collected_metric_names(metrics_reader) == ['process.runtime.cpython.cpu.utilization']


def test_custom_system_metrics_collection(metrics_reader: InMemoryMetricReader) -> None:
    logfire.instrument_system_metrics(
        {
            'system.memory.utilization': ['available'],
            'process.cpu.core_utilization': None,
            'process.cpu.utilization': None,
        },
        base=None,
    )
    assert get_collected_metric_names(metrics_reader) == snapshot(
        [
            'process.cpu.core_utilization',
            'process.cpu.utilization',
            'system.memory.utilization',
        ]
    )


def test_basic_base():
    assert get_base_config('basic') == {
        'process.cpu.utilization': None,
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
        'process.runtime.gc_count': None,
        'process.open_file_descriptor.count': None,
        'process.memory.usage': None,
        'process.memory.virtual': None,
        'process.cpu.time': ['user', 'system'],
        # There's no reason for OTel to give a value here, so the docs say `None`
        'process.cpu.utilization': None,
        'process.cpu.core_utilization': None,
        'process.disk.io': ['read', 'write'],
        'process.thread.count': None,
        'process.context_switches': ['involuntary', 'voluntary'],
        'cpython.gc.collected_objects': None,
        'cpython.gc.collections': None,
        'cpython.gc.uncollectable_objects': None,
    }, 'Docs and the MetricName type need to be updated if this test fails'


def test_empty_base():
    assert get_base_config(None) == {}


def test_invalid_base():
    with pytest.raises(ValueError):
        get_base_config('invalid')  # type: ignore


def test_filesystem_metrics(metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch) -> None:
    partition = PartitionWithLimits('/dev/data', '/work', 'EXT4', 'rw,relatime', 255, 1024)
    usage = Usage(100, 40, 50, 80)
    usage_calls: list[str] = []

    def disk_partitions(*, all: bool) -> list[PartitionWithLimits]:
        return [partition]

    def disk_usage(path: str) -> Usage:
        usage_calls.append(path)
        return usage

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    filesystem_config: system_metrics.FilesystemConfig = {
        'paths': ['/work/app'],
        'states': ['used', 'reserved'],
    }
    logfire.instrument_system_metrics(
        {
            'system.filesystem.usage': filesystem_config,
            'system.filesystem.limit': filesystem_config,
            'system.filesystem.utilization': filesystem_config,
        },
        base=None,
    )
    metrics = {metric['name']: metric for metric in get_collected_metrics(metrics_reader)}

    assert usage_calls == ['/work/app'] * 3
    assert set(metrics) == {
        'system.filesystem.usage',
        'system.filesystem.limit',
        'system.filesystem.utilization',
    }
    assert metrics['system.filesystem.usage']['unit'] == 'By'
    assert metrics['system.filesystem.usage']['data']['is_monotonic'] is False
    points = metrics['system.filesystem.usage']['data']['data_points']
    assert [(point['attributes']['system.filesystem.state'], point['value']) for point in points] == [
        ('used', 40),
        ('reserved', 10),
    ]
    assert points[0]['attributes'] == {
        'system.device': '/dev/data',
        'system.filesystem.mode': 'rw',
        'system.filesystem.mountpoint': '/work',
        'system.filesystem.state': 'used',
        'system.filesystem.type': 'ext4',
    }
    assert metrics['system.filesystem.limit']['unit'] == 'By'
    assert metrics['system.filesystem.limit']['data']['is_monotonic'] is False
    limit_point = metrics['system.filesystem.limit']['data']['data_points'][0]
    assert limit_point['value'] == 100
    assert limit_point['attributes']['system.filesystem.mode'] == 'rw'
    assert metrics['system.filesystem.utilization']['unit'] == '1'
    utilization_point = metrics['system.filesystem.utilization']['data']['data_points'][0]
    assert utilization_point['value'] == pytest.approx(40 / 90)
    assert utilization_point['attributes']['system.filesystem.state'] == 'used'
    assert utilization_point['attributes']['system.filesystem.mode'] == 'rw'
    SystemMetricsInstrumentor().uninstrument()


@pytest.mark.parametrize('error', [OSError('gone'), ValueError('invalid path')])
def test_filesystem_failures_warn_once_and_keep_other_metrics(
    error: Exception,
    metrics_reader: InMemoryMetricReader,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    partition_calls = 0

    def disk_partitions(*, all: bool) -> list[Partition]:
        nonlocal partition_calls
        partition_calls += 1
        raise system_metrics.psutil.AccessDenied(pid=1, name='partitions')

    def disk_usage(path: str) -> None:
        raise error

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)
    logfire.instrument_system_metrics({'system.filesystem.utilization': {'paths': ['/gone']}}, base='basic')

    with caplog.at_level(logging.WARNING):
        get_collected_metrics(metrics_reader)
        get_collected_metrics(metrics_reader)
    assert [record.message for record in caplog.records if record.name == system_metrics.__name__] == [
        "Unable to inspect filesystem mount points: (pid=1, name='partitions')",
        f"Unable to collect filesystem metrics for '/gone': {error}",
    ]
    assert partition_calls == 2
    assert 'system.cpu.simple_utilization' in get_collected_metric_names(metrics_reader)


def test_filesystem_exact_metric_subset(metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch) -> None:
    def disk_partitions(*, all: bool) -> list[Partition]:
        return [Partition('/dev/data', '/work', 'ext4', 'ro,relatime')]

    def disk_usage(path: str) -> Usage:
        return Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics({'system.filesystem.limit': {'paths': ['/work/app']}}, base=None)
    metrics = get_collected_metrics(metrics_reader)

    assert [metric['name'] for metric in metrics] == ['system.filesystem.limit']
    assert metrics[0]['data']['data_points'][0]['attributes']['system.filesystem.mode'] == 'ro'


def test_filesystem_enumeration_failure_uses_fallback_identity(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_partitions(*, all: bool) -> list[Partition]:
        raise NotImplementedError('unsupported')

    def disk_usage(path: str) -> Usage:
        return Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics({'system.filesystem.limit': {'paths': ['/work/app']}}, base=None)
    point = get_collected_metrics(metrics_reader)[0]['data']['data_points'][0]

    assert point['attributes'] == {
        'system.device': '/work/app',
        'system.filesystem.mountpoint': '/work/app',
    }


def test_filesystem_config_validation() -> None:
    with pytest.raises(ValueError, match='At most 32 filesystem paths'):
        logfire.instrument_system_metrics(
            {'system.filesystem.usage': {'paths': [f'/mnt/{index}' for index in range(33)]}}, base=None
        )

    with pytest.raises(ValueError, match='Invalid filesystem states'):
        logfire.instrument_system_metrics(
            {'system.filesystem.usage': {'states': ['used', 'cached']}},
            base=None,
        )

    with pytest.raises(ValueError, match='Filesystem metric keys must use the same configuration'):
        logfire.instrument_system_metrics(
            {
                'system.filesystem.usage': {'paths': ['/']},
                'system.filesystem.limit': {'paths': ['/tmp']},
            },
            base=None,
        )

    with pytest.raises(ValueError, match='must be a dictionary or None'):
        logfire.instrument_system_metrics({'system.filesystem.limit': ['/']}, base=None)


def test_filesystem_none_paths_uses_current_working_directory(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    usage_calls: list[str] = []

    monkeypatch.setattr(system_metrics.os, 'getcwd', lambda: '/work')

    def disk_partitions(*, all: bool) -> list[Partition]:
        return []

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)

    def disk_usage(path: str) -> Usage:
        usage_calls.append(path)
        return Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)
    logfire.instrument_system_metrics({'system.filesystem.limit': {'paths': None}}, base=None)

    assert get_collected_metrics(metrics_reader)[0]['data']['data_points'][0]['value'] == 100
    assert usage_calls == ['/work']


def test_filesystem_none_config_uses_current_working_directory(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_partitions(*, all: bool) -> list[Partition]:
        return []

    def disk_usage(path: str) -> Usage:
        return Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.os, 'getcwd', lambda: '/work')
    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics({'system.filesystem.limit': None}, base=None)

    point = get_collected_metrics(metrics_reader)[0]['data']['data_points'][0]
    assert point['value'] == 100
    assert point['attributes'] == {
        'system.device': '/work',
        'system.filesystem.mountpoint': '/work',
    }


def test_macos_firmlink_and_root_use_data_volume(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Partition('/dev/system', '/', 'apfs', 'ro')
    data = Partition('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')
    root_usage = Usage(100, 10, 40, 20)
    data_usage = Usage(100, 50, 40, 55)
    calls: list[str] = []

    def disk_usage(path: str) -> Usage:
        calls.append(path)
        return {
            '/': root_usage,
            '/System/Volumes/Data': data_usage,
            '/Users/me/app': data_usage,
        }[path]

    def disk_partitions(*, all: bool) -> list[Partition]:
        return [root, data]

    monkeypatch.setattr(system_metrics.sys, 'platform', 'darwin')
    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics(
        {'system.filesystem.limit': {'paths': ['/', '/Users/me/app']}},
        base=None,
    )
    points = get_collected_metrics(metrics_reader)[0]['data']['data_points']

    assert len(points) == 1
    assert points[0]['value'] == data_usage.total
    assert points[0]['attributes'] == {
        'system.device': '/dev/data',
        'system.filesystem.mode': 'rw',
        'system.filesystem.mountpoint': '/System/Volumes/Data',
        'system.filesystem.type': 'apfs',
    }
    assert calls.count('/System/Volumes/Data') == 1
    assert calls.count('/Users/me/app') == 1
    assert calls.count('/') == 1


def test_macos_data_volume_failure_falls_back_to_root(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Partition('/dev/system', '/', '', 'ro')
    data = Partition('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')
    root_usage = Usage(100, 10, 40, 20)

    def disk_usage(path: str) -> Usage:
        if path == data.mountpoint:
            raise OSError('data unavailable')
        assert path == root.mountpoint
        return root_usage

    def disk_partitions(*, all: bool) -> list[Partition]:
        return [root, data]

    monkeypatch.setattr(system_metrics.sys, 'platform', 'darwin')
    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics({'system.filesystem.limit': {'paths': ['/']}}, base=None)
    point = get_collected_metrics(metrics_reader)[0]['data']['data_points'][0]

    assert point['value'] == root_usage.total
    assert point['attributes'] == {
        'system.device': '/dev/system',
        'system.filesystem.mode': 'ro',
        'system.filesystem.mountpoint': '/',
    }


def test_equal_usage_bind_mount_prefers_lexical_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Partition('/dev/root', '/', 'ext4', 'rw')
    selected = Partition('/dev/data', '/srv/data', 'ext4', 'rw')
    bind = Partition('/dev/data', '/mnt/bind', 'ext4', 'rw')
    usage = Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.sys, 'platform', 'linux')
    partition = system_metrics._identify_partition(  # pyright: ignore[reportPrivateUsage]
        '/srv/data/app', usage, [root, selected, bind], lambda path: usage
    )

    assert partition is selected


def test_macos_ambiguous_usage_match_does_not_choose_unrelated_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Partition('/dev/system', '/', 'apfs', 'ro')
    data = Partition('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')
    clone = Partition('/dev/clone', '/Volumes/clone', 'apfs', 'rw')
    selected_usage = Usage(100, 50, 40, 55)
    root_usage = Usage(100, 10, 40, 20)
    usages = {'/': root_usage, '/System/Volumes/Data': selected_usage, '/Volumes/clone': selected_usage}

    monkeypatch.setattr(system_metrics.sys, 'platform', 'darwin')
    partition = system_metrics._identify_partition(  # pyright: ignore[reportPrivateUsage]
        '/Users/me/app', selected_usage, [root, data, clone], lambda path: usages[path]
    )

    assert partition is root


def test_macos_failed_usage_matches_use_lexical_partition(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Partition('/dev/system', '/', 'apfs', 'ro')
    data = Partition('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')
    selected_usage = Usage(100, 50, 40, 55)

    monkeypatch.setattr(system_metrics.sys, 'platform', 'darwin')
    partition = system_metrics._identify_partition(  # pyright: ignore[reportPrivateUsage]
        '/Users/me/app', selected_usage, [root, data], lambda path: OSError(f'{path} unavailable')
    )

    assert partition is root


def test_macos_firmlink_matching_tolerates_a_changed_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    root = Partition('/dev/system', '/', 'apfs', 'ro')
    data = Partition('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')
    selected_usage = Usage(100, 50, 40, 55)
    usages = {
        '/': Usage(100, 10, 40, 20),
        '/System/Volumes/Data': Usage(100, 51, 39, 56),
    }

    monkeypatch.setattr(system_metrics.sys, 'platform', 'darwin')
    partition = system_metrics._identify_partition(  # pyright: ignore[reportPrivateUsage]
        '/Users/me/app', selected_usage, [root, data], lambda path: usages[path]
    )

    assert partition is data


def test_windows_unc_fallback_is_case_insensitive(
    metrics_reader: InMemoryMetricReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_partitions(*, all: bool) -> list[Partition]:
        return []

    def disk_usage(path: str) -> Usage:
        return Usage(100, 40, 50, 80)

    monkeypatch.setattr(system_metrics.psutil, 'disk_partitions', disk_partitions)
    monkeypatch.setattr(system_metrics.psutil, 'disk_usage', disk_usage)

    logfire.instrument_system_metrics(
        {'system.filesystem.limit': {'paths': [r'\\server\share\app', r'\\SERVER\SHARE\other']}},
        base=None,
    )
    points = get_collected_metrics(metrics_reader)[0]['data']['data_points']

    assert len(points) == 1
    assert points[0]['attributes'] == {
        'system.device': r'\\server\share',
        'system.filesystem.mountpoint': r'\\server\share',
    }


def test_windows_fallback_handles_an_unparseable_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    def splitdrive(path: str) -> tuple[str, str]:
        return '', path

    monkeypatch.setattr(system_metrics.ntpath, 'splitdrive', splitdrive)

    path = r'\\invalid'
    assert system_metrics._fallback_filesystem_identity(path) == (path, path)  # pyright: ignore[reportPrivateUsage]


def test_partition_for_path_tolerates_commonpath_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def commonpath(paths: tuple[str, str]) -> str:
        raise ValueError('different drives')

    monkeypatch.setattr(system_metrics.os.path, 'commonpath', commonpath)

    partition = system_metrics._partition_for_path(  # pyright: ignore[reportPrivateUsage]
        '/work/app', [Partition('/dev/data', '/work', 'ext4', 'rw')]
    )
    assert partition is None


@pytest.mark.parametrize(
    ('path', 'partitions', 'expected_device'),
    [
        (
            '/var/lib/app/data',
            [('/dev/root', '/', 'ext4', 'rw'), ('/dev/data', '/var/lib/app', 'xfs', 'rw')],
            '/dev/data',
        ),
        (
            '/System/Volumes/Data/Users/me/app',
            [('/dev/system', '/', 'apfs', 'ro'), ('/dev/data', '/System/Volumes/Data', 'apfs', 'rw')],
            '/dev/data',
        ),
        (
            r'\\server\share\apps\service',
            [(r'\\SERVER\SHARE', r'\\SERVER\SHARE', 'NTFS', 'rw')],
            r'\\SERVER\SHARE',
        ),
        (r'D:\apps\service', [('C:', 'C:\\', 'NTFS', 'rw'), ('D:', 'D:\\', 'NTFS', 'rw')], 'D:'),
    ],
)
def test_partition_for_path(path: str, partitions: list[tuple[str, str, str, str]], expected_device: str) -> None:
    partition = system_metrics._partition_for_path(  # pyright: ignore[reportPrivateUsage]
        path, (Partition(*values) for values in partitions)
    )
    assert partition is not None
    assert partition.device == expected_device
