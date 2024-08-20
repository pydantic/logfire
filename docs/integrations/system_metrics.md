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
    'system.cpu.simple_utilization': None,  # (1)!
    'system.memory.utilization': ['available'],
    'system.swap.utilization': ['used'],
})
```

1. `None` simply means that there are no fields to configure for this metric.

To collect lots of detailed data about all available metrics, use `logfire.instrument_system_metrics(base='full')`.

!!! warning
    The amount of data collected by `base='full'` can be expensive, especially if you have many servers,
    and this is easy to forget about. Be sure to monitor your usage and costs.

    The most expensive metrics are `system.cpu.utilization/time` which collect data for each core and each mode,
    and `system.disk.*` which collect data for each disk device. This can result in hundreds of data points per minute.
    The exact number depends on your machine.

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
    'process.runtime.memory': ['rss', 'vms'],
    'process.runtime.cpu.time': ['user', 'system'],
    'process.runtime.gc_count': None,
    'process.runtime.thread_count': None,
    'process.runtime.cpu.utilization': None,
    'process.runtime.context_switches': ['involuntary', 'voluntary'],
    'process.open_file_descriptor.count': None,
})
```

Each key here is a metric name. The values have different meanings for different metrics. For example, for `system.cpu.utilization`, the value is a list of CPU modes. So there will be a separate row for each CPU core saying what percentage of time it spent idle, another row for the time spent waiting for IO, etc. There are no fields to configure for `system.thread_count`, so the value is `None`.

The first dict argument is merged with the base. For example, if you want to collect disk read operations (but not writes) you can write:

- `logfire.instrument_system_metrics({'system.disk.operations': ['read']})` to collect that data in addition to the basic defaults.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base='full')` to collect detailed data about all metrics, excluding disk write operations.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base=None)` to collect only disk read operations and nothing else.
