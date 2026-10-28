---
title: "Send Codex sessions to Logfire"
description: "Configure Codex's built-in OpenTelemetry support to see each Codex turn in Logfire: the prompt, the model, token usage, tool calls, and the final answer."
integration: otel
---

# Send Codex sessions to Logfire

See what Codex did in each turn: your prompt, the model it used, how many tokens it spent, which tools it called, and its final answer. Codex has built-in OpenTelemetry support, so you only change its configuration file. You do not need the Logfire SDK or a plugin.

Codex sends three kinds of data, called signals, over the OpenTelemetry Protocol (OTLP), the standard wire format Logfire receives:

| Signal | What Codex sends | Where you see it in Logfire |
| --- | --- | --- |
| Traces | A span (one operation, with a start and a duration) for each turn, with the model and token usage, plus a span for each tool call | Each turn appears as a **Codex** run in the [Agents view](../guides/web-ui/agents.md) |
| Logs | Events such as the prompt, each tool's arguments and output, and the final answer | [Live view](../guides/web-ui/live.md) and [SQL Workbench](../guides/web-ui/explore.md) |
| Metrics | Counts and timings, such as token usage, tool calls, and request durations | [Dashboards](../guides/web-ui/dashboards.md) and SQL Workbench |

For a single span per turn that renders as a conversation in Logfire's LLM panel, you can also add the [Logfire Exporter plugin](../how-to-guides/codex-logfire-exporter.md).

## Configure Codex

