# Baggage

In OpenTelemetry, [Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/) is a key-value store that can be
used to propagate any data you like alongside context during (distributed) tracing.
Baggage is included in the context of a trace, and is propagated across service boundaries, allowing you to
attach metadata to a trace that can be accessed by any service that participates in that trace.

Technically, Baggage is a separate key-value store and is formally unassociated with attributes on spans, metrics, or
logs without explicitly creating those attributes from the Baggage.

However, a common use cases for Baggage is to add data to span attributes across a whole trace. Because of this,
**Logfire** provides convenience APIs for setting Baggage and automatically adding Baggage to descendant span
attributes.

## Why use Baggage to set attributes?

Though tracing makes it a lot easier to understand and visualize the relationship between parent and child spans,
it's still usually easiest to express filtering criteria on an _individual_ span when doing custom searches,
aggregations, etc.

As a concrete example, you might have received an issue report from a user with user_id `scolvin`, and want to
search for all spans corresponding to slow database queries that happened in requests made by that user. You might find
all slow database requests with the query `duration > 1 AND attributes ? 'db.statement'`, but trying to filter
down to only those spans coming from requests by a specific user is harder.

## Basic usage

Here's how to solve the above example using Baggage:

```python
import logfire

logfire.configure()

with logfire.set_baggage(user_id='scolvin'):
    print(logfire.get_baggage())  # (just for demonstration, not usually needed)
    #> {'user_id': 'scolvin'}

    # All spans opened here (and their descendants)
    # will have the attribute `logfire.baggage` set to `{"user_id": "scolvin"}`
    # (or more if you set other baggage values)
    with logfire.span('inside-baggage-span'):
        ...
```

Then you can update your query to
`duration > 1 AND attributes ? 'db.statement' AND attributes->'logfire.baggage'->>'user_id' = 'scolvin'`.

## Disabling

If you don't want to add Baggage to span attributes, pass `add_baggage_to_attributes=False` to the
`logfire.configure()` function. This may slightly improve performance.
The `set_baggage` contextmanager will still update the OpenTelemetry Baggage and propagate it to other services.

## Using with multiple services

Baggage is propagated automatically to other processes along with the trace context if you've instrumented
the appropriate libraries, e.g. HTTP clients and servers.
See the [Distributed Tracing](../../how-to-guides/distributed-tracing.md#integrations)
documentation for more information on how this works.

For example, if you:

1. Instrument [`httpx`](../../integrations/http-clients/httpx.md) in one service, where you
2. make an `httpx` request in the context of `with logfire.set_baggage`
3. to another service that has instrumented [`fastapi`](../../integrations/web-frameworks/fastapi.md)

then the values set in `logfire.set_baggage` in step 2 will be available as Baggage in the `fastapi` service,
and by default those values will be added as attributes to the spans created in that service.

This works by including the values in the `Baggage` HTTP header in the request made by `httpx`.
This happens regardless of whether the request is received by a server that can read the Baggage or not,
or whether either service sets Baggage as span attributes. So it's important to be careful about what you put in Baggage:

- **Don't put sensitive information in Baggage**, as it may be sent to third party services. While span attributes from baggage are still [scrubbed](../../how-to-guides/scrubbing.md) by default, the Baggage header itself is not scrubbed.
- **Don't put large values in Baggage**, as this may add bloat to HTTP headers. Large values may also be dropped by servers instead of being propagated.

### With other OpenTelemetry SDKs

If all your services are using the Python Logfire SDK, then Baggage will be set as span attributes automatically by default,
so you only need to ensure that context propagation is working.

For other OpenTelemetry SDKs, Baggage will still be propagated automatically, but to set the span attributes requires extra configuration.
Try searching for `BaggageSpanProcessor` and the name of the language you're using.

These processors will typically set span attributes with the same name as the Baggage key, e.g. if the baggage key is `user_id`, the span attribute will also just be `user_id`.
This differs from Logfire which puts the values inside the `logfire.baggage` JSON attribute to avoid conflicts with attributes set directly on the span.
You can make Logfire behave like other SDKs with `logfire.configure(add_baggage_to_attributes='direct')`.
Then you can query e.g. `attributes->>'user_id' = 'scolvin'` which will work for all spans in the trace regardless of whether they were created by Logfire or another OpenTelemetry SDK.
