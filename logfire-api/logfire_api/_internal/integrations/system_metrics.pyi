from _typeshed import Incomplete
from collections.abc import Iterable
from logfire import Logfire as Logfire
from typing import Literal
from typing_extensions import LiteralString

MetricName: type[Literal['system.cpu.simple_utilization', 'system.cpu.time', 'system.cpu.utilization', 'system.cpu.load_average.1m', 'system.memory.usage', 'system.memory.utilization', 'system.swap.usage', 'system.swap.utilization', 'system.disk.io', 'system.disk.operations', 'system.disk.time', 'system.network.dropped.packets', 'system.network.packets', 'system.network.errors', 'system.network.io', 'system.network.connections', 'system.process.count', 'system.thread_count', 'process.open_file_descriptor.count', 'process.context_switches', 'process.cpu.time', 'process.cpu.utilization', 'process.cpu.core_utilization', 'process.disk.io', 'process.memory.usage', 'process.memory.virtual', 'process.thread.count', 'process.runtime.gc_count', 'cpython.gc.collected_objects', 'cpython.gc.collections', 'cpython.gc.uncollectable_objects']]
Config = dict[MetricName, Iterable[str] | None]
CPU_FIELDS: list[LiteralString]
MEMORY_FIELDS: list[LiteralString]
FULL_CONFIG: Config
BASIC_CONFIG: Config
Base: Incomplete

def get_base_config(base: Base) -> Config: ...
def instrument_system_metrics(logfire_instance: Logfire, config: Config | None = None, base: Base = 'basic'): ...
def measure_simple_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_runtime_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_cpu_utilization(logfire_instance: Logfire): ...
def measure_process_cpu_core_utilization(logfire_instance: Logfire):
    """Same as process.cpu.utilization, but not divided by the number of available cores."""
def measure_system_cpu_load_average_1m(logfire_instance: Logfire):
    """1-minute system load average.

    OTel semconv defines no load average metric. The system metrics spec only
    floats `system.linux.cpu.load_1m` as a hypothetical illustration of OS-prefixed
    naming, so there's nothing to conform to. The name, gauge instrument, and
    `{thread}` unit here match the OTel Collector's `hostmetrics` load scraper,
    which is where most host load averages reaching Logfire come from. Matching it
    means SDK-reported and Collector-reported hosts land on one series instead of two.

    Upstream `SystemMetricsInstrumentor` doesn't emit this. On Windows,
    `psutil.getloadavg()` is an emulated polling shim — the first call returns 0
    and subsequent values update every ~5s.
    """
def measure_system_process_count(logfire_instance: Logfire):
    """Total number of processes on the system.

    Name, instrument, and unit follow OTel semconv's `system.process.count`
    (an UpDownCounter in `{process}`). Its `process.state` attribute is omitted:
    `psutil.pids()` is a single cheap syscall, while splitting by state needs a
    `process_iter` over every process and multiplies the series count. This metric
    is in the basic base, so that cost would land on every default install.

    Note that the OTel Collector's `hostmetrics` receiver still emits the older
    `system.processes.count` for the same measurement.

    Upstream `SystemMetricsInstrumentor` doesn't emit this.
    """
