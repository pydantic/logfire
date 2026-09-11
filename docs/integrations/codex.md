---
title: "Send Codex logs and metrics to Logfire"
description: "Configure Codex's built-in OpenTelemetry support to send session events, tool activity, and timing metrics to Logfire."
integration: otel
---

# Send Codex logs and metrics to Logfire

See Codex session events, tool results, and request timings in Logfire. Codex has built-in OpenTelemetry support for sending logs and metrics. A log is a timestamped record of a single event. A metric is a number tracked over time, such as a request count or duration.

Codex uses the OpenTelemetry Protocol (OTLP), the standard wire format Logfire uses to receive that data. You do not need the Logfire SDK or a plugin for this setup.

This guide covers Codex's native telemetry. For completed turns with tool calls grouped beneath them and conversation content in Logfire's LLM panel, use the [Logfire Exporter plugin](../how-to-guides/codex-logfire-exporter.md).

## Configure Codex

Install [Codex CLI](https://developers.openai.com/codex/cli) and create a [write token](../how-to-guides/create-write-tokens.md) in your Logfire project's **Settings → Write tokens**. The configuration below was checked with Codex CLI 0.153.2.

!!! warning "Review the data Codex sends"
    Enabling this configuration sends Codex activity to Logfire. `log_user_prompt = false` redacts user prompts, but other event fields can include tool output and identifying metadata. The Logfire SDK's scrubbing, which hides sensitive values before sending them, does not process data sent directly by Codex.

Add these settings to `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` if you use a custom Codex home. Merge them into any existing `[otel]` configuration:

```toml title="~/.codex/config.toml"
[otel]
environment = "codex-dev"
log_user_prompt = false

[otel.exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/logs"
protocol = "binary"

[otel.metrics_exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/metrics"
protocol = "binary"
```

For an EU project, replace `logfire-us.pydantic.dev` with `logfire-eu.pydantic.dev` in each endpoint. Keep the `/v1/logs` and `/v1/metrics` paths: Codex sends to the configured URL without appending a signal path.

Start Codex from a shell with the authorization header set:

```bash
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=<your-write-token>'
codex
```

Replace `<your-write-token>` with your token. Logfire expects the token directly, without a `Bearer` prefix. The environment variable supplies the header to both HTTP configurations and keeps the token out of `config.toml`. For a desktop or IDE client, the variable must be available to the process that starts Codex; restart that client after changing its environment.

!!! note "TOML headers are literal strings"
    Codex also accepts `headers = { "Authorization" = "<your-write-token>" }` inside each `otlp-http` table. It does not expand `${CODEX_LOGFIRE_WRITE_TOKEN}` there. Use the environment variable above to avoid sending that placeholder as your credential.

### Understand the signal settings

| Setting | Sends | Logfire HTTP path |
| --- | --- | --- |
| `otel.exporter` | Log events, such as conversation starts and tool results | `/v1/logs` |
| `otel.metrics_exporter` | Counts and timing measurements | `/v1/metrics` |
| `otel.trace_exporter` | Spans: individual operations with a name, start, and duration | `/v1/traces` |

Each setting is independent. Configuring `otel.exporter` does not enable metrics export to Logfire. Codex's `protocol = "binary"` means protobuf over HTTP, equivalent to `http/protobuf` in standard OpenTelemetry environment configuration.

### Include native traces

To also send Codex's native spans, add this table to the same file:

```toml
[otel.trace_exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/traces"
protocol = "binary"
```

Use the matching regional host. The same `OTEL_EXPORTER_OTLP_HEADERS` variable authenticates these requests.

## Verify

Start a new Codex session, complete a turn, then exit normally so Codex flushes pending data. In the [Live view](../guides/web-ui/live.md), look for events such as `codex.conversation_starts`, `codex.user_prompt`, or `codex.tool_result`. Inspect `conversation.id` to identify events from the same session. User prompt text should appear as `[REDACTED]`.

In [SQL Workbench](../guides/web-ui/explore.md), run:

```sql
SELECT DISTINCT service_name, metric_name
FROM metrics
WHERE metric_name LIKE 'codex.%'
ORDER BY service_name, metric_name
```

Select a time range that includes your session. You should see metrics such as `codex.api_request`, `codex.api_request.duration_ms`, and `codex.turn.e2e_duration_ms`. A `codex exec` run reports `service_name = 'codex_exec'`; other Codex clients can use different service names.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Requests fail or no data arrives | Use the full signal-specific path and the regional host that matches your project. Restart Codex after editing its configuration. |
| Authentication fails | Check that `OTEL_EXPORTER_OTLP_HEADERS` reaches the Codex process. Use a valid write token without `Bearer`, and remove any literal `${...}` header from the TOML configuration. |
| Logs arrive but metrics do not | Configure `otel.metrics_exporter` separately. `[analytics] enabled = false` disables metrics collection, including this export; remove that override or set it to `true` if you want metrics. This flag also controls Codex's built-in analytics. |
| A recent event or measurement is missing | Sending happens in batches. Complete a turn and exit normally to flush pending data. Tool metrics require a turn that actually calls a tool. |

See [Codex's telemetry documentation](https://developers.openai.com/codex/config-advanced#observability-and-telemetry) for its event catalog and [configuration reference](https://developers.openai.com/codex/config-reference) for supported settings. Use [dashboard queries](../how-to-guides/write-dashboard-queries.md#working-with-metrics) to chart the metrics you receive.
