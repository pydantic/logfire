from _typeshed import Incomplete
from logfire import Logfire as Logfire
from typing import Iterable, Literal
from typing_extensions import LiteralString

MetricName: type[Literal['system.cpu.simple_utilization', 'system.cpu.time', 'system.cpu.utilization', 'system.memory.usage', 'system.memory.utilization', 'system.swap.usage', 'system.swap.utilization', 'system.disk.io', 'system.disk.operations', 'system.disk.time', 'system.network.dropped.packets', 'system.network.packets', 'system.network.errors', 'system.network.io', 'system.network.connections', 'system.thread_count', 'process.open_file_descriptor.count', 'process.context_switches', 'process.cpu.time', 'process.cpu.utilization', 'process.cpu.core_utilization', 'process.memory.usage', 'process.memory.virtual', 'process.thread.count', 'process.runtime.gc_count', 'process.runtime.memory', 'process.runtime.cpu.time', 'process.runtime.thread_count', 'process.runtime.cpu.utilization', 'process.runtime.context_switches']]
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
