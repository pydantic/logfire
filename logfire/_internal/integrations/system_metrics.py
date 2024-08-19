from __future__ import annotations

import contextlib
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

MetricName = Literal[
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
    # The values of `process.cpu_percent()` are relative to the last time it was called.
    # In particular, the first call will always return 0.
    # So we need to call it once before we start measuring the actual utilization,
    # and we need to use the same process object for all calls.
    # TODO a similar problem exists with `psutil.cpu_percent()`
    #   and thus for the OTEL instrumentation as well, and there it's harder to fix because
    #   the previous values are separated by thread.
    #   See https://github.com/open-telemetry/opentelemetry-python-contrib/issues/2797
    process = psutil.Process()
    process.cpu_percent()

    def callback(_options: CallbackOptions) -> Iterable[Observation]:
        percents: list[float] = [
            # Average CPU usage across all cores.
            # A high value is notable regardless of which core(s) this process is using.
            psutil.cpu_percent(),
            # CPU usage of this particular process.
            # Can be greater than 100% if the process is using multiple cores.
            # Will be less than 100% if multiple processes are using the same core,
            # even if this process is using it at full capacity.
            process.cpu_percent(),
        ]
        # CPU usage of the core this process is using, if available.
        # This will be higher than `process.cpu_percent()` if multiple processes are using the same core.
        # This requires `process.cpu_num()` which is only available on Linux,
        # so we need to suppress the exception on other platforms.
        with contextlib.suppress(Exception):
            # Whether `Process.cpu_num` exists depends on the platform, and this affects pyright.
            # So we can't use `# type: ignore` here, because on Linux it's not needed.
            if not TYPE_CHECKING:  # pragma: no branch
                cpu_num = process.cpu_num()
                # `cpu_num` can be -1 on some platforms according to psutil.
                if cpu_num >= 0:  # pragma: no branch
                    percents.append(psutil.cpu_percent(percpu=True)[cpu_num])
        yield Observation(max(percents) / 100)

    logfire_instance.metric_gauge_callback(
        'system.cpu.simple_utilization',
        [callback],
        description='Maximum of: '
        '(1) average CPU usage across all cores, '
        '(2) CPU usage of this process, '
        '(3) CPU usage of the core this process is using, if available.',
        unit='1',
    )
