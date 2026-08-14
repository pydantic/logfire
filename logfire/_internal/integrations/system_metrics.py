from __future__ import annotations

import logging
import ntpath
import os
import sys
from collections.abc import Callable, Iterable, Sequence
from platform import python_implementation
from threading import Lock
from typing import TYPE_CHECKING, Literal, Protocol, TypedDict, cast

from opentelemetry.metrics import CallbackOptions, Observation

if TYPE_CHECKING:
    from typing_extensions import LiteralString

    from logfire import Logfire

try:
    import psutil
    from opentelemetry.instrumentation.system_metrics import (
        _DEFAULT_CONFIG,  # pyright: ignore[reportPrivateUsage]
        SystemMetricsInstrumentor,
    )
except ImportError as e:  # pragma: no cover
    raise RuntimeError(
        '`logfire.instrument_system_metrics()` requires the `opentelemetry-instrumentation-system-metrics` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[system-metrics]'"
    ) from e

# stubgen seems to need this redundant type declaration.
MetricName: type[
    Literal[
        'system.cpu.simple_utilization',
        'system.cpu.time',
        'system.cpu.utilization',
        'system.memory.usage',
        'system.memory.utilization',
        'system.swap.usage',
        'system.swap.utilization',
        'system.disk.io',
        'system.disk.operations',
        'system.disk.time',
        'system.filesystem.usage',
        'system.filesystem.limit',
        'system.filesystem.utilization',
        'system.network.dropped.packets',
        'system.network.packets',
        'system.network.errors',
        'system.network.io',
        'system.network.connections',
        'system.thread_count',
        'process.open_file_descriptor.count',
        'process.context_switches',
        'process.cpu.time',
        'process.cpu.utilization',
        'process.cpu.core_utilization',
        'process.disk.io',
        'process.memory.usage',
        'process.memory.virtual',
        'process.thread.count',
        'process.runtime.gc_count',
        'cpython.gc.collected_objects',
        'cpython.gc.collections',
        'cpython.gc.uncollectable_objects',
    ]
] = Literal[  # type: ignore  # but pyright doesn't like it
    'system.cpu.simple_utilization',
    'system.cpu.time',
    'system.cpu.utilization',
    'system.memory.usage',
    'system.memory.utilization',
    'system.swap.usage',
    'system.swap.utilization',
    'system.disk.io',
    'system.disk.operations',
    'system.disk.time',
    'system.filesystem.usage',
    'system.filesystem.limit',
    'system.filesystem.utilization',
    'system.network.dropped.packets',
    'system.network.packets',
    'system.network.errors',
    'system.network.io',
    'system.network.connections',
    'system.thread_count',
    'process.open_file_descriptor.count',
    'process.context_switches',
    'process.cpu.time',
    'process.cpu.utilization',
    'process.cpu.core_utilization',
    'process.disk.io',
    'process.memory.usage',
    'process.memory.virtual',
    'process.thread.count',
    'process.runtime.gc_count',
    'cpython.gc.collected_objects',
    'cpython.gc.collections',
    'cpython.gc.uncollectable_objects',
]


class FilesystemConfig(TypedDict, total=False):
    """Configuration for the filesystem metric family."""

    paths: Iterable[str | os.PathLike[str]] | None
    states: Iterable[Literal['used', 'free', 'reserved']]


MetricConfig = Iterable[str] | FilesystemConfig | None
Config = dict[MetricName, MetricConfig]

logger = logging.getLogger(__name__)


class DiskUsage(Protocol):
    @property
    def total(self) -> int: ...

    @property
    def used(self) -> int: ...

    @property
    def free(self) -> int: ...


class DiskPartition(Protocol):
    @property
    def device(self) -> str: ...

    @property
    def mountpoint(self) -> str: ...

    @property
    def fstype(self) -> str: ...

    @property
    def opts(self) -> str: ...


FilesystemMetricName = Literal['system.filesystem.usage', 'system.filesystem.limit', 'system.filesystem.utilization']
FilesystemState = Literal['used', 'free', 'reserved']

