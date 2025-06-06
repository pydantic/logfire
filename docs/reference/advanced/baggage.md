# Baggage

In OpenTelemetry, [Baggage](https://opentelemetry.io/docs/concepts/signals/baggage/) is a key-value store that can be
used to propagate any data you like alongside context during (distributed) tracing.

Technically, Baggage is a separate key-value store and is formally unassociated with attributes on spans, metrics, or
logs without explicitly creating those attributes from the Baggage.

However, because a common use cases for Baggage is to add data to span attributes across a whole trace, **Logfire**
provides convenience APIs for setting Baggage and automatically adding Baggage to descendant span attributes.

### Why use Baggage to set attributes?

Though tracing makes it a lot easier to understand and visualize the relationship between parent and child spans,
it's still usually easiest to express filtering criteria on an _individual_ span when doing custom searches,
aggregations, etc.

As a concrete example, you might have received an issue report from a user with user_id `scolvin`, and want to
search for all spans corresponding to slow database queries that happened in requests made by that user. You might find
all slow database requests with the query `duration > '1 second' AND attributes ? 'db.statement'`, but trying to filter
down to only those spans coming from requests by a specific user is harder.

But Baggage provides a solution to this: just add `{'user_id': 'scolvin'}` at the start of your endpoint, and
ensure that all Baggage is converted to span attributes. Then every span created while handling that endpoint will
have an appropriately set `user_id` attribute, and you can update your query to
`duration > '1 second' AND attributes ? 'db.statement' AND attributes->>'user_id' = 'scolvin'`.

### Using Baggage in Logfire

To enable Baggage processing, you just need to add the `add_baggage_to_attributes=True` argument to `logfire.configure()`:

```python
import logfire
logfire.configure(add_baggage_to_attributes=True)
```

This will ensure that any OpenTelemetry Baggage is added as attributes to the spans handled by logfire.
(Under the hood, this is just adding a [`BaggageSpanProcessor`](https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/processor/opentelemetry-processor-baggage) to the list of additional span processors.)

Once you've done this, you can use the [`update_baggage`][logfire.update_baggage] contextmanager to contextually update the Baggage (which will
be added as attributes to all spans opened under that context):

```python
import logfire

logfire.configure(add_baggage_to_attributes=True)

with logfire.update_baggage({
    'user_id': '123',
    'session': 'abcdef',
}):
    # All spans opened here and their descendants will have attributes user_id='123' and session='abcdef'
    with logfire.span('inside-baggage-span'):
        ...
```

Note that the `update_baggage` contextmanager will always update the OpenTelemetry Baggage used during propagation,
regardless of whether you configure logfire to add the Baggage to span attributes.

!!! info "Baggage and distributed tracing"
    Baggage is propagated automatically during distributed tracing, but in order for the propagated baggage to be
    added as _attributes_ in other services, you need to ensure a `BaggageSpanProcessor` is configured in those services.

    If using the `logfire` library from Python, that is as simple as calling `logfire.configure(add_baggage_to_attributes=True)`,
    but you can accomplish this with the opentelemetry SDK in many other languages as well. You can find more information
    in the official [OpenTelemetry Baggage documentation]https://opentelemetry.io/docs/concepts/signals/baggage/).
