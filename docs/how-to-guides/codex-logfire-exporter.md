---
title: Export Codex Activity to Logfire
description: Install the Logfire Exporter plugin to send completed Codex turns and tool calls to Logfire as OpenTelemetry traces.
---

# Export Codex Activity to Logfire

The **Logfire Exporter** plugin sends Codex's own activity telemetry to Logfire. It is separate from the
main [Logfire plugin](skills.md#codex), which gives Codex skills and MCP access for instrumenting applications
and querying existing telemetry.

| Plugin | Purpose |
| --- | --- |
| **Logfire** | Helps Codex instrument your code, query Logfire data, and open Logfire UI views. |
| **Logfire Exporter** | Exports Codex turns and tool calls to Logfire. |

The two plugins solve different problems and can be installed together.

## Install

Add the Pydantic marketplace and enable the exporter plugin:

```bash
codex plugin marketplace add pydantic/skills --ref main
codex plugin add logfire-exporter@pydantic-skills
```

You can also enable **Logfire Exporter** from the **Pydantic** marketplace in the Codex plugin UI.

After enabling the plugin:

1. Restart Codex so hook configuration is loaded.
2. Run `/hooks` if Codex asks you to review or trust the plugin hooks.
3. Complete a new Codex turn — the exporter sends telemetry when the turn finishes.

## Configure

Create a config file at:

```text
${XDG_CONFIG_HOME:-~/.config}/logfire-exporter/config.env
```

Example for Logfire Cloud:

```dotenv
LOGFIRE_TOKEN=<your Logfire write token>
LOGFIRE_BASE_URL=https://logfire-us.pydantic.dev
```

Use `https://logfire-eu.pydantic.dev` instead if your data is in the EU region.

For a local Logfire instance:

```dotenv
LOGFIRE_TOKEN=test-e2e-write-token
LOGFIRE_BASE_URL=http://localhost:3000
CODEX_LOGFIRE_DEBUG=true
```

`LOGFIRE_URL` is still accepted as a compatibility alias, but `LOGFIRE_BASE_URL` takes precedence.

The exporter sends `Authorization: <LOGFIRE_TOKEN>`, matching Logfire's direct OTLP client configuration. If you
need a scheme-prefixed header, set `CODEX_LOGFIRE_AUTH_SCHEME=Bearer`.

!!! note
    Do not put tokens in URLs, command examples, or query strings. Keep credentials in `config.env` only.

## How It Works

The exporter registers Codex lifecycle hooks:

| Hook | Purpose |
| --- | --- |
| `SessionStart` | Initialize local telemetry state |
| `UserPromptSubmit` | Store the submitted prompt and turn metadata |
| `PostToolUse` | Store tool-call results for export as child spans |
| `Stop` | Export the completed turn and its tool spans to Logfire |

### Export boundary

Only completed turns are exported. The exporter sends telemetry on the `Stop` hook — it does not live-stream every
Codex action. Interrupted turns that never reach `Stop` are not exported.

### Trace model

There is no long-lived session root span. Codex hooks do not provide a reliable session-end event, so the exporter
deliberately avoids a session-level trace.

Instead, each completed turn becomes a root-level span in a deterministic conversation trace. Tool calls appear as
child spans of that turn span. Spans for the same Codex conversation share a stable trace ID derived from Codex
conversation metadata.

## Content Capture

Content capture controls whether prompt text, assistant text, tool inputs, tool outputs, and tool errors are
included in exported span attributes. By default, the exporter uses `CODEX_LOGFIRE_CONTENT_CAPTURE_MODE=full`,
which includes redacted content for all of those fields.

For sensitive projects, set a narrower mode in `config.env`:

```dotenv
CODEX_LOGFIRE_CONTENT_CAPTURE_MODE=metadata_only
```

Available modes:

| Mode | Captures |
| --- | --- |
| `full` | Redacted user prompt, final assistant message, tool input/output, and tool errors (default). |
| `no_tool_content` | Redacted user prompt and final assistant message, but not tool input/output. |
| `metadata_only` | No prompt, assistant, tool input, or tool output content. |

When content capture is enabled, spans include `pydantic_ai.all_messages`, the Pydantic AI message-schema attribute
that lets Logfire show Codex turns in the generic LLM conversation details panel.

## Troubleshooting

Debug logs are written to:

```text
${XDG_STATE_HOME:-~/.local/state}/logfire-exporter/logs/
```

If no spans appear after a completed Codex turn, check the Codex TUI log:

```bash
rg -n "logfire-exporter|failed to load plugin" ~/.codex/log/codex-tui.log
```

Common issues:

- **No spans after a turn** — confirm `LOGFIRE_TOKEN` is set in `config.env` and the turn completed normally (reached `Stop`).
- **Hooks not trusted** — run `/hooks` in Codex and approve the exporter hooks.
- **Stale plugin state** — restart Codex or start a new conversation after changing plugin configuration.

## See also

- [Coding Agent Skills](skills.md) — install the Logfire plugin and other Pydantic skills.
- [Connect to MCP Server](mcp-server.md) — configure Logfire MCP access through the Logfire plugin.
- Source repository: [github.com/pydantic/skills](https://github.com/pydantic/skills)