FILESYSTEM_METRICS: tuple[FilesystemMetricName, ...] = (
    'system.filesystem.usage',
    'system.filesystem.limit',
    'system.filesystem.utilization',
)
FILESYSTEM_STATES: tuple[FilesystemState, ...] = ('used', 'free', 'reserved')
MAX_FILESYSTEM_PATHS = 32

# All the cpu_times fields provided by psutil (used by system_metrics) across all platforms,
# except for 'guest' and 'guest_nice' which are included in 'user' and 'nice' in Linux (see psutil._cpu_tot_time).
# Docs: https://psutil.readthedocs.io/en/latest/#psutil.cpu_times
CPU_FIELDS: list[LiteralString] = 'idle user system irq softirq nice iowait steal interrupt dpc'.split()

# All the virtual_memory fields provided by psutil across all platforms,
# except for 'percent' which can be calculated as `(total - available) / total * 100`.
# Docs: https://psutil.readthedocs.io/en/latest/#psutil.virtual_memory
MEMORY_FIELDS: list[LiteralString] = 'available used free active inactive buffers cached shared wired slab'.split()

FULL_CONFIG: Config = {
    **cast(Config, _DEFAULT_CONFIG),
    'system.cpu.simple_utilization': None,
    'process.cpu.utilization': None,
    'process.cpu.core_utilization': None,
    'system.cpu.time': CPU_FIELDS,
    'system.cpu.utilization': CPU_FIELDS,
    # For usage, knowing the total amount of bytes available might be handy.
    'system.memory.usage': MEMORY_FIELDS + ['total'],
    # For utilization, the total is always just 1 (100%), so it's not included.
    'system.memory.utilization': MEMORY_FIELDS,
    # The 'free' utilization is not included because it's just 1 - 'used'.
    'system.swap.utilization': ['used'],
}

if sys.platform == 'darwin':  # pragma: no cover
    # see https://github.com/giampaolo/psutil/issues/1219
    # upstream pr: https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2008
    FULL_CONFIG.pop('system.network.connections', None)

for _deprecated in [
    'process.runtime.memory',
    'process.runtime.cpu.time',
    'process.runtime.thread_count',
    'process.runtime.cpu.utilization',
    'process.runtime.context_switches',
]:
    FULL_CONFIG.pop(_deprecated, None)  # pyright: ignore[reportArgumentType, reportCallIssue]

BASIC_CONFIG: Config = {
    'process.cpu.utilization': None,
    'system.cpu.simple_utilization': None,
    # The actually used memory ratio can be calculated as `1 - available`.
    'system.memory.utilization': ['available'],
    'system.swap.utilization': ['used'],
}

Base = Literal['basic', 'full', None]


def get_base_config(base: Base) -> Config:
    if base == 'basic':
        return BASIC_CONFIG
    elif base == 'full':
        return FULL_CONFIG
    elif base is None:
        return {}
    else:
        raise ValueError(f'Invalid base: {base}')


def instrument_system_metrics(logfire_instance: Logfire, config: Config | None = None, base: Base = 'basic'):
    config = {**get_base_config(base), **(config or {})}

    filesystem_config = {name: config.pop(name) for name in FILESYSTEM_METRICS if name in config}
    if filesystem_config:
        values = list(filesystem_config.values())
        if any(value != values[0] for value in values[1:]):
            raise ValueError('Filesystem metric keys must use the same configuration.')
        measure_filesystems(
            logfire_instance,
            values[0],
            enabled=cast(set[FilesystemMetricName], set(filesystem_config)),
        )

    if 'system.cpu.simple_utilization' in config:
        measure_simple_cpu_utilization(logfire_instance)

    if 'process.cpu.core_utilization' in config:
        measure_process_cpu_core_utilization(logfire_instance)

    if 'process.runtime.cpu.utilization' in config:  # pyright: ignore[reportUnnecessaryContains]
        # Override OTEL here, see comment in measure_process_runtime_cpu_utilization.<locals>.callback.
        # (The name is also deprecated by OTEL, but that's not really important)
        measure_process_runtime_cpu_utilization(logfire_instance)
        del config['process.runtime.cpu.utilization']  # pyright: ignore[reportArgumentType]

    if 'process.cpu.utilization' in config:
        # Override OTEL here to avoid emitting 0 in the first measurement.
        measure_process_cpu_utilization(logfire_instance)
        del config['process.cpu.utilization']

    instrumentor = SystemMetricsInstrumentor(config=config)  # pyright: ignore[reportArgumentType]
    instrumentor.instrument(meter_provider=logfire_instance.config.get_meter_provider())


