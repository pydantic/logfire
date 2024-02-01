# Sampling

Sampling is the practice of discarding some traces or spans in order to reduce the amount of data that needs to be stored and analyzed. Sampling is a trade-off between cost and completeness of data.

## Head vs Tail sampling

Sampling can be done in two ways:

- Head sampling: sampling is done at the beginning of the trace / span. This is the most common way of sampling and is done at the SDK level.
- Tail sampling: sampling is done at the end of the trace / span. This is done at the collector level.

The main advantage of head sampling is that it immediately reduces overhead on the client side.
The main advantage of tail sampling is that it can be done with more information, such as the duration of the trace / span.

## Global sampling

To configure sampling globally for the SDK, use the [`trace_sample_rate`][logfire.configure(trace_sample_rate)]
option to [`logfire.configure()`][logfire.configure], the equivalent `LOGFIRE_TRACE_SAMPLE_RATE` environment variable
or config file option. See [Configuration](../configuration.md) for more information.

```python
import logfire

logfire.configure(trace_sample_rate=0.5)

with logfire.span("my_span"):  # This span will be sampled 50% of the time
    pass
```

## Fine grained sampling

You can tweak sampling on a per module or per code block basis using
[`logfire.with_trace_sample_rate()`][logfire.Logfire.with_trace_sample_rate].

```python
import logfire

sampled = logfire.with_trace_sample_rate(0.5)

with sampled.span("outer"):  # This span will be sampled 50% of the time
    # `with sampled.with_trace_sample_rate(0.1).span("inner")` would also work
    with logfire.with_trace_sample_rate(0.1).span("inner"):  # This span will be sampled 10% of the time
        pass
```
