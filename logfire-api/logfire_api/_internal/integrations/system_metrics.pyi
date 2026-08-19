import os
from _typeshed import Incomplete
from collections.abc import Iterable
from logfire import Logfire as Logfire
from threading import local
from typing import Literal, Protocol, TypedDict
from typing_extensions import LiteralString

MetricName: type[Literal['system.cpu.simple_utilization', 'system.cpu.time', 'system.cpu.utilization', 'system.memory.usage', 'system.memory.utilization', 'system.swap.usage', 'system.swap.utilization', 'system.disk.io', 'system.disk.operations', 'system.disk.time', 'system.filesystem.usage', 'system.filesystem.limit', 'system.filesystem.utilization', 'system.network.dropped.packets', 'system.network.packets', 'system.network.errors', 'system.network.io', 'system.network.connections', 'system.thread_count', 'process.open_file_descriptor.count', 'process.context_switches', 'process.cpu.time', 'process.cpu.utilization', 'process.cpu.core_utilization', 'process.disk.io', 'process.memory.usage', 'process.memory.virtual', 'process.thread.count', 'process.runtime.gc_count', 'cpython.gc.collected_objects', 'cpython.gc.collections', 'cpython.gc.uncollectable_objects']]

class FilesystemConfig(TypedDict, total=False):
    """Configuration for the filesystem metric family."""
    paths: Iterable[str | os.PathLike[str]] | None
    states: Iterable[Literal['used', 'free', 'reserved']]
MetricConfig = Iterable[str] | FilesystemConfig | None
Config = dict[MetricName, MetricConfig]
logger: Incomplete

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

FilesystemMetricName: Incomplete
FilesystemState: Incomplete

class _FilesystemCallbackState(local):
    cached_observations: tuple[tuple[DiskUsage, dict[str, str]], ...]
    pending_metrics: set[FilesystemMetricName]
    def __init__(self) -> None: ...

FILESYSTEM_METRICS: tuple[FilesystemMetricName, ...]
FILESYSTEM_STATES: tuple[FilesystemState, ...]
MAX_FILESYSTEM_PATHS: int
CPU_FIELDS: list[LiteralString]
MEMORY_FIELDS: list[LiteralString]
FULL_CONFIG: Config
BASIC_CONFIG: Config
Base: Incomplete

def get_base_config(base: Base) -> Config: ...
def instrument_system_metrics(logfire_instance: Logfire, config: Config | None = None, base: Base = 'basic'): ...
def measure_filesystems(logfire_instance: Logfire, config: MetricConfig, *, enabled: set[FilesystemMetricName]) -> None:
    """Create selected OpenTelemetry filesystem metrics for a bounded list of paths."""
def measure_simple_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_runtime_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_cpu_core_utilization(logfire_instance: Logfire):
    """Same as process.cpu.utilization, but not divided by the number of available cores."""
