---
title: "Send Langflow telemetry to Logfire"
description: "Configure Langflow's built-in tracing to send AI flow traces to Pydantic Logfire."
integration: otel
---

# Send Langflow telemetry to Logfire

See each Langflow run as a trace (the full journey of one flow run, made of one or more spans) in Logfire. A span is one unit of work: a single operation, with a name, a start, and a duration. The trace includes instrumented model and tool activity.

Langflow sends traces using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. This route requires an administrator who can set the Langflow service environment; it is not available in a hosted workspace that does not expose runtime settings.

## Configure Langflow

Create a [project write token](../../how-to-guides/create-write-tokens.md), then set:

```dotenv
TRACELOOP_API_KEY=<your-write-token>
TRACELOOP_BASE_URL=https://logfire-us.pydantic.dev
OTEL_EXPORTER_OTLP_INSECURE=false
```

For an EU project, use `https://logfire-eu.pydantic.dev`. Langflow requires `TRACELOOP_API_KEY` to initialize its tracing integration. The instrumentation sends that value as a Bearer authorization token, and appends `/v1/traces` to `TRACELOOP_BASE_URL`.

Do not also set `TRACELOOP_HEADERS`: when present, it takes precedence over `TRACELOOP_API_KEY` in the underlying instrumentation library.

!!! warning "Review captured flow content"
    Langflow records flow inputs, outputs, and logs on spans. Review the data before enabling tracing for production traffic. The Logfire SDK's scrubbing feature does not process telemetry sent directly by Langflow. If Langflow cannot omit sensitive content before sending it, do not enable this route for flows whose telemetry must be redacted.

Restart Langflow after applying the environment.

## Verify

Run a flow, then open the [Live view](../../guides/web-ui/live.md). You should see a root Langflow span with child spans for instrumented components.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| No traces arrive | Confirm `TRACELOOP_API_KEY` is non-empty and Langflow can reach the regional URL. |
| Requests go to the wrong path | Supply the Logfire base URL without `/v1/traces`; the instrumentation appends the path. |
| Authentication fails | Replace `TRACELOOP_API_KEY` with a valid write token and remove any conflicting `TRACELOOP_HEADERS`. |

See [Langflow's Traceloop integration](https://docs.langflow.org/integrations-instana-traceloop) and [Traceloop configuration](https://www.traceloop.com/docs/openllmetry/configuration) for the vendor settings used by this route.