You need [Codex CLI](https://developers.openai.com/codex/cli) and a [write token](../how-to-guides/create-write-tokens.md). Create the token in your Logfire project under **Settings → Write tokens**. This configuration was checked with Codex CLI 0.163.

!!! warning "Review the data Codex sends"
    This configuration sends your prompts, Codex's answers, and each tool call's arguments and output preview to Logfire. Every log event also includes your OpenAI account email and account ID. The Logfire SDK's scrubbing, which hides sensitive values before sending them, does not process data that Codex sends directly. To send less, see [Choose what Codex sends](#choose-what-codex-sends).

Add these settings to `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` if you use a custom Codex home. Merge them into any existing `[otel]` configuration, and replace `<your-write-token>` in each exporter with your token:

```toml title="~/.codex/config.toml"
[otel]
# Shown as the deployment environment in Logfire.
environment = "codex-dev"
# Send the prompt text. Set to false to send "[REDACTED]" in its place.
log_user_prompt = true
# Send Codex's final answer, up to 64 KiB. Requires the log exporter below.
log_agent_responses = true

# Logs: prompts, final answers, tool arguments and output previews, request timings.
[otel.exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/logs"
protocol = "binary"
headers = { Authorization = "<your-write-token>" }

# Traces: one span per turn with the model and token usage, and a span per tool call.
# Required for the Agents view.
[otel.trace_exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/traces"
protocol = "binary"
headers = { Authorization = "<your-write-token>" }

# Metrics: token usage, tool calls, and latency.
[otel.metrics_exporter.otlp-http]
endpoint = "https://logfire-us.pydantic.dev/v1/metrics"
protocol = "binary"
headers = { Authorization = "<your-write-token>" }
```

For an EU project, replace `logfire-us.pydantic.dev` with `logfire-eu.pydantic.dev` in each endpoint. Keep the `/v1/logs`, `/v1/traces`, and `/v1/metrics` paths: Codex sends to the configured URL without appending a path. `protocol = "binary"` means Protocol Buffers over HTTP, which standard OpenTelemetry configuration calls `http/protobuf`.

Logfire expects the token directly, without a `Bearer` prefix. Codex does not expand variables such as `${LOGFIRE_TOKEN}` in `headers`, so paste the token itself.

!!! warning "The token is stored in `config.toml`"
    Anyone who can read `config.toml` can send data to your project. Restrict the file to your user with `chmod 600 ~/.codex/config.toml`, and do not commit it to a repository. The token is in the file because the Codex desktop app, the IDE extension, and Codex's background process do not reliably read your shell's environment variables.

Then restart Codex's background process and start Codex:

```bash
codex app-server daemon restart
codex
```

!!! note "Restart after every change"
    The terminal `codex` command does not run your turns itself. It starts a background process, the Codex app server, and reuses it for later sessions. That process reads `config.toml` only when it starts. If it was already running, it keeps sending with the old settings. Run `codex app-server daemon restart` after you change `config.toml`. Restart the desktop app or IDE extension too.

### Which Codex process sends the data

| How you run Codex | Process that runs your turns | `service_name` in Logfire |
| --- | --- | --- |
| `codex` in a terminal | The background app server | `codex-app-server` for turns, tools, and logs. The terminal process also sends a few `fs.*` spans as `codex_cli_rs`. |
| `codex --no-daemon` | The terminal process | `codex_cli_rs` |
| `codex exec` | The `exec` process | `codex_exec` |
| Codex desktop app or IDE extension | The app server | `codex-app-server` |

The app server reads `~/.codex/config.toml`, or `$CODEX_HOME/config.toml` if `CODEX_HOME` is set in its environment.

## Verify

Start a new Codex session in a terminal, ask it to run a command, and wait for the answer. Then:

1. Open the [Agents view](../guides/web-ui/agents.md). A **Codex** agent appears with one run per turn. Each run shows the model and token usage.
2. In the [Live view](../guides/web-ui/live.md), search for `codex.user_prompt`, `codex.tool_result`, or `codex.agent_response` events. Inspect `conversation.id` to group events from the same session.

To check metrics, run this in [SQL Workbench](../guides/web-ui/explore.md) with a time range that includes your session:

```sql
SELECT DISTINCT service_name, metric_name
FROM metrics
WHERE metric_name LIKE 'codex.%'
ORDER BY service_name, metric_name
```

You should see metrics such as `codex.api_request`, `codex.turn.token_usage`, and `codex.tool.call`. Codex sends metrics every 60 seconds and when it exits.

## Choose what Codex sends

Each signal is configured independently. Remove or comment out an exporter table to stop sending that signal.

| Setting | Effect |
| --- | --- |
| `log_user_prompt = false` | Codex sends `[REDACTED]` in place of the prompt text. |
| `log_agent_responses = false` (the default) | Codex does not send its final answer. |
| `[otel.tool_result] max_bytes = <n>` | Sets the size of the tool output preview in `codex.tool_result` events. The default is 2048 bytes. Tool arguments are always sent. |
| `span_attributes = { "team" = "platform" }` | Adds these attributes to every span, for example to filter by team. |
| Remove `[otel.trace_exporter.otlp-http]` | Stops sending traces. Logs and metrics still arrive, but Codex turns no longer appear in the Agents view. |

!!! note "Data volume"
    Codex can produce hundreds of records per turn, and they count toward your Logfire usage. To send less, remove an exporter or turn off prompt logging.

`[analytics] enabled = false` does not affect the exporters on this page. It only turns off Codex's own analytics.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Only `fs.read_file` and `fs.get_metadata` spans from `codex_cli_rs` arrive | The background app server started before you configured telemetry. Run `codex app-server daemon restart`, then start a new session. |
| Authentication fails or no data arrives | Use the full signal-specific path and the regional host that matches your project. Check that each exporter has a `headers` entry with a valid write token, without `Bearer` and without a literal `${...}`. |
| No Codex runs in the Agents view | Check that `[otel.trace_exporter.otlp-http]` is configured. Turns from `codex exec` and `codex --no-daemon` do not appear in the Agents view yet; their logs and metrics still arrive. |
| Prompt shows `[REDACTED]` or answers are missing | Set `log_user_prompt = true` and `log_agent_responses = true`, then restart the app server. |
| A recent event or measurement is missing | Codex sends data in batches. Complete a turn and wait a minute, or exit Codex normally to flush pending data. |
| A "Hooks need review" prompt appears when Codex starts | This prompt comes from an installed plugin with hooks, such as the Logfire Exporter plugin. It does not affect the configuration on this page. |

See [Codex's telemetry documentation](https://developers.openai.com/codex/config-advanced#observability-and-telemetry) for its event catalog and [configuration reference](https://developers.openai.com/codex/config-reference) for all settings. Use [dashboard queries](../how-to-guides/write-dashboard-queries.md#working-with-metrics) to chart the metrics you receive.