def measure_filesystems(logfire_instance: Logfire, config: MetricConfig, *, enabled: set[FilesystemMetricName]) -> None:
    """Create selected OpenTelemetry filesystem metrics for a bounded list of paths."""
    configured_paths: Iterable[str | os.PathLike[str]] | None
    if config is None:
        configured_paths = None
        configured_states: Iterable[FilesystemState] = FILESYSTEM_STATES
    elif isinstance(config, dict):
        filesystem_config = cast(FilesystemConfig, config)
        configured_paths = filesystem_config.get('paths')
        configured_states = filesystem_config.get('states', FILESYSTEM_STATES)
    else:
        raise ValueError('Filesystem metric configuration must be a dictionary or None.')

    if configured_paths is None:
        configured_paths = [os.getcwd()]
    raw_paths = list(configured_paths)
    if len(raw_paths) > MAX_FILESYSTEM_PATHS:
        raise ValueError(f'At most {MAX_FILESYSTEM_PATHS} filesystem paths can be configured.')
    paths = [_absolute_path(os.fsdecode(path)) for path in raw_paths]

    states = tuple(dict.fromkeys(configured_states))
    invalid_states = set(states) - set(FILESYSTEM_STATES)
    if invalid_states:
        raise ValueError(f'Invalid filesystem states: {sorted(invalid_states)}')

    warned_paths: set[str] = set()
    partition_warning_emitted = False
    warning_lock = Lock()

    def collect_filesystems() -> tuple[tuple[DiskUsage, dict[str, str]], ...]:
        nonlocal partition_warning_emitted

        try:
            # Use named attributes below. Some supported psutil 5.9 platforms append maxfile and maxpath.
            partitions = cast(Sequence[DiskPartition], psutil.disk_partitions(all=True))
        except (OSError, NotImplementedError, ValueError, psutil.Error) as exc:
            with warning_lock:
                should_warn = not partition_warning_emitted
                partition_warning_emitted = True
            if should_warn:
                logger.warning('Unable to inspect filesystem mount points: %s', exc)
            partitions = ()

        usage_cache: dict[str, DiskUsage | BaseException] = {}

        def usage_for(path: str) -> DiskUsage | BaseException:
            key = _path_key(path)
            if key not in usage_cache:
                try:
                    usage_cache[key] = cast(DiskUsage, psutil.disk_usage(path))
                except (OSError, NotImplementedError, ValueError, psutil.Error) as exc:
                    usage_cache[key] = exc
            return usage_cache[key]

        observations: list[tuple[DiskUsage, dict[str, str]]] = []
        seen: set[tuple[str, str]] = set()
        for selected_path in paths:
            partition: DiskPartition | None = None
            usage: DiskUsage | BaseException

            data_partition = _macos_data_partition(selected_path, partitions)
            if data_partition is not None:
                usage = usage_for(data_partition.mountpoint)
                if not isinstance(usage, BaseException):
                    partition = data_partition
                else:
                    usage = usage_for(selected_path)
            else:
                usage = usage_for(selected_path)

            if isinstance(usage, BaseException):
                warning_key = _path_key(selected_path)
                with warning_lock:
                    should_warn = warning_key not in warned_paths
                    warned_paths.add(warning_key)
                if should_warn:
                    logger.warning('Unable to collect filesystem metrics for %r: %s', selected_path, usage)
                continue

            if partition is None:
                partition = _identify_partition(selected_path, usage, partitions, usage_for)

            attributes = _filesystem_attributes(selected_path, partition)
            identity = _filesystem_identity(attributes)
            if identity in seen:
                continue
            seen.add(identity)
            observations.append((usage, attributes))
        return tuple(observations)

    def usage_callback(_options: CallbackOptions) -> Iterable[Observation]:
        for usage, attributes in collect_filesystems():
            values = {
                'used': usage.used,
                'free': usage.free,
                'reserved': max(usage.total - usage.used - usage.free, 0),
            }
            for state in states:
                yield Observation(values[state], {**attributes, 'system.filesystem.state': state})

    def limit_callback(_options: CallbackOptions) -> Iterable[Observation]:
        for usage, attributes in collect_filesystems():
            yield Observation(usage.total, attributes)

    def utilization_callback(_options: CallbackOptions) -> Iterable[Observation]:
        for usage, attributes in collect_filesystems():
            available = usage.used + usage.free
            yield Observation(
                usage.used / available if available else 0,
                {**attributes, 'system.filesystem.state': 'used'},
            )

    if 'system.filesystem.usage' in enabled:
        logfire_instance.metric_up_down_counter_callback(
            'system.filesystem.usage',
            [usage_callback],
            unit='By',
            description="Reports a filesystem's space usage across different states.",
        )
    if 'system.filesystem.limit' in enabled:
        logfire_instance.metric_up_down_counter_callback(
            'system.filesystem.limit',
            [limit_callback],
            unit='By',
            description='The total storage capacity of the filesystem.',
        )
    if 'system.filesystem.utilization' in enabled:
        logfire_instance.metric_gauge_callback(
            'system.filesystem.utilization',
            [utilization_callback],
            unit='1',
            description='Fraction of filesystem bytes used.',
        )


