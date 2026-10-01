---
title: "Route traces to different Logfire projects"
description: "Use an OpenTelemetry Collector to send each request to a different Logfire project, chosen while the request runs, without changing application code."
---
# Route traces to different Logfire projects

Send each request to whichever Logfire project it belongs to, decided while the request runs. Your application sends everything to one address and never learns the project tokens.

Reach for this when one deployment serves data that must land in separate projects:

- **One project per customer**, so each customer's data stays isolated and can be deleted on its own.
- **Separate projects for production and staging traffic** coming from the same cluster.
- **A restricted project for sensitive workloads**, with a smaller set of people able to read it.

## When to route in the Collector

An [OpenTelemetry Collector](otel-collector-overview.md) is a separate program that sits between your apps and Logfire, gathering telemetry and forwarding it. Routing there keeps every [write token](../create-write-tokens.md) (the credential a deployed app uses to send data to a project) in one configuration file instead of in every application instance, and you change where data goes by editing that file rather than redeploying.

You do not need a Collector when the split is fixed per deployment. If each service, environment, or region always sends to the same project, give each one its own `LOGFIRE_TOKEN` and stop there. Routing pays off when one running process produces data for more than one project.

## Before you start

You need:

- **A Collector already forwarding to Logfire.** [Send data through a Collector](send-data-through-a-collector.md) gets one running; this page changes where it sends.
- **A write token for each destination project.** Create one per project under **Settings → Write tokens**, as described in [Create write tokens](../create-write-tokens.md). The configuration below reads them from the environment, so export one variable per project before starting the Collector:

    ```bash
    export LOGFIRE_TOKEN_ACME='<acme-write-token>'
    export LOGFIRE_TOKEN_GLOBEX='<globex-write-token>'
    export LOGFIRE_TOKEN_INTERNAL='<internal-write-token>'
    ```

- **The `contrib` build of the Collector**, `otel/opentelemetry-collector-contrib`. The routing connector used below is not in the core build.

## Tag each request with its destination

The Collector can only route on something it can see in the data. Attach the routing key once at the edge of the request with [baggage](../../reference/advanced/baggage.md), small key/value data that rides along with a request across services:

```python
import logfire


def handle_request() -> None:
    logfire.info('handling the request')


customer_id = 'acme'

with logfire.set_baggage(tenant=customer_id):
    handle_request()
```

Every span (one unit of work: a single operation, with a name, a start, and a duration) opened inside that block carries a `tenant` attribute, including spans created by instrumented libraries.

Two limits are worth knowing before you rely on this:

- **Spans started before the block do not carry the key.** The key is stamped onto a span when the span starts, so a server span that an instrumented web framework opened before your code ran never gets it, and goes to the default pipeline. That splits the trace (the full journey of one request, made of nested spans) across projects. Either accept the server span landing in the default project, or set the attribute on it yourself: `from opentelemetry import trace` then `trace.get_current_span().set_attribute('tenant', customer_id)` inside the handler.
- **Downstream services need the same behavior.** Baggage travels with the request, but turning it into a span attribute is what the Logfire SDK's `add_baggage_to_attributes` setting does. A service using a plain OpenTelemetry SDK propagates the baggage without putting it on its spans, so those spans are not routed by it.

!!! warning
    Baggage travels in request headers, so a caller outside your system can set it. Never route on a value that arrived from an untrusted client: overwrite the key from your own authenticated tenant state at the edge, before the request reaches anything that opens a span. Otherwise a caller can choose which project their data lands in.

Point the application at the Collector and turn off sending straight to Logfire, so the Collector is the only path out:

```python skip-run="true" skip-reason="external-connection"
import os

os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = 'http://collector:4318'

import logfire

logfire.configure(send_to_logfire=False)
```

Set the base endpoint rather than only `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`. With `send_to_logfire=False` and a traces-only endpoint, the SDK has nowhere to send metrics and logs and drops them silently.

If you leave `send_to_logfire=True`, the application keeps sending a full copy to the project its own token points at, in addition to whatever the Collector does.

## Configure the Collector

The `routing` connector reads an attribute off each span and sends it down a different pipeline. Each pipeline ends in an exporter carrying its own project's write token:

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

connectors:
  routing:
    # Anything that matches no condition below goes here.
    default_pipelines: [traces/internal]
    error_mode: ignore
    table:
      - context: span
        condition: attributes["tenant"] == "acme"
        pipelines: [traces/acme]
      - context: span
        condition: attributes["tenant"] == "globex"
        pipelines: [traces/globex]

exporters:
  otlphttp/acme:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_ACME}"
  otlphttp/globex:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_GLOBEX}"
  otlphttp/internal:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_INTERNAL}"

service:
  pipelines:
    traces/in:
      receivers: [otlp]
      exporters: [routing]
    traces/acme:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/acme]
    traces/globex:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/globex]
    traces/internal:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/internal]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/internal]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/internal]
