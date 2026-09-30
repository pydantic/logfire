---
title: "Migrate from Datadog to Logfire"
description: "Move your OpenTelemetry traces, metrics, and logs from Datadog to Logfire by repointing the exporter — whether you send OTLP to the Datadog Agent or run the Datadog Distribution of the OpenTelemetry Collector."
---

# Migrate from Datadog

Datadog ingests OpenTelemetry (OTel) two ways: OTel SDKs that export to the **Datadog Agent's** OpenTelemetry Protocol (OTLP) intake, or the **Datadog Distribution of the OpenTelemetry Collector** (DDOT) with the `datadog` exporter. In both cases your instrumentation is standard OpenTelemetry, so moving to Logfire is an exporter change — see [Migrate to Logfire](overview.md) for the general shape.

!!! note "If you use `dd-trace` libraries"
    Datadog's tracing libraries (`dd-trace-py`, `dd-trace-js`, …) are proprietary, not OpenTelemetry. If your apps are instrumented with those rather than OTel, adopt OpenTelemetry instrumentation first; from then on this guide applies. Anything already emitting OTLP just needs repointing.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP to the Datadog Agent

You were pointing the OpenTelemetry SDK at the Agent's OTLP receiver (usually `http://localhost:4317`/`:4318`), or straight at Datadog's Direct OTLP Ingest endpoint. Either way, point it at Logfire instead — no agent in the middle:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## If you run a Collector with the `datadog` exporter (DDOT or upstream)

Replace the `datadog` exporter with an `otlphttp` exporter that targets Logfire, and reference it from each pipeline. Receivers and processors stay as they are.

```yaml
exporters:
  # remove (or keep alongside during cutover):
  # datadog:
  #   api:
  #     site: datadoghq.com  # yours may differ: datadoghq.eu, us5.datadoghq.com, etc.
  #     key: ${env:DD_API_KEY}
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
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

To run both during a cutover, list both exporters (`[datadog, otlphttp/logfire]`) and compare the same traffic in each backend before dropping Datadog.

!!! note "HTTP or gRPC"
    Logfire's managed platform accepts OTLP over both HTTP and gRPC. These examples use HTTP, the most broadly supported option.

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds. If not, re-check the write token and region.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Alternative clients](../how-to-guides/alternative-clients.md) — worked SDK examples
- [Logfire vs Datadog](https://pydantic.dev/logfire/vs-datadog) — how the platforms compare
- Datadog's own docs, to confirm your current setup: [OpenTelemetry Collector & the Datadog exporter](https://docs.datadoghq.com/opentelemetry/setup/collector_exporter/)
