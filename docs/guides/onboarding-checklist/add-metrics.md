---
title: "Logfire Onboarding: Adding Metrics"
description: "Practical guide to adding Logfire metrics: Use system metrics or manual metrics to track Counter, Gauge or Callback Metrics."
---
**Pydantic Logfire** can be used to collect metrics from your application and send them to a metrics backend.

Metrics are a great way to record numerical values where you want to see an aggregation of the data (e.g. over time),
rather than the individual values.

## System Metrics

The easiest way to start using metrics is to enable system metrics.
See the [System Metrics][system-metrics] documentation to learn more.

## Manual Metrics

Let's see how to create and use custom metrics in your application.

```py
import logfire

# Create a counter metric
messages_sent = logfire.metric_counter('messages_sent')


# Increment the counter
def send_message():
    messages_sent.add(1)
```

### Counter

The Counter metric is particularly useful when you want to measure the frequency or occurrence of a certain
event or state in your application.

You can use this metric for counting things like:

* The number of exceptions caught.
* The number of requests received.
* The number of items processed.

To create a counter metric, use the [`logfire.metric_counter`][logfire.Logfire.metric_counter] function:

```py
import logfire

counter = logfire.metric_counter(
    name='exceptions',
    unit='1',  # (1)!
    description='Number of exceptions caught',
)

try:
    raise Exception('oops')
except Exception:
    counter.add(1)
```

1. The `unit` parameter is optional, but it's a good practice to specify it.
    It should be a string that represents the unit of the counter.
    If the metric is _unitless_, you can use `'1'`.

You can read more about the Counter metric in the [OpenTelemetry documentation][counter-metric].

### Histogram

The Histogram metric is particularly useful when you want to measure the distribution of a set of values.

You can use this metric for measuring things like:

* The duration of a request.
* The size of a file.
* The number of items in a list.

To create a histogram metric, use the [`logfire.metric_histogram`][logfire.Logfire.metric_histogram] function:

```py
import logfire

histogram = logfire.metric_histogram('request_duration', unit='ms', description='Duration of requests')  # (1)!

for duration in [10, 20, 30, 40, 50]:
    histogram.record(duration)
```

1. The `unit` parameter is optional, but it's a good practice to specify it.
    It should be a string that represents the unit of the histogram.

You can read more about the Histogram metric in the [OpenTelemetry documentation][histogram-metric].

