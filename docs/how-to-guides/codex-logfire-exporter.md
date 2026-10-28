---
title: Export Codex Activity to Logfire
description: Install the Logfire Exporter plugin to add one span per completed Codex turn, with the prompt and final answer, to Codex's built-in telemetry in Logfire.
---

# Export Codex Activity to Logfire

Read each Codex turn in Logfire as a conversation: your prompt and Codex's final answer, in Logfire's LLM panel and the **Codex** tab of the Live view. The **Logfire Exporter** plugin adds one span per completed turn to the data Codex already sends.

Start with [Send Codex sessions to Logfire](../integrations/codex.md). Codex's built-in telemetry provides the model, token usage, tool calls, and Agents view runs. The plugin does not send those. Add the plugin when you also want the conversation view.

The plugin is separate from the main [Logfire plugin](skills.md#codex), which gives Codex skills and MCP access for instrumenting applications and querying existing telemetry. The two plugins can be installed together.

| Plugin | Purpose |
| --- | --- |
| **Logfire** | Helps Codex instrument your code, query Logfire data, and open Logfire UI views. |
| **Logfire Exporter** | Exports one span per completed Codex turn to Logfire. |

## Install

Add the Pydantic marketplace and enable the exporter plugin:

```bash
codex plugin marketplace add pydantic/skills --ref main
codex plugin add logfire-exporter@pydantic-skills
```

You can also enable **Logfire Exporter** from the **Pydantic** marketplace in the Codex plugin UI.

## Configure

Create the configuration file. The path is the same on macOS and Linux:

```bash
mkdir -p ~/.config/logfire-exporter
cat > ~/.config/logfire-exporter/config.env <<'EOF'
LOGFIRE_TOKEN=<your Logfire write token>
LOGFIRE_BASE_URL=https://logfire-us.pydantic.dev
EOF
```

Replace `<your Logfire write token>` with a [write token](create-write-tokens.md) from your project's **Settings → Write tokens**. For an EU project, use `https://logfire-eu.pydantic.dev`. If you set `XDG_CONFIG_HOME`, the plugin reads `$XDG_CONFIG_HOME/logfire-exporter/config.env` instead.

!!! warning "Keep each value on its own line"
    Do not put a `#` comment after a value on the same line. The plugin reads the comment as part of the value, and an endpoint with a comment fails without an error message. Put comments on their own lines.

For a local Logfire instance:

```dotenv
LOGFIRE_TOKEN=test-e2e-write-token
LOGFIRE_BASE_URL=http://localhost:3000
CODEX_LOGFIRE_DEBUG=true
```

`LOGFIRE_URL` is still accepted as a compatibility alias, but `LOGFIRE_BASE_URL` takes precedence.

The exporter sends `Authorization: <LOGFIRE_TOKEN>`, matching Logfire's direct OTLP client configuration. If you need a scheme-prefixed header, set `CODEX_LOGFIRE_AUTH_SCHEME=Bearer`.

!!! note
    Do not put tokens in URLs, command examples, or query strings. Keep credentials in `config.env` only.

## Trust the plugin hooks

Codex runs a plugin's hooks only after you trust them. Until then, the plugin sends nothing, and Codex does not show an error.

1. Start `codex` in a terminal.
2. When Codex shows **Hooks need review**, select **Trust all and continue**. If Codex does not ask, run `/hooks` and trust the Logfire Exporter hooks.
3. Start a new session and complete a turn. The exporter sends telemetry when the turn finishes.

`codex exec` does not show the prompt and skips untrusted hooks. Trust the hooks in an interactive session first. For automation that already vets its hook sources, `codex exec --dangerously-bypass-hook-trust` runs the hooks without stored trust.

## Verify

After a turn completes, open the [Live view](../guides/web-ui/live.md) and search for `codex turn` spans from the `logfire-exporter` service. Select one and open the **Codex** tab to read the prompt and answer.

## How it works

The exporter registers two Codex lifecycle hooks:

| Hook | Purpose |
| --- | --- |
| `UserPromptSubmit` | Store the submitted prompt and turn metadata |
| `Stop` | Export the completed turn and the final answer to Logfire |

### Export boundary

Only completed turns are exported. The exporter sends telemetry on the `Stop` hook. It does not stream every Codex action. Interrupted turns that never reach `Stop` are not exported.

### Trace model

Each completed turn becomes one root-level `codex turn` span. Turns from the same Codex conversation share a stable trace ID derived from Codex conversation metadata. There is no long-lived session root span, because Codex hooks do not provide a reliable session-end event.

The plugin does not send tool calls or token usage. Codex's built-in telemetry sends those: see [Send Codex sessions to Logfire](../integrations/codex.md).

## Content capture

Content capture controls whether the prompt and the final answer are included in exported span attributes. By default, the exporter uses `CODEX_LOGFIRE_CONTENT_CAPTURE_MODE=no_tool_content`, which includes the redacted prompt and final answer.

For sensitive projects, set a narrower mode in `config.env`:

```dotenv
CODEX_LOGFIRE_CONTENT_CAPTURE_MODE=metadata_only
```

Available modes:

| Mode | Captures |
| --- | --- |
| `full` | Redacted prompt and final answer. Codex's built-in log events carry tool arguments and output. |
| `no_tool_content` | Redacted prompt and final answer (default). |
| `metadata_only` | No prompt or answer content. |

When content capture is enabled, spans include `pydantic_ai.all_messages`, the Pydantic AI message-schema attribute that lets Logfire show Codex turns in the [LLM panel](../guides/web-ui/llm-panels.md).

## Troubleshooting

Debug logs are written to:

```text
${XDG_STATE_HOME:-~/.local/state}/logfire-exporter/logs/
```

Set `CODEX_LOGFIRE_DEBUG=true` in `config.env` to record each hook run and export there.

| Symptom | Cause and fix |
| --- | --- |
| No spans and no debug log after a turn | The hooks are not trusted. Run `/hooks` in Codex and trust the Logfire Exporter hooks, then start a new session. |
| The debug log shows the hook ran, but no spans arrive | Check `config.env`: `LOGFIRE_TOKEN` is set, and no value has a `#` comment on the same line. |
| `config.env` cannot be created | The directory does not exist. Run `mkdir -p ~/.config/logfire-exporter`. |
| Changes have no effect | Restart Codex or start a new conversation after changing plugin configuration. |

If no debug log appears, check the Codex TUI log for plugin load errors:

```bash
rg -n "logfire-exporter|failed to load plugin" ~/.codex/log/codex-tui.log
```

## See also

- [Send Codex sessions to Logfire](../integrations/codex.md): Codex's built-in logs, traces, and metrics.
- [Coding Agent Skills](skills.md): install the Logfire plugin and other Pydantic skills.
- [Connect to MCP Server](mcp-server.md): configure Logfire MCP access through the Logfire plugin.
- Source repository: [github.com/pydantic/skills](https://github.com/pydantic/skills)
