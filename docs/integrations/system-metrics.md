---
integration: logfire
---

The [`logfire.instrument_system_metrics()`][logfire.Logfire.instrument_system_metrics] method can be used to collect system metrics with **Logfire**, such as CPU and memory usage.

## Installation

Install `logfire` with the `system-metrics` extra:

{{ install_logfire(extras=['system-metrics']) }}

## Usage

```py
import logfire

logfire.configure()

logfire.instrument_system_metrics()
```

Then in your project, click on 'Dashboards' in the top bar, click 'New Dashboard', and select 'Basic System Metrics (Logfire)' from the dropdown.

## Configuration

By default, `instrument_system_metrics` collects only the metrics it needs to display the 'Basic System Metrics (Logfire)' dashboard. You can choose exactly which metrics to collect and how much data to collect about each metric. The default is equivalent to this:

```py
logfire.instrument_system_metrics({
    'process.runtime.cpu.utilization': None,  # (1)!
    'system.cpu.simple_utilization': None,  # (2)!
    'system.memory.utilization': ['available'],  # (3)!
    'system.swap.utilization': ['used'],  # (4)!
})
```

1. `process.runtime.cpu.utilization` will lead to exporting a metric that is actually named `process.runtime.cpython.cpu.utilization` or a similar name depending on the Python implementation used. The `None` value means that there are no fields to configure for this metric. The value of this metric is [`psutil.Process().cpu_percent()`](https://psutil.readthedocs.io/en/latest/#psutil.Process.cpu_percent)`/ 100`, i.e. the fraction of CPU time used by this process, where 1 means using 100% of a single CPU core. The value can be greater than 1 if the process uses multiple cores. In the next major release, the default will instead emit `'process.cpu.core_utilization'`, which is the same metric but with a simpler name.
2. The `None` value means that there are no fields to configure for this metric. The value of this metric is [`psutil.cpu_percent()`](https://psutil.readthedocs.io/en/latest/#psutil.cpu_percent)`/ 100`, i.e. the fraction of CPU time used by the whole system, where 1 means using 100% of all CPU cores.
3. The value here is a list of 'modes' of memory. The full list can be seen in the [`psutil` documentation](https://psutil.readthedocs.io/en/latest/#psutil.virtual_memory). `available` is "the memory that can be given instantly to processes without the system going into swap. This is calculated by summing different memory metrics that vary depending on the platform. It is supposed to be used to monitor actual memory usage in a cross platform fashion." The value of the metric is a number between 0 and 1, and subtracting the value from 1 gives the fraction of memory used.
4. This is the fraction of available swap used. The value is a number between 0 and 1.

To collect lots of detailed data about all available metrics, use `logfire.instrument_system_metrics(base='full')`.

!!! warning
    The amount of data collected by `base='full'` can be expensive, especially if you have many servers,
    and this is easy to forget about. If you enable this, be sure to monitor your usage and costs.

    The most expensive metrics are `system.cpu.utilization/time` which collect data for each core and each mode,
    and `system.disk.*` which collect data for each disk device. The exact number depends on the machine hardware,
    but this can result in hundreds of data points per minute from each instrumented host.

`logfire.instrument_system_metrics(base='full')` is equivalent to:

```py
logfire.instrument_system_metrics({
    'system.cpu.simple_utilization': None,
    'system.cpu.time': ['idle', 'user', 'system', 'irq', 'softirq', 'nice', 'iowait', 'steal', 'interrupt', 'dpc'],
    'system.cpu.utilization': ['idle', 'user', 'system', 'irq', 'softirq', 'nice', 'iowait', 'steal', 'interrupt', 'dpc'],
    'system.memory.usage': ['available', 'used', 'free', 'active', 'inactive', 'buffers', 'cached', 'shared', 'wired', 'slab', 'total'],
    'system.memory.utilization': ['available', 'used', 'free', 'active', 'inactive', 'buffers', 'cached', 'shared', 'wired', 'slab'],
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
    'process.context_switches': ['involuntary', 'voluntary'],
    'process.runtime.gc_count': None,
    'process.open_file_descriptor.count': None,
    'process.cpu.time': ['user', 'system'],
    'process.cpu.utilization': None,
    'process.cpu.core_utilization': None,
    'process.memory.usage': None,
    'process.memory.virtual': None,
    'process.thread.count': None,
    # These are deprecated and equivalent to some of the above.
    # base='full' will stop including them in the next major release.
    'process.runtime.memory': ['rss', 'vms'],
    'process.runtime.cpu.time': ['user', 'system'],
    'process.runtime.thread_count': None,
    'process.runtime.cpu.utilization': None,
    'process.runtime.context_switches': ['involuntary', 'voluntary'],
})
```

Each key here is a metric name. The values have different meanings for different metrics. For example, for `system.cpu.utilization`, the value is a list of CPU modes. So there will be a separate row for each CPU core saying what percentage of time it spent idle, another row for the time spent waiting for IO, etc. There are no fields to configure for `system.thread_count`, so the value is `None`.

For convenient customizability, the first dict argument is merged with the base. For example, if you want to collect disk read operations (but not writes) you can write:

- `logfire.instrument_system_metrics({'system.disk.operations': ['read']})` to collect that data in addition to the basic defaults.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base='full')` to collect detailed data about all metrics, excluding disk write operations.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base=None)` to collect only disk read operations and nothing else.
