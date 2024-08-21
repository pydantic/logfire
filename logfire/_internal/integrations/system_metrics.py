from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Dict, Iterable, Literal, Optional, cast

from opentelemetry.metrics import CallbackOptions, Observation

if TYPE_CHECKING:
    from typing_extensions import LiteralString

    from logfire import Logfire

try:
    import psutil
    from opentelemetry.instrumentation.system_metrics import (
        _DEFAULT_CONFIG,  # type: ignore
        SystemMetricsInstrumentor,
    )
except ModuleNotFoundError as e:  # pragma: no cover
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

Config = Dict[MetricName, Optional[Iterable[str]]]

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

BASIC_CONFIG: Config = {
    'process.runtime.cpu.utilization': None,
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
    SystemMetricsInstrumentor(config=config).instrument()  # type: ignore

    if 'system.cpu.simple_utilization' in config:
        measure_simple_cpu_utilization(logfire_instance)


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