def _identify_partition(
    path: str,
    usage: DiskUsage,
    partitions: Sequence[DiskPartition],
    usage_for: Callable[[str], DiskUsage | BaseException],
) -> DiskPartition | None:
    """Identify the measured partition, preferring lexical containment except for macOS Data firmlinks."""
    lexical = _partition_for_path(path, partitions)
    if sys.platform != 'darwin' or lexical is None or _path_key(lexical.mountpoint) != '/':
        return lexical

    candidates: list[tuple[int, DiskPartition]] = []
    for partition in partitions:
        partition_usage = usage_for(partition.mountpoint)
        if not isinstance(partition_usage, BaseException) and partition_usage.total == usage.total:
            distance = abs(partition_usage.used - usage.used) + abs(partition_usage.free - usage.free)
            candidates.append((distance, partition))

    if not candidates:
        return lexical
    best_distance = min(distance for distance, _partition in candidates)
    matches = [partition for distance, partition in candidates if distance == best_distance]
    if lexical in matches:
        return lexical
    if len(matches) == 1 and _path_key(matches[0].mountpoint) == '/System/Volumes/Data':
        return matches[0]
    return lexical


def _macos_data_partition(path: str, partitions: Sequence[DiskPartition]) -> DiskPartition | None:
    """Resolve the sealed macOS root to the writable Data volume."""
    if sys.platform != 'darwin' or _path_key(path) != '/':
        return None
    return next(
        (partition for partition in partitions if _path_key(partition.mountpoint) == '/System/Volumes/Data'), None
    )


def _filesystem_attributes(path: str, partition: DiskPartition | None) -> dict[str, str]:
    if partition is None:
        device, mountpoint = _fallback_filesystem_identity(path)
        return {'system.device': device, 'system.filesystem.mountpoint': mountpoint}

    attributes = {
        'system.device': partition.device,
        'system.filesystem.mountpoint': partition.mountpoint,
        'system.filesystem.mode': 'ro' if 'ro' in {option.lower() for option in partition.opts.split(',')} else 'rw',
    }
    if partition.fstype:
        attributes['system.filesystem.type'] = partition.fstype.lower()
    return attributes


def _fallback_filesystem_identity(path: str) -> tuple[str, str]:
    """Return a stable best-effort identity when psutil does not enumerate the partition."""
    if _is_windows_path(path):
        drive, _tail = ntpath.splitdrive(path)
        if drive:
            mountpoint = drive if drive.startswith(('\\\\', '//')) else drive + '\\'
            return drive, mountpoint
    return path, path


def _filesystem_identity(attributes: dict[str, str]) -> tuple[str, str]:
    return (
        _path_key(attributes['system.device']) if attributes.get('system.device') else '',
        _path_key(attributes['system.filesystem.mountpoint']),
    )


