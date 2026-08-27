---
title: "Send Flowise metrics to Logfire"
description: "Connect Flowise OpenTelemetry metrics to Pydantic Logfire through an OpenTelemetry Collector."
integration: otel
---

# Send Flowise metrics to Logfire

Track Flowise API, flow, and prediction metrics (numbers tracked over time, such as request counts and duration) in Logfire. Flowise sends these metrics using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. Its current OpenTelemetry support does not send detailed model or tool traces or Node.js process metrics.

This setup requires access to Flowise's runtime configuration and an [OpenTelemetry Collector](../../how-to-guides/otel-collector/otel-collector-overview.md). The Collector is a separate program that sits between Flowise and Logfire, gathering telemetry and forwarding it. It also adds the Logfire authorization header.

## Configure Flowise

Set these values in the Flowise environment:

```dotenv
ENABLE_METRICS=true
METRICS_PROVIDER=open_telemetry
METRICS_OPEN_TELEMETRY_METRIC_ENDPOINT=http://otel-collector:4318/v1/metrics
METRICS_OPEN_TELEMETRY_PROTOCOL=http
METRICS_OPEN_TELEMETRY_DEBUG=false
```

Replace `otel-collector` if the Collector has a different hostname. Restart Flowise after applying the environment.

!!! warning "Flowise exports metrics every five seconds"
    Flowise currently hard-codes a five-second interval in its OpenTelemetry metrics implementation and does not provide a setting to change it. This sends twelve times as many datapoints as the recommended 60-second interval. Monitor metric usage on busy instances and only enable this integration when you need its metrics. `METRICS_INCLUDE_NODE_METRICS` only affects Flowise's Prometheus provider, so it is intentionally omitted here.

## Configure the Collector

Create a [project write token](../../how-to-guides/create-write-tokens.md), expose the Collector's OTLP/HTTP receiver to Flowise, and forward metrics to Logfire:

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

exporters:
  otlphttp/logfire:
    endpoint: https://logfire-us.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/logfire]
```

Set `LOGFIRE_TOKEN` in the Collector's environment. For an EU project, use `https://logfire-eu.pydantic.dev`. Keep port `4318` private to the network shared by Flowise and the Collector.

## Verify

Run a flow, then open [Metrics](../../guides/web-ui/metrics-explorer.md) in Logfire. Filter for `service_name = 'FlowiseAI'` if needed. The first metric series can take a minute or two to appear.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| No metrics arrive | Confirm Flowise can resolve `otel-collector`, reach port `4318`, and has all the settings above. |
| Collector rejects the request | Confirm the receiver has an OTLP/HTTP protocol and that Flowise's endpoint ends in `/v1/metrics`. |
| Logfire returns `401` or `403` | Set the Collector's `LOGFIRE_TOKEN` to a write token from the project in the selected region. |
| Metrics appear but no traces do | This is expected. Flowise's documented OpenTelemetry integration currently exports metrics only. |

See [Flowise monitoring](https://docs.flowiseai.com/using-flowise/monitoring) for the vendor's OpenTelemetry settings.
