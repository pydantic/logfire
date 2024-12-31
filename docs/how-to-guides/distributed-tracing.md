**Logfire** builds on OpenTelemetry, which keeps track of *context* to determine the parent trace/span of a new span/log and whether it should be included by sampling. *Context propagation* is when this context is serialized and sent to another process, so that tracing can be distributed across services while allowing the full tree of spans to be cleanly reconstructed and viewed together.

## Manual Context Propagation

**Logfire** provides a thin wrapper around the OpenTelemetry context propagation API to make manual distributed tracing easier. You shouldn't usually need to do this yourself, but it demonstrates the concept nicely. Here's an example:

```python
from logfire.propagate import attach_context, get_context
import logfire

logfire.configure()

with logfire.span('parent'):
    ctx = get_context()

print(ctx)

# Attach the context in another execution environment
with attach_context(ctx):
    logfire.info('child')  # This log will be a child of the parent span.
```

`ctx` will look something like this:

```python
{'traceparent': '00-d1b9e555b056907ee20b0daebf62282c-7dcd821387246e1c-01'}
```

This contains 4 fields:

- `00` is a version number which you can ignore.
- `d1b9e555b056907ee20b0daebf62282c` is the `trace_id`.
- `7dcd821387246e1c` is the `span_id` of the parent span, i.e. the `parent_span_id` of the child log.
- `01` is the `trace_flags` field and indicates that the trace should be included by sampling.

See the [API reference](../../reference/api/propagate.md) for more details about these functions.

## Integrations

OpenTelemetry instrumentation libraries (which **Logfire** uses for its integrations) handle context propagation automatically, even across different programming languages. For example:

- Instrumented HTTP clients such as [`requests`](../../integrations/requests.md) and [`httpx`](../../integrations/httpx.md) will automatically set the `traceparent` header when making requests.
- Instrumented web servers such as [`flask`](../../integrations/flask.md) and [`fastapi`](../../integrations/fastapi.md) will automatically extract the `traceparent` header and use it to set the context for server spans.
- The [`celery` integration](../../integrations/celery.md) will automatically propagate the context to child tasks.

## Thread and Pool executors

**Logfire** automatically patches [`ThreadPoolExecutor`][concurrent.futures.ThreadPoolExecutor] and [`ProcessPoolExecutor`][concurrent.futures.ProcessPoolExecutor] to propagate context to child threads and processes. This means that logs and spans created in child threads and processes will be correctly associated with the parent span. Here's an example to demonstrate:

```python
import logfire
from concurrent.futures import ThreadPoolExecutor

logfire.configure()


@logfire.instrument("Doubling {x}")
def double(x: int):
    return x * 2


with logfire.span("Doubling everything") as span:
    executor = ThreadPoolExecutor()
    results = list(executor.map(double, range(3)))
    span.set_attribute("results", results)
```

## Unintentional Distributed Tracing

Because instrumented web servers automatically extract the `traceparent` header by default, your spans can accidentally pick up the wrong context from an externally instrumented client, or from your cloud provider such as Google Cloud Run. This can lead to:

- Spans missing their parent.
- Spans being mysteriously grouped together.
- Spans missing entirely because the original trace was excluded by sampling.