def _partition_for_path(path: str, partitions: Iterable[DiskPartition]) -> DiskPartition | None:
    """Return the most specific psutil partition containing path, including UNC mount points."""
    candidates: list[tuple[int, DiskPartition]] = []
    for partition in partitions:
        raw_mountpoint = partition.mountpoint
        path_module = ntpath if _is_windows_path(path) or _is_windows_path(raw_mountpoint) else os.path
        normalized_path = path_module.normcase(path_module.abspath(path))
        mountpoint = path_module.normcase(path_module.abspath(raw_mountpoint))
        if path_module is ntpath:
            boundary = mountpoint.rstrip('\\/') + '\\'
            contains = normalized_path == mountpoint or normalized_path.startswith(boundary)
        else:
            try:
                contains = path_module.commonpath((normalized_path, mountpoint)) == mountpoint
            except ValueError:
                contains = False
        if contains:
            candidates.append((len(mountpoint), partition))
    return max(candidates, default=(0, None), key=lambda item: item[0])[1]


def _is_windows_path(path: str) -> bool:
    return path.startswith(('\\\\', '//')) or bool(ntpath.splitdrive(path)[0])


def _absolute_path(path: str) -> str:
    path_module = ntpath if _is_windows_path(path) else os.path
    return path_module.abspath(path)


def _path_key(path: str) -> str:
    path_module = ntpath if _is_windows_path(path) else os.path
    return path_module.normcase(path_module.abspath(path))


def measure_simple_cpu_utilization(logfire_instance: Logfire):
    def callback(_options: CallbackOptions) -> Iterable[Observation]:
        # psutil returns a value from 0-100, OTEL values here are generally 0-1, so we divide by 100.
        yield Observation(psutil.cpu_percent() / 100)

    logfire_instance.metric_gauge_callback(
        'system.cpu.simple_utilization',
        [callback],
        description='Average CPU usage across all cores, as a fraction between 0 and 1.',
        unit='1',
    )


def measure_process_runtime_cpu_utilization(logfire_instance: Logfire):
    process = psutil.Process()
    # This first call always returns 0, do it here so that the first real measurement from an exporter
    # will return a nonzero value.
    process.cpu_percent()

    def callback(_options: CallbackOptions) -> Iterable[Observation]:
        # psutil returns a value from 0-100, OTEL values here are generally 0-1, so we divide by 100.
        # OTEL got this wrong: https://github.com/open-telemetry/opentelemetry-python-contrib/issues/2810
        # A fix has been merged there, but we need to know in the dashboard how to interpret the values.
        # So the dashboard will assume a 0-100 range if the scope is 'opentelemetry.instrumentation.system_metrics',
        # and a 0-1 range otherwise. In particular the scope will be 'logfire' if it comes from here.
        yield Observation(process.cpu_percent() / 100)

    logfire_instance.metric_gauge_callback(
        f'process.runtime.{python_implementation().lower()}.cpu.utilization',
        [callback],
        description='Runtime CPU utilization',
        unit='1',
    )


def measure_process_cpu_utilization(logfire_instance: Logfire):
    process = psutil.Process()
    # This first call always returns 0, do it here so that the first real measurement from an exporter
    # will return a nonzero value.
    # Otherwise this function mimics what OTel's SystemMetricsInstrumentor does.
    process.cpu_percent()

    num_cpus = psutil.cpu_count() or 1

    def callback(_options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(process.cpu_percent() / 100 / num_cpus)

    logfire_instance.metric_gauge_callback(
        'process.cpu.utilization',
        [callback],
        description='Runtime CPU utilization',
        unit='1',
    )


def measure_process_cpu_core_utilization(logfire_instance: Logfire):
    """Same as process.cpu.utilization, but not divided by the number of available cores."""
    process = psutil.Process()
    # This first call always returns 0, do it here so that the first real measurement from an exporter
    # will return a nonzero value.
    process.cpu_percent()

    def callback(_options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(process.cpu_percent() / 100)

    logfire_instance.metric_gauge_callback(
        'process.cpu.core_utilization',
        [callback],
        description='Runtime CPU utilization, not divided by the number of available cores.',
        unit='core',
    )
