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

See the [API reference](../../reference/api/propagate.md) for more details.

## Integrations



Logfire leverages OTEL’s built-in mechanisms to propagate context automatically through HTTP headers, specifically the `traceparent` header. This header carries essential tracing information such as the trace ID and parent span ID, enabling seamless tracing across services.

For example, in a FastAPI application, OTEL instrumentation simplifies tracing by automatically handling the `traceparent` header:

- **Incoming Requests**: The `traceparent` header in HTTP requests is parsed to establish the tracing context.
- **Outgoing Requests**: When making HTTP calls (e.g., using `requests`), the header is automatically added, ensuring continuity in the trace.

### Potential Pitfalls

#### Unintentional Distributed Tracing

Distributed tracing issues can arise unintentionally:

- **External Trace Roots**: External clients or providers might set a `traceparent` header, changing trace origins.
- **Missing Parent Spans**: Gaps in the UI appear when upstream services alter the trace context.
- **Sampling Conflicts**: Providers like Google Cloud Run may override sampling, causing inconsistencies.

### Conclusion

Logfire simplifies the complexities of distributed tracing by abstracting OTEL’s functionality while allowing both automatic and manual propagation of tracing context. By understanding its features and addressing potential pitfalls, you can effectively manage and debug distributed systems with ease.