```

The routing connector works on spans, so the metrics and logs pipelines above are not routed: they go to one project. Give them their own destination if that is not what you want, and leave them out only if your applications send neither.

Set the endpoint to the region your projects live in: `https://logfire-us.pydantic.dev` or `https://logfire-eu.pydantic.dev`. All destination projects must be in the same region as the endpoint you give their exporter.

Points worth knowing about this config:

- **`context: span`** routes each span by its own attributes. Use it when the routing key varies per request, as it does with baggage. To route by something fixed for the whole service, see [Route on a fixed attribute](#route-on-a-fixed-attribute-instead) below, which is cheaper.
- **`default_pipelines`** catches everything that matches no condition. Without it, unmatched spans are dropped. Sending them to an internal project makes missing data visible rather than silent.
- **`error_mode: ignore`** keeps a span whose attribute is absent or the wrong type flowing to the default pipeline instead of failing the batch.
- **A pipeline per destination** means the connector groups spans before export, so each project receives one request per batch rather than a shared batch being filtered several times.

## Verify the split

Send one request per destination, then open each project's Live view. Every span you opened inside the baggage block should be in that customer's project, and nothing from that request should appear in another customer's.

One exception, and it is the expected one: if an instrumented web framework opened a server span before your code ran, that span has no routing key and lands in the default project. Seeing the request's own entry span there, with the rest of the trace in the right place, means the setup is working as described above, not that it is broken.

If you want to confirm the routing before pointing it at real projects, add a `debug` exporter to one of the pipelines and read the Collector's own output:

```yaml title="otel-collector-config.yaml"
exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces/internal:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/internal, debug]
```

An exporter only runs when a pipeline lists it, so adding `debug` under `exporters` alone prints nothing.

## Route on a fixed attribute instead

When the destination depends on the service rather than the request, route on a resource attribute. Resource attributes describe the process emitting the data, so `context: resource` evaluates once per batch instead of once per span:

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

connectors:
  routing:
    default_pipelines: [traces/internal]
    error_mode: ignore
    table:
      - context: resource
        condition: attributes["deployment.environment.name"] == "production"
        pipelines: [traces/production]
      - context: resource
        condition: attributes["deployment.environment.name"] == "staging"
        pipelines: [traces/staging]

exporters:
  otlphttp/internal:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_INTERNAL}"
  otlphttp/production:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_PRODUCTION}"
  otlphttp/staging:
    endpoint: "https://logfire-us.pydantic.dev"
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN_STAGING}"

service:
  pipelines:
    traces/in:
      receivers: [otlp]
      exporters: [routing]
    traces/production:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/production]
    traces/staging:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/staging]
    traces/internal:
      receivers: [routing]
      processors: [batch]
      exporters: [otlphttp/internal]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/internal]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/internal]
```

Set that attribute from the application with [`logfire.configure(environment=...)`](../environments.md) or the `OTEL_RESOURCE_ATTRIBUTES` environment variable. Resource attributes are evaluated per emitting process, so every span from one process goes to the same place. A trace crossing services whose values differ is still split across projects.

## Send the same data to two projects

If you want a copy in every project rather than a split, you do not need the routing connector. List several exporters on one pipeline:

```yaml title="otel-collector-config.yaml"
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlphttp/acme, otlphttp/globex]
```

The Logfire SDK can also do this on its own, without a Collector, by passing several tokens: `logfire.configure(token=[token_a, token_b])`. This is the usual way to run two projects in parallel while migrating between them.

## Troubleshoot routing

**One trace appears in two projects, and not just its entry span.** The routing key is reaching some spans and not others. Setting the attribute directly on one span covers that span alone; children are routed on their own and fall to the default project. Use `logfire.set_baggage()` for the request as a whole, and reserve the direct attribute for the one span that opened before your code ran.

**Every project rejects the data with a 401.** Check the ordinary causes first: a `LOGFIRE_TOKEN_*` variable that is unset in the Collector's environment resolves to an empty header, and a token only works against the region its project lives in.

If those are right and you run a Collector behind another Collector, the inner one strips the `Authorization` header. The receiving Collector has to set `include_metadata: true` on its receiver and forward the header with the `headers_setter` extension.

**Everything lands in the default project.** The condition never matched. Attribute values are compared exactly and are case sensitive, so `"Acme"` does not match `"acme"`. Add a `debug` exporter to the default pipeline and read the attributes the Collector actually received.

**Spans arrive with no `tenant` attribute.** The SDK adds baggage to spans through the `add_baggage_to_attributes` setting, which is on by default. Check that it has not been set to `False` in `logfire.configure()`, and that the work happens inside the `with logfire.set_baggage(...)` block rather than after it.

## Next steps

- [Scrub sensitive data in the Collector](otel-collector-scrubbing.md) to apply one set of redaction rules to every project you route to.
- [Back up data in AWS S3](s3-backup.md) to keep a copy of the raw data beyond Logfire's retention window.
- [Baggage](../../reference/advanced/baggage.md) for what else you can carry along a request.