A histogram is also what to reach for if you are used to Prometheus summaries. Logfire does not store OTLP `Summary` metrics, which report quantiles the sender has already computed: see [Summary metrics are not supported](../../reference/limits.md#summary-metrics-are-not-supported). Record the raw values in a histogram and compute percentiles at query time instead.

### Up-Down Counter

The "Up-Down Counter" is a type of counter metric that allows both incrementing (up) and decrementing (down) operations.
Unlike a regular counter that only allows increments, an up-down counter can be increased or decreased based on
the events or states you want to track.

You can use this metric for measuring things like:

* The number of active connections.
* The number of items in a queue.
* The number of users online.

To create an up-down counter metric, use the [`logfire.metric_up_down_counter`][logfire.Logfire.metric_up_down_counter] function:

```py
import logfire

active_users = logfire.metric_up_down_counter('active_users', unit='1', description='Number of active users')  # (1)!


def user_logged_in():
    active_users.add(1)


def user_logged_out():
    active_users.add(-1)
```

1. The `unit` parameter is optional, but it's a good practice to specify it.
    It should be a string that represents the unit of the up-down counter.
    If the metric is _unitless_, you can use `'1'`.

You can read more about the Up-Down Counter metric in the [OpenTelemetry documentation][up-down-counter-metric].

### Gauge

The Gauge metric is particularly useful when you want to measure the current value of a certain state
or event in your application. Unlike the counter metric, the gauge metric does not accumulate values over time.

You can use this metric for measuring things like:

* The current temperature.
* The current memory usage.
* The current number of active connections.
* The current number of users online.

To create a gauge metric, use the [`logfire.metric_gauge`][logfire.Logfire.metric_gauge] function:

```py
import logfire

temperature = logfire.metric_gauge('temperature', unit='C', description='Temperature')


def set_temperature(value: float):
    temperature.set(value)
```

You can read more about the Gauge metric in the [OpenTelemetry documentation][gauge-metric].

#### Poll an async source

OpenTelemetry observable callbacks must return synchronously when the metrics SDK collects them. They run on an SDK
thread, where awaiting a coroutine would block collection and an unawaited coroutine would not produce an observation.
If a metric value comes from an async API, let your application's lifecycle own a polling task and update a normal
[`logfire.metric_gauge`][logfire.Logfire.metric_gauge].

This runnable example starts a polling task and runs until you press Ctrl+C. `queue_depth.set(...)` updates the current
measurement. The metrics SDK exports it on its regular collection schedule, and `logfire.force_flush()` requests a
final export during shutdown.

```py hl_lines="23-32 35-42" skip-run="true" skip-reason="long-running"
import asyncio
from contextlib import suppress

import logfire

POLL_INTERVAL_SECONDS = 30

logfire.configure()

queue_depth = logfire.metric_gauge(
    'jobs.queue_depth',
    unit='1',
    description='Number of jobs waiting to run',
)


async def read_queue_depth() -> int:
    """Replace this with a call to your async client."""
    await asyncio.sleep(0.01)
    return 7


async def poll_queue_depth() -> None:
    """Update the gauge until the application stops this task."""
    while True:
        try:
            value = await read_queue_depth()
        except Exception:  # Replace with the exception your client raises.
            logfire.exception('Failed to read queue depth')
        else:
            queue_depth.set(value)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    poller = asyncio.create_task(poll_queue_depth(), name='queue-depth-poller')
    try:
        await asyncio.Event().wait()  # Keep this standalone example running.
    finally:
        poller.cancel()
        with suppress(asyncio.CancelledError):
            await poller


try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
finally:
    logfire.force_flush()
```

Run the script to update `jobs.queue_depth` immediately, then wait 30 seconds after each read before reading again. Open
[**Metrics** in the project sidebar](../web-ui/metrics-explorer.md) to find it under the `jobs` namespace. A line becomes
visible after Logfire collects multiple points. Press Ctrl+C to stop the script and export its final value.

Replace `read_queue_depth()` with your async client call. In a real application, create the `poll_queue_depth()` task in
the application's startup hook instead of `main()`. Keep the same ownership shown above: the code that starts the task
must retain it, cancel it during shutdown, and await the cancelled task so its cleanup can finish.

Long-running pollers usually use **fixed-delay polling**: each delay starts after the previous read finishes. Slow reads
therefore move later polls, but one task never overlaps two reads. **Fixed-rate polling** instead calculates each start
time from a clock so that polls target a regular schedule. If a read takes longer than one interval, skip a missed run
or continue late. Do not start concurrent reads unless the source, gauge labels, timeout, and shutdown behavior are
designed for overlap.

Decide how failures should affect the metric before deploying a poller:

- Catch expected source exceptions inside the loop so that one failure does not silently end the task. Add a timeout,
  exponential backoff, and limited retry logging when the source can remain unavailable.
- A failed poll records no new point. A query over a wider time range can still include the previous successful point,
  so it may be mistaken for a current value. Record a separate last-success timestamp or poll-success metric if
  consumers need to detect staleness.
- Do not catch `BaseException`. `asyncio.CancelledError` then stops the loop. If you catch cancellation to run
  poller-specific cleanup, always re-raise it.
- Each worker process creates its own task and metric series. Add a worker-identifying attribute when you need separate
  values, or aggregate the per-worker series in your query. Do not interpret one worker's gauge as a process-wide or
  cluster-wide value.

Use an [observable callback][gauge-callback-metric] only when reading the value is synchronous, quick, and safe for the
metrics SDK to invoke. Lifecycle-owned polling keeps async I/O on the application's event loop and does not require a
new async callback API.

### Callback Metrics

Callback metrics, or observable metrics, are a way to create metrics that are automatically emitted every 60 seconds in
a background thread.

#### Counter Callback

To create a counter callback metric, use the [`logfire.metric_counter_callback`][logfire.Logfire.metric_counter_callback] function:

```py
from typing import Iterable

from opentelemetry.metrics import CallbackOptions, Observation

import logfire


def cpu_time_callback(options: CallbackOptions) -> Iterable[Observation]:
    observations = []
    with open('/proc/stat') as procstat:  # (1)!
        procstat.readline()  # skip the first line
        for line in procstat:
            if not line.startswith('cpu'):
                break
            cpu, user_time, nice_time, system_time = line.split()
            observations.append(Observation(int(user_time) // 100, {'cpu': cpu, 'state': 'user'}))
            observations.append(Observation(int(nice_time) // 100, {'cpu': cpu, 'state': 'nice'}))
            observations.append(Observation(int(system_time) // 100, {'cpu': cpu, 'state': 'system'}))
    return observations


logfire.metric_counter_callback(
    'system.cpu.time',
    unit='s',
    callbacks=[cpu_time_callback],
    description='CPU time',
)
```

1. This is a Linux-specific example that will not work on macOS and Windows.

You can read more about the Counter metric in the [OpenTelemetry documentation][counter-callback-metric].

#### Gauge Callback

The gauge metric is particularly useful when you want to measure the current value of a certain state
or event in your application. Unlike the counter metric, the gauge metric does not accumulate values over time.

To create a gauge callback metric, use the [`logfire.metric_gauge_callback`][logfire.Logfire.metric_gauge_callback] function:

```py
from typing import Iterable

from opentelemetry.metrics import CallbackOptions, Observation

import logfire


def get_temperature(room: str) -> float:
    return 22.0


def temperature_callback(options: CallbackOptions) -> Iterable[Observation]:
    for room in ['kitchen', 'living_room', 'bedroom']:
        temperature = get_temperature(room)
        yield Observation(temperature, {'room': room})


logfire.metric_gauge_callback(
    'temperature',
    unit='C',
    callbacks=[temperature_callback],
    description='Temperature',
)
```

You can read more about the Gauge metric in the [OpenTelemetry documentation][gauge-callback-metric].

#### Up-Down Counter Callback

This is the callback version of the [up-down counter metric](#up-down-counter).

To create an up-down counter callback metric, use the
[`logfire.metric_up_down_counter_callback`][logfire.Logfire.metric_up_down_counter_callback] function:

```py
from typing import Iterable

from opentelemetry.metrics import CallbackOptions, Observation

import logfire


def get_active_users() -> int:
    return 5


def active_users_callback(options: CallbackOptions) -> Iterable[Observation]:
    active_users = get_active_users()
    yield Observation(active_users, {})


logfire.metric_up_down_counter_callback(
    'active_users',
    unit='1',
    callbacks=[active_users_callback],
    description='Number of active users',
)
```

You can read more about the Up-Down Counter metric in the [OpenTelemetry documentation][up-down-counter-callback-metric].

## You're done

You've integrated Logfire, added manual and automatic tracing, and started recording metrics. Your Python app is now
sending the data you need to monitor performance, find bugs, and understand behavior.

From here:

- **Watch it live**: open the [Live view](../web-ui/live.md) and use your app.
- **Instrument the libraries you use**: [Integrations](../../integrations/index.md) add rich tracing to your web framework, database, and HTTP clients with one line each.
- **Build dashboards and alerts**: turn the questions you check often into [Dashboards](../web-ui/dashboards.md), and get told about problems with [Alerts](../web-ui/alerts.md).

[counter-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#counter
[histogram-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#histogram
[up-down-counter-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#updowncounter
[gauge-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#gauge
[counter-callback-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-counter
[gauge-callback-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-gauge
[up-down-counter-callback-metric]: https://opentelemetry.io/docs/specs/otel/metrics/api/#asynchronous-updowncounter
[system-metrics]: ../../integrations/system-metrics.md
