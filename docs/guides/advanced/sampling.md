# Sampling

Sampling is the practice of discarding some traces or spans in order to reduce the amount of data that needs to be
stored and analyzed. Sampling is a trade-off between cost and completeness of data.

_Head sampling_ means the decision to sample is made at the beginning of a trace. This is simpler and more common. _Tail
sampling_ means the decision to sample is delayed, possibly until the end of a trace. This means there is more
information available to make the decision, but this adds complexity.

Sampling usually happens at the trace level, meaning entire traces are kept or discarded. This way the remaining traces
are generally complete.

## Random head sampling

Here's an example of randomly sampling 50% of traces:

```python
import logfire

logfire.configure(sampling=logfire.SamplingOptions(head=0.5))

for x in range(10):
    with logfire.span(f'span {x}'):
        logfire.info(f'log {x}')
```

This outputs something like:

```
11:09:29.041 span 0
11:09:29.041   log 0
11:09:29.041 span 1
11:09:29.042   log 1
11:09:29.042 span 4
11:09:29.042   log 4
11:09:29.042 span 5
11:09:29.042   log 5
11:09:29.042 span 7
11:09:29.042   log 7
```

Note that 5 out of 10 traces are kept, and that the child log is kept if and only if the parent span is kept.

## Tail sampling by level and duration

Random head sampling often works well, but you may not want to lose any traces which indicate problems. In this case,
you can use tail sampling. Here's a simple example:

```python
import time

import logfire

logfire.configure(sampling=logfire.SamplingOptions.level_or_duration())

for x in range(3):
    # None of these are logged
    with logfire.span('excluded span'):
        logfire.info(f'info {x}')

    # All of these are logged
    with logfire.span('included span'):
        logfire.error(f'error {x}')

for t in range(1, 10, 2):
    with logfire.span(f'span with duration {t}'):
        time.sleep(t)
```

This outputs something like:

```
11:37:45.484 included span
11:37:45.484   error 0
11:37:45.485 included span
11:37:45.485   error 1
11:37:45.485 included span
11:37:45.485   error 2
11:37:49.493 span with duration 5
11:37:54.499 span with duration 7
11:38:01.505 span with duration 9
```

[`logfire.SamplingOptions.level_or_duration()`][logfire.sampling.SamplingOptions.level_or_duration] creates an instance
of [`logfire.sampling.SamplingOptions`][logfire.sampling.SamplingOptions] with simple tail sampling. With no arguments,
it means that a trace will be included if and only if it has at least one span/log that:

1. has a log level greater than `info` (the default of any span), or
2. has a duration greater than 5 seconds.

This way you won't lose information about warnings/errors or long-running operations. You can customize what to keep with the `level_threshold` and `duration_threshold` arguments.

## Combining head and tail sampling

You can combine head and tail sampling. For example:

```python
import logfire

logfire.configure(sampling=logfire.SamplingOptions.level_or_duration(head=0.1))
```

This will only keep 10% of traces, even if they have a high log level or duration. Traces that don't meet the tail sampling criteria will be discarded every time.

## Keeping a fraction of all traces

To keep some traces even if they don't meet the tail sampling criteria, you can use the `background_rate` argument. For example, this script:

```python
import logfire

logfire.configure(sampling=logfire.SamplingOptions.level_or_duration(background_rate=0.3))

for x in range(10):
    logfire.info(f'info {x}')
for x in range(5):
    logfire.error(f'error {x}')
```

will output something like:

```
12:24:40.293 info 2
12:24:40.293 info 3
12:24:40.293 info 7
12:24:40.294 error 0
12:24:40.294 error 1
12:24:40.294 error 2
12:24:40.294 error 3
12:24:40.295 error 4
```

i.e. about 30% of the info logs and 100% of the error logs are kept.

