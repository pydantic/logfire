---
title: "Configure Tools for a Prompt"
description: "Define the tools a prompt can call during a Logfire run, including schema shape and where tool settings live in the data model."
---

# Configure tools

When you run a prompt through the Logfire gateway, the model can be offered a set of tools to call. You declare those tools on the prompt's settings panel. Tools are shared across every run of the prompt — they are not per-scenario and not per-version.

## Defining a tool

A tool definition has three fields:

| Field | Type | Notes |
|---|---|---|
| `name` | string | The tool's name as the model will see it. |
| `description` | string or null | Optional free-text description passed to the model. |
| `parameters` | JSON object | A JSON Schema describing the tool's arguments. |

The schema shape matches the standard tool-definition format used by modern chat APIs. For example:

```json
{
  "name": "fetch_weather",
  "description": "Look up the current weather for a city by name.",
  "parameters": {
    "type": "object",
    "properties": {
      "city": { "type": "string" },
      "units": { "type": "string", "enum": ["metric", "imperial"] }
    },
    "required": ["city"]
  }
}
```

During a run, the gateway advertises these tool definitions to the model. When the model responds with a tool call, the tool call is recorded on the run — it is *not* executed, because Prompt Management does not have access to your application code. Tool-calling behavior can be rehearsed in [scenarios](./scenarios.md), which provide both the tool call and the tool return on a turn-by-turn basis.

## What "autosaved" means for tools

Tools live in the prompt's **settings**, not in its **versions**. That has two consequences worth knowing:

- **Edits apply immediately.** Changing a tool's schema, adding a new tool, or removing one updates the live settings right away — no save-version step. The next run uses the new set.
- **Versions do not snapshot tools.** A version freezes only the prompt template. A run pinned to "v2" today and another pinned to "v2" after you edit a tool will use the same template but different tool definitions.

Each **run** does snapshot the tools that were active when it executed, so a run's history remains reproducible even after you change the tool configuration.

!!! note "Why tools are not versioned"
    Decoupling tools from template versions keeps the version concept focused on the prompt text — the field most authors iterate on day to day. The trade-off is that tool edits are a global action: there is no per-version tool pinning today. See [Known limitations](./limitations.md#versioning-is-template-only) for the broader discussion and roadmap.

## API format and model settings

Tools sit in the same settings row as the prompt's other execution parameters:

- **API format** — one of `openai-chat`, `openai-responses`, `anthropic`, `gemini`. Controls how the gateway talks to the underlying model provider.
- **Route** — an optional gateway route identifier if your project's gateway uses custom routes.
- **Model** — the model identifier your gateway should use (e.g. `gpt-5-mini`).
- **Model settings** — a free-form JSON bag of provider-specific parameters (temperature, max_tokens, etc.).
- **Stream** — whether runs should use the streaming Run endpoint or not.

All of these, like tools, are autosaved and shared by every run of the prompt.
