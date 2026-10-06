---
title: "Send Dify telemetry to Logfire"
description: "Configure Dify's OpenTelemetry support to send application and workflow traces and metrics to Pydantic Logfire."
integration: otel
---

# Send Dify telemetry to Logfire

See each Dify application or workflow run as a trace (the full journey of one request or workflow run, made of one or more spans) in Logfire. A span is one unit of work: a single operation, with a name, a start, and a duration. Dify also sends metrics (numbers tracked over time), including HTTP response counts by method, route, and status.

Dify sends this data using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. This direct route is available when an administrator can configure the Dify API and worker runtime. A hosted plan that does not expose runtime settings cannot use this route.

## Configure Dify

Create a [project write token](../../how-to-guides/create-write-tokens.md), then set these values for the Dify API and worker services:

```dotenv
ENABLE_OTEL=true
OTLP_BASE_ENDPOINT=https://logfire-us.pydantic.dev
OTLP_API_KEY=<your-write-token>
OTEL_EXPORTER_TYPE=otlp
OTEL_EXPORTER_OTLP_PROTOCOL=http
OTEL_METRIC_EXPORT_INTERVAL=60000
OTEL_SAMPLING_RATE=1.0
```

For an EU project, use `https://logfire-eu.pydantic.dev`. Leave `OTLP_TRACE_ENDPOINT` and `OTLP_METRIC_ENDPOINT` unset when using the base URL. Dify appends `/v1/traces` and `/v1/metrics`, and sends `OTLP_API_KEY` as a Bearer authorization token.

`OTEL_SAMPLING_RATE=1.0` records every eligible trace and is useful while verifying the connection. Lower it after considering traffic volume and cost.

`OTEL_METRIC_EXPORT_INTERVAL` is in milliseconds. Dify defaults to 60,000 (one minute); setting it makes the intended interval explicit in your deployment. Keep it at one minute unless you have a specific need for finer resolution.

!!! warning "Review captured data"
    Current Dify spans can contain user, tenant, application, and workflow identifiers, plus database and outbound-request metadata. Review this data before enabling production traffic. The Logfire SDK's scrubbing feature does not process telemetry sent directly by Dify. If Dify cannot omit sensitive content before sending it, do not enable this route for workflows whose telemetry must be redacted.

Restart the API and worker services after applying the environment.

## Verify

Run an application or workflow, then open the [Live view](../../guides/web-ui/live.md). You should see Dify spans. Metrics can take a minute or two to appear in [Metrics](../../guides/web-ui/metrics-explorer.md).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| No data arrives | Confirm the settings are available to both the API and worker services and check their logs for errors sending telemetry. |
| Requests use a duplicated signal path | Set only `OTLP_BASE_ENDPOINT`; do not include `/v1/traces` or `/v1/metrics` in it. |
| Logfire returns `401` or `403` | Replace `OTLP_API_KEY` with a valid write token from the project in the selected region. |
| Too few traces arrive | Dify samples traces. Keep `OTEL_SAMPLING_RATE=1.0` while verifying the connection. |

See Dify's current [OpenTelemetry configuration](https://github.com/langgenius/dify/blob/main/api/configs/observability/otel/otel_config.py) and [OpenTelemetry implementation](https://github.com/langgenius/dify/blob/main/api/extensions/ext_otel.py) for the settings and endpoint behavior.
