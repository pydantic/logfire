---
title: "Monitor system metrics with Logfire"
description: "See how the machine running your app is doing (CPU, memory, disk, and network) as metrics in Logfire, plotted on a ready-made dashboard."
integration: logfire
---
# System metrics

See how the machine running your app is doing (CPU, memory, disk, network, and process activity) as
**metrics** (a metric is a number tracked over time, like CPU usage or free memory) in Logfire, plotted
on charts and a ready-made dashboard so you can watch performance in real time.

## What you'll capture

- CPU usage, for the process and for the whole machine
- Memory and swap usage
- Disk input/output and network traffic (with the detailed configuration below)
- Process activity, such as thread and file-descriptor counts

{{ before_you_start() }}

## Installation

Install `logfire` with the `system-metrics` extra:

{{ install_logfire(extras=['system-metrics']) }}

## Usage

Call `logfire.configure()` to connect to your project, then
[`logfire.instrument_system_metrics()`][logfire.Logfire.instrument_system_metrics] to start collecting
metrics from the machine:

```py
import logfire

logfire.configure()

logfire.instrument_system_metrics()
```

Your metrics then show up in several places in the Logfire UI:

- **[Hosts](../guides/web-ui/hosts.md)**: the machine running your code appears automatically, with CPU, memory,
  load, disk, network and process-count charts per host.
- **[Metrics explorer](../guides/web-ui/metrics-explorer.md)**: browse the `system.*` metrics by namespace and
  break them down by dimension, no SQL required.
- **[Dashboards](../guides/web-ui/dashboards.md)**: enable the built-in **Basic System Metrics (Logfire)**
  standard dashboard. Standard dashboards are read-only; to adjust it,
  [use it as a template](../guides/web-ui/dashboards.md#using-a-standard-dashboard-as-a-template) for a custom
  dashboard.

You can also query the metrics directly in the [Explore](../guides/web-ui/explore.md) view via the `metrics`
table (see the [SQL reference](../reference/sql.md)).

## Verify it worked

Run your program and leave it running for a few seconds, then open the
[Metrics explorer](../guides/web-ui/metrics-explorer.md) or the [Hosts](../guides/web-ui/hosts.md)
view. Within a few seconds you'll see your machine appear with CPU and memory charts.

## Troubleshooting

Not seeing your metrics in Logfire? Check that `logfire.configure()` ran before
`instrument_system_metrics()`, that your write token is set, and that you left the program running long
enough for at least one collection interval to pass.

## Advanced

### Customizing resource attributes

The Hosts view identifies a machine by its `host.name`, which Logfire takes from `socket.gethostname()`. If that
isn't meaningful, for example a random container ID, set a clearer value (or add other resource attributes such
as `process.*` or cloud metadata). See the [SQL reference](../reference/sql.md#resource-attributes) for how to set
and query resource attributes.

### Choosing which metrics to collect

By default, `instrument_system_metrics` collects only the metrics it needs to display the 'Basic System Metrics (Logfire)' dashboard. You can choose exactly which metrics to collect and how much data to collect about each metric. The default is equivalent to this:

```py skip="true" skip-reason="incomplete"
logfire.instrument_system_metrics({
    'process.cpu.utilization': None,  # (1)!
    'system.cpu.simple_utilization': None,  # (2)!
    'system.memory.utilization': ['available'],  # (3)!
    'system.swap.utilization': ['used'],  # (4)!
})
```

1. The `None` value means that there are no fields to configure for this metric. The value of this metric is [`psutil.Process().cpu_percent()`](https://psutil.readthedocs.io/en/latest/#psutil.Process.cpu_percent)`/100`, i.e. the fraction of CPU time used by this process, where 1 means using 100% of a single CPU core. The value can be greater than 1 if the process uses multiple cores.
2. The `None` value means that there are no fields to configure for this metric. The value of this metric is [`psutil.cpu_percent()`](https://psutil.readthedocs.io/en/latest/#psutil.cpu_percent)`/100`, i.e. the fraction of CPU time used by the whole system, where 1 means using 100% of all CPU cores.
3. The value here is a list of 'modes' of memory. The full list can be seen in the [`psutil` documentation](https://psutil.readthedocs.io/en/latest/#psutil.virtual_memory). `available` is "the memory that can be given instantly to processes without the system going into swap. This is calculated by summing different memory metrics that vary depending on the platform. It is supposed to be used to monitor actual memory usage in a cross platform fashion." The value of the metric is a number between 0 and 1, and subtracting the value from 1 gives the fraction of memory used.
4. This is the fraction of available swap used. The value is a number between 0 and 1.

To collect lots of detailed data about all available metrics, use `logfire.instrument_system_metrics(base='full')`.

!!! warning "`base='full'` sends much more data, and can cost more"
    The amount of data collected by `base='full'` can be expensive, especially if you have many servers,
    and this is easy to forget about. If you enable this, be sure to monitor your usage and costs.

    The most expensive metrics are `system.cpu.utilization/time` which collect data for each core and each mode,
    and `system.disk.*` which collect data for each disk device. The exact number depends on the machine hardware,
    but this can result in hundreds of data points per minute from each instrumented host.

`logfire.instrument_system_metrics(base='full')` is equivalent to:

```py skip="true" skip-reason="incomplete"
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
    'process.disk.io': ['read', 'write'],
    'process.memory.usage': None,
    'process.memory.virtual': None,
    'process.thread.count': None,
    'cpython.gc.collected_objects': None,
    'cpython.gc.collections': None,
    'cpython.gc.uncollectable_objects': None,
})
```

Each key here is a metric name. The values have different meanings for different metrics. For example, for `system.cpu.utilization`, the value is a list of CPU modes. So there will be a separate row for each CPU core saying what percentage of time it spent idle, another row for the time spent waiting for IO, etc. There are no fields to configure for `system.thread_count`, so the value is `None`.

For convenient customizability, the first dict argument is merged with the base. For example, if you want to collect disk read operations (but not writes) you can write:

- `logfire.instrument_system_metrics({'system.disk.operations': ['read']})` to collect that data in addition to the basic defaults.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base='full')` to collect detailed data about all metrics, excluding disk write operations.
- `logfire.instrument_system_metrics({'system.disk.operations': ['read']}, base=None)` to collect only disk read operations and nothing else.

## Reference

- [`logfire.instrument_system_metrics()`][logfire.Logfire.instrument_system_metrics]: the Logfire API reference.
- [SQL reference](../reference/sql.md): querying the `metrics` table and resource attributes.
- [`psutil` documentation](https://psutil.readthedocs.io/en/latest/): the library the metric values come from.
