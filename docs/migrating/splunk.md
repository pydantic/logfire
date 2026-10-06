---
title: "Migrate from Splunk Observability Cloud to Logfire"
description: "Swap the Splunk Distribution of the OpenTelemetry Collector's sapm/signalfx exporters for an otlphttp exporter pointed at Logfire."
---

# Migrate from Splunk Observability Cloud

Splunk Observability Cloud is fed by the **Splunk Distribution of the OpenTelemetry Collector**, which exports through the `sapm` (traces) and `signalfx` (metrics) exporters — and often `splunk_hec` for logs — to a realm-based ingest endpoint, authenticated with an access token. Those are Splunk-specific exporters wrapped around standard OpenTelemetry data, so migrating to Logfire means swapping them for an `otlphttp` exporter — see [Migrate to Logfire](overview.md) for the general shape.

!!! note "Newer Splunk collectors already use `otlphttp`"
    Splunk now recommends `otlphttp` for traces; the `sapm` exporter is deprecated. If your collector already uses `otlphttp` with an `X-SF-Token` header, the change is even smaller — repoint the endpoint to Logfire and swap `X-SF-Token: <token>` for `Authorization: Bearer <token>`.

You'll need a Logfire [write token](../how-to-guides/create-write-tokens.md) and your [region](../reference/data-regions.md) endpoint (`https://logfire-us.pydantic.dev` or `-eu`).

## If you run the Splunk Collector

Replace the Splunk exporters with one that targets Logfire, and reference it from each pipeline. Your receivers and processors don't change.

```yaml
exporters:
  # remove (or keep alongside during cutover):
  # sapm:                      # traces
  #   access_token: "${env:SPLUNK_ACCESS_TOKEN}"
  #   endpoint: "https://ingest.<realm>.signalfx.com/v2/trace"
  # signalfx:                  # metrics
  #   access_token: "${env:SPLUNK_ACCESS_TOKEN}"
  #   realm: "<realm>"
  # splunk_hec:                # logs (and splunk_hec/profiling, if present)
  #   token: "${env:SPLUNK_HEC_TOKEN}"
  #   endpoint: "https://<splunk-host>:8088/services/collector"
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

!!! note "Don't forget logs"
    Splunk setups often send **logs** (and profiling) through a separate `splunk_hec` exporter rather than `sapm`/`signalfx`. Point the `logs` pipeline at `otlphttp/logfire` too — if a `splunk_hec` exporter stays wired into that pipeline, your logs keep flowing to Splunk.

## If your apps export OTLP

If your services export OpenTelemetry Protocol (OTLP) straight to the Splunk Collector's OTLP receiver, point the SDK at Logfire instead:

```sh
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
export OTEL_SERVICE_NAME=your-service-name
```

To cut over gradually, keep the Splunk exporters and add `otlphttp/logfire` alongside them, then compare the same traffic in each backend before removing Splunk.

## Verify

Run your workload and open the [Live view](../guides/web-ui/live.md). Traces should appear within seconds.

## See also

- [Migrate to Logfire](overview.md) — the general two-path pattern and parallel-run guidance
- [Alternative clients](../how-to-guides/alternative-clients.md) — worked SDK examples
- Splunk's own docs, to confirm your current exporters and token: [Splunk Distribution of the OpenTelemetry Collector](https://github.com/signalfx/splunk-otel-collector)
