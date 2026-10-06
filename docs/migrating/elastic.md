---
title: "Migrate from Elastic to Logfire"
description: "Repoint the Elastic Distributions of OpenTelemetry (EDOT) — or any OTLP exporter aimed at your Elastic OTLP endpoint — at Logfire."
---

# Migrate from Elastic

Elastic's observability is fed by OTLP, either through the **Elastic Distributions of OpenTelemetry** (EDOT — Elastic's Collector and SDK distributions) or by pointing OTel SDKs at the **Elastic Cloud Managed OTLP Endpoint** (mOTLP). Authentication uses an `Authorization: ApiKey <key>` header. Because it's standard OpenTelemetry, migrating to Logfire is an exporter change — see [Migrate to Logfire](overview.md) for the general shape.

!!! note "On an older Elastic Cloud APM deployment?"
    If your config points at `https://<deployment>.apm.<region>.cloud.es.io:443` with an `Authorization=Bearer <secret-token>` header (rather than the Managed OTLP Endpoint and `ApiKey`), the migration is identical — swap that endpoint and header for the two Logfire lines below.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If your apps export OTLP

Point the SDK at Logfire and replace Elastic's API key header with Logfire's write token:

```sh
# before (Elastic — copy your Managed OTLP Endpoint from Elastic Cloud; the
# API key from Kibana does not include the "ApiKey " scheme, so add it yourself):
#   OTEL_EXPORTER_OTLP_ENDPOINT=https://<your-managed-otlp-endpoint>
#   OTEL_EXPORTER_OTLP_HEADERS='Authorization=ApiKey your-elastic-api-key'
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

## If you run the EDOT Collector

Change the exporter's endpoint and header to Logfire's:

```yaml
exporters:
  otlphttp/logfire:
    endpoint: "https://logfire-us.pydantic.dev"  # or https://logfire-eu.pydantic.dev
    headers:
      # was: Authorization: "ApiKey your-elastic-api-key"
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
- Elastic's own docs, to confirm your current endpoint and header: [Elastic Cloud Managed OTLP Endpoint](https://www.elastic.co/docs/reference/opentelemetry/motlp)
