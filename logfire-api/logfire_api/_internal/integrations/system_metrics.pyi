from _typeshed import Incomplete
from logfire import Logfire as Logfire
from typing import Iterable

MetricName: Incomplete
Config = dict[MetricName, Iterable[str] | None]
CPU_FIELDS: list[str]
MEMORY_FIELDS: list[str]
FULL_CONFIG: Config
BASIC_CONFIG: Config
Base: Incomplete

def get_base_config(base: Base) -> Config: ...
def instrument_system_metrics(logfire_instance: Logfire, config: Config | None = None, base: Base = 'basic'): ...
def measure_simple_cpu_utilization(logfire_instance: Logfire): ...
