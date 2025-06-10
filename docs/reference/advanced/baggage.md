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

Note that the `set_baggage` contextmanager will always update the OpenTelemetry Baggage used during propagation,
regardless of whether you configure logfire to add the Baggage to span attributes.

!!! info "Baggage and distributed tracing"
    Baggage is propagated automatically during distributed tracing, but in order for the propagated baggage to be
    added as _attributes_ in other services, you need to ensure a `BaggageSpanProcessor` is configured in those services.

    If using the `logfire` library from Python, that is as simple as calling `logfire.configure(add_baggage_to_attributes=True)`,
    but you can accomplish this with the opentelemetry SDK in many other languages as well. You can find more information
    in the official [OpenTelemetry Baggage documentation](https://opentelemetry.io/docs/concepts/signals/baggage/).
