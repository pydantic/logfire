from _typeshed import Incomplete
from opentelemetry.metrics import MeterProvider
from typing import Any, Iterable

MetricName: Incomplete
ConfigString: Incomplete
ConfigDict = dict[MetricName, Iterable[str] | None]
Config: Incomplete
CPU_FIELDS: Incomplete
MEMORY_FIELDS: Incomplete
DEFAULT_CONFIG: ConfigDict
BASIC_METRICS: list[MetricName]

def parse_config(config: Config) -> ConfigDict: ...
def instrument_system_metrics(meter_provider: MeterProvider, config: Any = 'basic') -> None: ...
