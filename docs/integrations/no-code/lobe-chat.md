---
title: "Send LobeChat telemetry to Logfire"
description: "Configure LobeChat to send request, AI, and tool telemetry to Pydantic Logfire."
integration: otel
---

# Send LobeChat telemetry to Logfire

See each LobeChat request as a trace (the full journey of one request, made of one or more spans) in Logfire. A span is one unit of work: a single operation, with a name, a start, and a duration. LobeChat traces cover HTTP requests, model calls, agent steps, tool calls, and database work. It also sends metrics (numbers tracked over time), including RPC duration and agent activity counts.

LobeChat sends this data using the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive telemetry. This setup is available where an administrator can configure the LobeChat runtime; it is not available in a hosted workspace that does not expose runtime settings.

## Configure LobeChat

Create a [project write token](../../how-to-guides/create-write-tokens.md), then set:

```dotenv
ENABLE_TELEMETRY=1
OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev
OTEL_EXPORTER_OTLP_HEADERS=Authorization=<your-write-token>
OTEL_METRICS_EXPORTER_INTERVAL=60000
```

For an EU project, use `https://logfire-eu.pydantic.dev`. LobeChat sends both signals over OTLP/HTTP and appends the signal paths to the base URL. It currently reports the service as `lobehub`.

The metrics interval is in milliseconds. LobeChat's default is one second; the example changes it to one minute, which sends one-sixtieth as many datapoints. Keep the interval at one minute unless you have a specific need for finer resolution.

For a non-production development build, also set `ENABLE_TELEMETRY_IN_DEV=1`. Restart LobeChat after applying the environment.

!!! warning "Tool data can leave the LobeChat runtime"
    LobeChat's agent spans can include tool arguments and results. Review this data before enabling telemetry for production traffic. The Logfire SDK's scrubbing feature does not process telemetry sent directly by LobeChat. If LobeChat cannot omit sensitive content before sending it, do not enable this route for conversations whose telemetry must be redacted.

## Verify

Send a chat message that calls a model or tool, then open the [Live view](../../guides/web-ui/live.md). Filter for `service_name = 'lobehub'`. Metrics can take a minute or two to appear in [Metrics](../../guides/web-ui/metrics-explorer.md).

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| No data arrives | Confirm `ENABLE_TELEMETRY=1`, the runtime is Node.js, and the endpoint is reachable from LobeChat. |
| Development emits no data | Add `ENABLE_TELEMETRY_IN_DEV=1`; non-production builds disable telemetry without it. |
| Authentication fails | Use `Authorization=<your-write-token>` without a `Bearer` prefix, and match the endpoint to the token's region. |
| The expected service name is missing | Search for `lobehub`, which is the service name set by LobeChat's current telemetry package. |

See LobeChat's [OpenTelemetry package](https://github.com/lobehub/lobe-chat/tree/main/packages/observability-otel) for the current implementation.
