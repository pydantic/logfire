---
title: "Migrate from Dynatrace to Logfire"
description: "Dynatrace exposes a native OTLP endpoint and ships its own Collector distribution — repoint either at Logfire with an exporter change."
---

# Migrate from Dynatrace

Dynatrace has a native OTLP HTTP endpoint (`https://<your-env>.live.dynatrace.com/api/v2/otlp`), authenticated with an `Authorization: Api-Token <token>` header, and ships the **Dynatrace Distribution of the OpenTelemetry Collector** (the Dynatrace OTel Collector). Both are standard OpenTelemetry, so migrating to Logfire is an exporter change — see [Migrate to Logfire](overview.md) for the general shape.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP

Point the SDK at Logfire and replace the Dynatrace API token with Logfire's write token:

```sh
# before (Dynatrace):
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://<env>.live.dynatrace.com/api/v2/otlp
#   OTEL_EXPORTER_OTLP_HEADERS='Authorization=Api-Token dt0c01.XXXX'
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## If you run the Dynatrace Collector

Replace the Dynatrace OTLP exporter with one that targets Logfire:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      # was: Authorization: "Api-Token dt0c01.XXXX"
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

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Alternative clients](../how-to-guides/alternative-clients.md) — worked SDK examples
- Dynatrace's own docs, to confirm your current endpoint and token: [Export with OTLP](https://docs.dynatrace.com/docs/ingest-from/opentelemetry/getting-started/otlp-export)
