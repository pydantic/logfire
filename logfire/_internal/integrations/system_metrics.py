import sys
from typing import Any, Dict, Iterable, List, Literal, Optional, Union, cast

from opentelemetry.metrics import MeterProvider

try:
    from opentelemetry.instrumentation.system_metrics import (
        _DEFAULT_CONFIG,  # type: ignore
        SystemMetricsInstrumentor,
    )
except ModuleNotFoundError:  # pragma: no cover
    raise RuntimeError(
        '`logfire.instrument_system_metrics()` requires the `opentelemetry-instrumentation-system-metrics` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[system-metrics]'"
    )

MetricName = Literal[
    'system.cpu.time',
    'system.cpu.utilization',
    'system.memory.usage',
    'system.memory.utilization',
    'system.swap.usage',
    'system.swap.utilization',
    'system.disk.io',
    'system.disk.operations',
    'system.disk.time',
    'system.network.dropped.packets',
    'system.network.packets',
    'system.network.errors',
    'system.network.io',
    'system.network.connections',
    'system.thread_count',
    'process.runtime.memory',
    'process.runtime.cpu.time',
    'process.runtime.gc_count',
    'process.runtime.thread_count',
    'process.runtime.cpu.utilization',
    'process.runtime.context_switches',
    'process.open_file_descriptor.count',
]

ConfigString = Union[Literal['basic'], MetricName]
ConfigDict = Dict[MetricName, Optional[Iterable[str]]]
Config = Union[Literal['all'], ConfigString, Iterable[ConfigString], Dict[ConfigString, Optional[Iterable[str]]]]


# All the cpu_times fields provided by psutil (used by system_metrics) across all platforms,
# except for 'guest' and 'guest_nice' which are included in 'user' and 'nice' in Linux (see psutil._cpu_tot_time).
# Docs: https://psutil.readthedocs.io/en/latest/#psutil.cpu_times
CPU_FIELDS = 'idle user system irq softirq nice iowait steal interrupt dpc'.split()

# All the virtual_memory fields provided by psutil across all platforms,
# except for 'percent' which can be calculated as `(total - available) / total * 100`.
# Docs: https://psutil.readthedocs.io/en/latest/#psutil.virtual_memory
MEMORY_FIELDS = 'total available used free active inactive buffers cached shared wired slab'.split()

# Based on opentelemetry/instrumentation/system_metrics/__init__.py
DEFAULT_CONFIG: ConfigDict = {
    **cast(ConfigDict, _DEFAULT_CONFIG),
    'system.cpu.time': CPU_FIELDS,
    'system.cpu.utilization': CPU_FIELDS,
    'system.memory.usage': MEMORY_FIELDS,
    'system.memory.utilization': MEMORY_FIELDS,
}

if sys.platform == 'darwin':  # pragma: no cover
    # see https://github.com/giampaolo/psutil/issues/1219
    # upstream pr: https://github.com/open-telemetry/opentelemetry-python-contrib/pull/2008
    DEFAULT_CONFIG.pop('system.network.connections', None)


BASIC_METRICS: List[MetricName] = [
    'system.thread_count',  # used by process count
    'system.cpu.utilization',
    'system.memory.utilization',
    'system.swap.usage',
]


def parse_config(config: Config) -> ConfigDict:
    if isinstance(config, str):
        if config == 'all':
            return DEFAULT_CONFIG
        config = [config]

    config_dict: Dict[ConfigString, Optional[Iterable[str]]]
    if isinstance(config, dict):
        config_dict = config
    else:
        config_dict = {}
        key: ConfigString
        for key in config:
            if key == 'basic':
                config_dict[key] = None
            else:
                config_dict[key] = DEFAULT_CONFIG[key]

    result: ConfigDict = {}
    for key, value in config_dict.items():
        if key == 'basic':
            for metric in BASIC_METRICS:
                result[metric] = DEFAULT_CONFIG[metric]
        elif value is None:
            result[key] = DEFAULT_CONFIG[key]
        else:
            result[key] = value
    return result


def instrument_system_metrics(meter_provider: MeterProvider, config: Any = 'basic') -> None:
    SystemMetricsInstrumentor().uninstrument()  # type: ignore
    SystemMetricsInstrumentor(config=parse_config(config)).instrument(meter_provider=meter_provider)  # type: ignore
