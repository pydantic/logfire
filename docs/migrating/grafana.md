---
title: "Migrate from Grafana Cloud to Logfire"
description: "Repoint Grafana Alloy — or any OTLP exporter aimed at Grafana Cloud's Tempo/Loki/Mimir — at Logfire, and query everything with SQL instead of three languages."
---

# Migrate from Grafana Cloud

Grafana Cloud's recommended pipeline is **Grafana Alloy**, Grafana's distribution of the OpenTelemetry Collector, exporting OTLP to the Grafana Cloud endpoint (Tempo for traces, Loki for logs, Mimir for metrics). Because that's standard OpenTelemetry, migrating to Logfire is an exporter change — see [Migrate to Logfire](overview.md) for the general shape.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP to Grafana Cloud

Grafana Cloud authenticates OTLP with HTTP Basic auth (`instanceID:token`). Point the SDK at Logfire and replace that with Logfire's `Authorization` header:

```sh
# before (Grafana Cloud — copy your exact values from the Grafana Cloud
# "OpenTelemetry" tile, which generates the endpoint and Basic-auth header):
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
#   OTEL_EXPORTER_OTLP_HEADERS='Authorization=Basic <base64 instanceID:token>'
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## If you run Grafana Alloy

Change the `otelcol.exporter.otlphttp` block's endpoint and auth to Logfire, and keep the rest of your pipeline. Alloy uses its own configuration syntax:

```hcl
otelcol.exporter.otlphttp "logfire" {
  client {
    endpoint = "https://logfire-us.pydantic.dev"  // or https://logfire-eu.pydantic.dev
    headers  = {
      "Authorization" = "Bearer " + sys.env("LOGFIRE_TOKEN"),
    }
  }
}
```

Then point your processors' `output` at `otelcol.exporter.otlphttp.logfire.input`. During a cutover you can send to both Grafana Cloud and Logfire from the same pipeline.

!!! note "Three query languages → one"
    Grafana uses PromQL, LogQL, and TraceQL — one per signal. Logfire queries traces, metrics, and logs together with SQL (PostgreSQL-compatible), so dashboards and alerts you rebuild in Logfire share a single query language.

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Logfire vs Grafana](https://pydantic.dev/logfire/vs-grafana) — how the platforms compare
- Grafana's own docs, to confirm your current endpoint and header: [Send data to the Grafana Cloud OTLP endpoint](https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/) and the [`otelcol.exporter.otlphttp`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlphttp/) Alloy component