(Technical note: the trace ID is compared against the head and background rates to determine inclusion, so the probabilities don't depend on the number of spans in the trace, and the rates give the probabilities directly without needing any further calculations. For example, with a head sample rate of `0.6` and a background rate of `0.3`, the chance of a non-notable trace being included is `0.3`, not `0.6 * 0.3`.)

## Caveats of tail sampling

### Memory usage

For tail sampling to work, all the spans in a trace must be kept in memory until either the trace is included by sampling or the trace is completed and discarded. In the above example, the spans named `included span` don't have a high enough level to be included, so they are kept in memory until the error logs cause the entire trace to be included. This means that traces with a large number of spans can consume a lot of memory, whereas without tail sampling the spans would be regularly exported and freed from memory without waiting for the rest of the trace.

In practice this is usually OK, because such large traces will usually exceed the duration threshold, at which point the trace will be included and the spans will be exported and freed. This works because the duration is measured as the time between the start of the trace and the start/end of the most recent span, so the tail sampler can know that a span will exceed the duration threshold even before it's complete. For example, running this script:

```python
import time

import logfire

logfire.configure(sampling=logfire.SamplingOptions.level_or_duration())

with logfire.span('span'):
    for x in range(1, 10):
        time.sleep(1)
        logfire.info(f'info {x}')
```

will do nothing for the first 5 seconds, before suddenly logging all this at once:

```
12:29:43.063 span
12:29:44.065   info 1
12:29:45.066   info 2
12:29:46.072   info 3
12:29:47.076   info 4
12:29:48.082   info 5
```

followed by additional logs once per second. This is despite the fact that at this stage the outer span hasn't completed yet and the inner logs each have 0 duration.

However, memory usage can still be a problem in any of the following cases:

- The duration threshold is set to a high value
- Spans are produced extremely rapidly
- Spans contain large attributes

### Distributed tracing

Logfire's tail sampling is implemented in the SDK and only works for traces within one process. If you need tail sampling with distributed tracing, consider deploying the [Tail Sampling Processor in the OpenTelemetry Collector](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/processor/tailsamplingprocessor/README.md).

If a trace was started on another process and its context was propagated to the process using the Logfire SDK tail sampling, the whole trace will be included.

If you start a trace with the Logfire SDK with tail sampling, and then propagate the context to another process, the spans generated by the SDK may be discarded, while the spans generated by the other process may be included, leading to an incomplete trace.

## Custom head sampling

If you need more control than random sampling, you can pass an [OpenTelemetry `Sampler`](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.sampling.html). For example:

```python
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, ParentBased, Sampler, SamplingResult

import logfire


class MySampler(Sampler):
    def should_sample(self, parent_context, trace_id, name, *args, **kwargs) -> SamplingResult:
        if name == 'exclude me':
            sampler = ALWAYS_OFF
        else:
            sampler = ALWAYS_ON
        return sampler.should_sample(parent_context, trace_id, name, *args, **kwargs)

    def get_description(self) -> str:
        return 'MySampler'


logfire.configure(
    sampling=logfire.SamplingOptions(
        head=ParentBased(
            MySampler(),
        )
    )
)

with logfire.span('keep me'):
    logfire.info('kept child')

with logfire.span('exclude me'):
    logfire.info('excluded child')
```

This will output something like:

```
10:37:30.897 keep me
10:37:30.898   kept child
```

Note that the sampler explicitly excluded only the span named `exclude me`. The reason that the `excluded child` log is not included is that `MySampler` was wrapped in a `ParentBased` sampler, which excludes spans whose parents are excluded. If you remove that and simply pass `head=MySampler()`, the `excluded child` log will be included, resulting in an incomplete trace.

You can also pass a `Sampler` to the `head` argument of `SamplingOptions.level_or_duration` to combine tail sampling with custom head sampling.

## Custom tail sampling

If you want tail sampling with more control than `level_or_duration`, you can pass a function to `tail`:

```python
import logfire


def get_tail_sample_rate(span_info):
    if span_info.duration >= 1:
        # Keep 50% of traces with duration >= 1 second
        return 0.5

    if span_info.level > 'warn':  # span_info.level is a special object that can be compared to log level names
        # Keep 30% of traces with a warning or error and with duration < 1 second
        return 0.3

    # Keep 10% of other traces
    return 0.1


logfire.configure(
    sampling=logfire.SamplingOptions(
        # Discard 50% of traces at the beginning to reduce the overhead of generating spans.
        # This is optional, but improves performance, and we know that `get_tail_sample_rate`
        # will always return at most 0.5 so the other 50% of traces will be discarded anyway.
        # The probabilities are not independent - this will not discard traces that would
        # otherwise have been kept by tail sampling.
        head=0.5,
        tail=get_tail_sample_rate,
    ),
)
```
