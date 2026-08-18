---
title: "Migrate from New Relic to Logfire"
description: "New Relic accepts OTLP directly, so migrating to Logfire swaps the endpoint and the api-key header for Logfire's Authorization header."
---

# Migrate from New Relic

New Relic accepts OpenTelemetry data over OTLP — the OpenTelemetry Protocol — at `otlp.nr-data.net`, authenticated with an `api-key` header carrying your license key. Migrating to Logfire swaps the endpoint and that header — see [Migrate to Logfire](overview.md) for the general shape.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP

Point the SDK at Logfire and replace New Relic's `api-key` header with `Authorization`:

```sh
# before (New Relic):
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp.nr-data.net   # EU: otlp.eu01.nr-data.net · FedRAMP: gov-otlp.nr-data.net
#   OTEL_EXPORTER_OTLP_HEADERS='api-key=your-license-key'
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

New Relic recommends OTLP over HTTP (`http/protobuf`); keeping that protocol when you repoint is the simplest path. (Logfire's managed platform accepts both HTTP and gRPC.)

!!! note "Metric temporality"
    New Relic requires delta metric temporality, so you likely set `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=delta`. You can leave it — Logfire accepts delta (its own SDK uses delta for counters and histograms) — or drop the override to fall back to your SDK's default.

## If you run the OpenTelemetry Collector

Change the exporter's endpoint and header to Logfire's:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      # was: api-key: your-license-key
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

Keep both exporters in the pipeline to run in parallel during a cutover.

!!! note "HTTP or gRPC"
    Logfire's managed platform accepts OTLP over both HTTP and gRPC. These examples use HTTP, the most broadly supported option.

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Alternative clients](../how-to-guides/alternative-clients.md) — worked SDK examples
- New Relic's own docs, to confirm your current endpoint and header: [OpenTelemetry: OTLP](https://docs.newrelic.com/docs/opentelemetry/best-practices/opentelemetry-otlp/)
