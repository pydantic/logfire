# Sampling

Sampling is the practice of discarding some traces or spans in order to reduce the amount of data that needs to be stored and analyzed. Sampling is a trade-off between cost and completeness of data.

To configure sampling for the SDK:

- Set the [`trace_sample_rate`][logfire.configure(trace_sample_rate)] option of [`logfire.configure()`][logfire.configure] to a number between 0 and 1, or
- Set the `LOGFIRE_TRACE_SAMPLE_RATE` environment variable, or
- Set the `trace_sample_rate` config file option.

See [Configuration](../../reference/configuration.md) for more information.

```python
import logfire

logfire.configure(trace_sample_rate=0.5)

with logfire.span("my_span"):  # This span will be sampled 50% of the time
    pass
```

<!-- ## Fine grained sampling

You can tweak sampling on a per module or per code block basis using
[`logfire.with_trace_sample_rate()`][logfire.Logfire.with_trace_sample_rate].

```python
import logfire

sampled = logfire.with_trace_sample_rate(0.5)

with sampled.span("outer"):  # This span will be sampled 50% of the time
    # `with sampled.with_trace_sample_rate(0.1).span("inner")` would also work
    with logfire.with_trace_sample_rate(0.1).span("inner"):  # This span will be sampled 10% of the time
        pass
``` -->
