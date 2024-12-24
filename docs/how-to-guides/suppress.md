# Suppress Spans and Metrics

At **Logfire** we want to provide you with the best experience possible. We understand that sometimes you might want to
fine tune the data you're sending to **Logfire**. That's why we provide you with the ability to suppress spans and metrics.

We provide two ways to suppress the data you're sending to **Logfire**: [Suppress Scopes](#suppress-scopes) and
[Suppress Instrumentation](#suppress-instrumentation).

## Suppress Scopes

You can suppress spans and metrics from a specific OpenTelemetry scope.
This is useful when you want to suppress data from a specific package.

For example, if you have [BigQuery] installed, it automatically instruments itself with OpenTelemetry.
Which means that you need to opt-out of instrumentation if you don't want to send data to **Logfire** related to BigQuery.

You can do this by calling the [`suppress_scopes`][logfire.Logfire.suppress_scopes] method.

```py
import logfire

logfire.configure()
logfire.suppress_scopes("google.cloud.bigquery.opentelemetry_tracing")
```

In this case, we're suppressing the scope `google.cloud.bigquery.opentelemetry_tracing`.
All spans and metrics related to BigQuery will not be sent to **Logfire**.

## Suppress Instrumentation

Sometimes you might want to suppress spans from a specific part of your code, and not a whole package.

For example, assume you are using [HTTPX], but you don't want to suppress all the spans and metrics related to it.
You just want to suppress a small part of the code that you know will generate a lot of spans.

You can do this by using the [`suppress_instrumentation`][logfire.suppress_instrumentation] context manager.

```py
import httpx
import logfire

logfire.configure()

client = httpx.Client()
logfire.instrument_httpx(client)

# The span generated will be sent to Logfire.
client.get("https://httpbin.org/get")

# The span generated will NOT be sent to Logfire.
with logfire.suppress_instrumentation():
    client.get("https://httpbin.org/get")
```

In this case, the span generated inside the `with logfire.suppress_instrumentation():` block will not be sent to **Logfire**.

[BigQuery]: ../integrations/databases/bigquery.md
