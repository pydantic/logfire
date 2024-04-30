By default, **Logfire** does not collect system metrics.

To enable metrics, you need to install the `logfire[system-metrics]` extra:

{{ install_logfire(extras=['system-metrics']) }}

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
