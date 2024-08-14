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

Then in your project, click on 'Dashboards' in the top bar, click 'New Dashboard', and select 'Basic System Metrics' from the dropdown.

## Configuration

By default, `instrument_system_metrics` collects only the metrics it needs to display the 'Basic System Metrics' dashboard. You can choose exactly which metrics to collect, and also how much information to collect about each metric, by passing an argument.
Here's what it looks like to specify the default configuration in full detail:

```py
logfire.instrument_system_metrics({
    'system.cpu.utilization': ['idle', 'iowait', 'user', 'system', 'irq', 'softirq'],
    'system.memory.utilization': ['available', 'used', 'free', 'active', 'inactive', 'buffers', 'cached', 'shared', 'wired', 'slab'],
    'system.swap.usage': ['used', 'free'],
    # There are no fields to configure for 'system.thread_count', so the value is None.
    'system.thread_count': None,
})
```

Each key here is a metric name. The values have different meanings for different metrics. For example, for `system.cpu.utilization`, the value is a list of CPU modes. So there will be a separate row for each CPU core saying what percentage of time it spent idle, another row for the time spent waiting for IO, etc. There are no fields to configure for `system.thread_count`, so the value is `None`.

To make it convenient to tweak the defaults, the argument can have many different shapes. To demonstrate, the following are all equivalent to the default:

```py
# If you don't need to configure the details of any metric, you can just pass a list of metric names.
logfire.instrument_system_metrics([
    'system.cpu.utilization',
    'system.memory.utilization',
    'system.swap.usage',
    'system.thread_count',
])

# If you need to configure the details of *some* metrics but not all,
# you can pass a dict with values for the metrics you want to configure,
# and `None` for the other metrics you just want to include with the default configuration.
logfire.instrument_system_metrics({
    'system.cpu.utilization': None,
    'system.memory.utilization': None,
    'system.swap.usage': None,
    'system.thread_count': None,
})


# You can also pass a single metric name as a string, e.g:
#   logfire.instrument_system_metrics('system.swap.usage')
# The string 'basic' is a special shortcut for the default metric names.
# You can also pass a list including 'basic' to add metrics to the default, e.g:
#   logfire.instrument_system_metrics(['basic', 'system.network.io'])
logfire.instrument_system_metrics('basic')

# Or you can use 'basic' as a dict key with the value `None`
# if you want to include and configure additional metrics.
# You cannot set the dict value of 'basic' to anything else since it contains different metrics.
logfire.instrument_system_metrics({'basic': None})
```



### Available Metrics

Logfire collects the following system metrics:

* `system.cpu.time`: CPU time spent in different modes.
* `system.cpu.utilization`: CPU utilization in different modes.
* `system.memory.usage`: Memory usage.
* `system.memory.utilization`: Memory utilization in different modes.
* `system.swap.usage`: Swap usage.
* `system.swap.utilization`: Swap utilization
* `system.disk.io`: Disk I/O operations (read/write).
* `system.disk.operations`: Disk operations (read/write).
* `system.disk.time`: Disk time (read/write).
* `system.network.dropped.packets`: Dropped packets (transmit/receive).
* `system.network.packets`: Packets (transmit/receive).
* `system.network.errors`: Network errors (transmit/receive).
* `system.network.io`: Network I/O (transmit/receive).
* `system.network.connections`: Network connections (family/type).
* `system.thread_count`: Thread count.
* `process.runtime.memory`: Process memory usage.
* `process.runtime.cpu.time`: Process CPU time.
* `process.runtime.gc_count`: Process garbage collection count.
