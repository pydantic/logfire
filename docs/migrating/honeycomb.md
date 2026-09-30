---
title: "Migrate from Honeycomb to Logfire"
description: "Honeycomb is OpenTelemetry-native, so moving to Logfire is a one-line exporter change: swap the endpoint and the x-honeycomb-team header for Logfire's."
---

# Migrate from Honeycomb

Honeycomb is OpenTelemetry-native — you already send OpenTelemetry Protocol (OTLP) data, authenticated with the `x-honeycomb-team` header, to `api.honeycomb.io` (or `api.eu1.honeycomb.io` for EU). Migrating to Logfire swaps the endpoint and that header for Logfire's `Authorization` header. Nothing else changes; see [Migrate to Logfire](overview.md) for the general shape.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP

Point the SDK's OTLP variables at Logfire and replace the Honeycomb team header with `Authorization`:

```sh
# before (Honeycomb):
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io
#   OTEL_EXPORTER_OTLP_HEADERS='x-honeycomb-team=your-honeycomb-key'
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## If you run the OpenTelemetry Collector

Change the Honeycomb exporter's endpoint and header to Logfire's:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      # was: "x-honeycomb-team": "your-honeycomb-key"
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      exporters: [otlphttp/logfire]
    metrics:
      exporters: [otlphttp/logfire]
    logs:
      exporters: [otlphttp/logfire]
```

To cut over gradually, keep both exporters in the pipeline and compare the same traffic in each before removing Honeycomb.

!!! note "Datasets → SQL"
    Honeycomb groups data into datasets you query with its Query Builder. In Logfire everything lives in one project you query with SQL (PostgreSQL-compatible), so a saved Honeycomb query becomes a SQL statement. If your setup also sends an `x-honeycomb-dataset` header (required by Honeycomb Classic, and by metrics even in the Environments model), just drop it — Logfire routes everything into one project and doesn't use dataset headers.

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Alternative clients](../how-to-guides/alternative-clients.md) — worked SDK examples
- Honeycomb's own docs, to confirm your current endpoint and header: [Send Data with the OpenTelemetry Collector](https://docs.honeycomb.io/send-data/opentelemetry/collector)
