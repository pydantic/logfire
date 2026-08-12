---
title: "Send Open WebUI telemetry to Logfire"
description: "Send Open WebUI traces, metrics, and logs to Pydantic Logfire through an OpenTelemetry Collector."
integration: otel
---

# Send Open WebUI telemetry to Logfire

See Open WebUI HTTP requests, database and cache calls, metrics, and logs in Logfire. A trace is the full journey of one request, made of one or more spans. A span is one unit of work: a single operation, with a name, a start, and a duration. A metric is a number tracked over time, like requests per second or CPU load. A log is a timestamped record of a single event.

Open WebUI sends this data using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. Its documented authentication settings support Basic authentication rather than Logfire's write-token header, so this setup uses an OpenTelemetry Collector to add that header.

The [OpenTelemetry Collector](../../how-to-guides/otel-collector/otel-collector-overview.md) is a separate program that sits between Open WebUI and Logfire, gathering telemetry and forwarding it. This route requires access to Open WebUI's runtime configuration. The official Docker images include the OpenTelemetry dependencies. A source or `pip` installation may need the optional OpenTelemetry packages described in the vendor documentation.

!!! warning "Review request, database, and log data"
    Open WebUI traces can contain request URLs, database statements, and Redis commands. Its logs can contain application data. The Logfire SDK's scrubbing feature does not process telemetry sent through this route. Use [Collector scrubbing](../../how-to-guides/otel-collector/otel-collector-scrubbing.md) when you need to remove sensitive values before they reach Logfire.

## Configure Open WebUI

Set these values using the address of a Collector that Open WebUI can reach:

```dotenv
ENABLE_OTEL=true
ENABLE_OTEL_TRACES=true
ENABLE_OTEL_METRICS=true
ENABLE_OTEL_LOGS=true
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_METRICS_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_LOGS_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
OTEL_EXPORTER_OTLP_INSECURE=true
OTEL_SERVICE_NAME=open-webui
OTEL_METRICS_EXPORT_INTERVAL_MILLIS=60000
```

Replace `otel-collector` if the Collector has a different hostname. Restart Open WebUI after applying the environment.

## Configure the Collector

Create a [project write token](../../how-to-guides/create-write-tokens.md), expose the Collector's OTLP receiver using Open WebUI's default gRPC transport, and forward all three signals to Logfire over OTLP using HTTP:

```yaml title="otel-collector-config.yaml"
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch: {}

exporters:
  otlphttp/logfire:
    endpoint: https://logfire-us.pydantic.dev
    headers:
      Authorization: "Bearer ${env:LOGFIRE_TOKEN}"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/logfire]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/logfire]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlphttp/logfire]
```

Set `LOGFIRE_TOKEN` in the Collector environment. For an EU project, change the Logfire endpoint to `https://logfire-eu.pydantic.dev`. Keep port `4317` private to the network shared by Open WebUI and the Collector.

## Verify

Send a chat message, then open the [Live view](../../guides/web-ui/live.md) and filter for `service_name = 'open-webui'`. Metrics can take a minute or two to appear in [Metrics](../../guides/web-ui/metrics-explorer.md).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Open WebUI reports a connection error | Confirm it can resolve `otel-collector` and reach the Collector's gRPC port `4317`. |
| Traces arrive but metrics or logs do not | Confirm each signal has its own endpoint variable and a matching Collector pipeline. |
| Collector cannot send to Logfire | Check `LOGFIRE_TOKEN`, the regional URL, and the Collector's outbound network access. |
| A source installation cannot start telemetry | Install the OpenTelemetry dependencies listed in Open WebUI's monitoring documentation. |

See [Open WebUI OpenTelemetry monitoring](https://docs.openwebui.com/reference/monitoring/otel/) for its signal coverage, dependencies, and environment variables.
