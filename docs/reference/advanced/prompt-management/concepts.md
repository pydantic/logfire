---
title: "Prompt Management Concepts"
description: "The four objects in Logfire Prompt Management — prompts, versions, scenarios, and runs — and how they relate."
---

# Concepts

Everything in Prompt Management is built out of four objects. Learn them once and the rest of the UI becomes easy to read.

## The four nouns

### Prompt

A **prompt** is the unit you author and ship. It owns a human-readable name, a URL slug, and — through its versions — the current template text. A prompt also owns a single autosaved settings row (model, tools, API format, route, stream, model settings) that applies to *any* run you execute in the UI.

Example: a prompt named *"Welcome Email"* with slug `welcome-email`. One prompt per concept your application consumes.

### Version

A **version** is an immutable snapshot of a prompt's template text. Versions are numbered sequentially (v1, v2, v3, …) and recorded with the author and timestamp. You save a version when you want a stable point to promote, compare against, or roll back to.

!!! important "A version freezes the template — nothing else"
    Saving a version stores only the template string. Model, tools, API format, and other settings live in a separate autosaved row that is updated immediately on every edit. A run pinned to "v2" today and another pinned to "v2" next month will use v2's template but whatever settings are current at execution time.

    Each **run** does snapshot the settings that were live when it executed, so run history stays reproducible. See [Known limitations](./limitations.md) for how this affects rollback and version-diff behavior.

### Scenario

A **scenario** is a reusable input configuration for exercising a prompt. It is a named list of messages (system/user/assistant/tool, optionally with tool calls and tool returns) plus a set of variables that fill the template during a run.

Every prompt starts with a **default scenario** that contains a single system message whose content is the placeholder `@{prompt}@` — meaning *"render the prompt template here"*. You typically add user messages that describe a realistic request, then run the prompt against that scenario to see what the model produces.

### Run

A **run** is the record of executing a prompt against a scenario (or against a dataset of scenario inputs) through the configured model gateway. A run captures:

- the **template snapshot** used at execution time,
- the **rendered messages** sent to the model,
- the **model output** and any tool calls,
- **cost**, **latency**, and **token usage** from the gateway, and
- the effective **model settings** and **tools** at the moment of execution.

A run is either a **single** run (one scenario, one output) or a **batch** run (the scenario messages executed once per case in a linked dataset, up to 500 cases per batch call, executed with limited concurrency).

## Cardinalities

| Relationship | Multiplicity |
|---|---|
| Prompt → Versions | 1 : N |
| Prompt → Scenarios | 1 : N (at least one default scenario always exists) |
| Prompt → Runs | 1 : N |
| Run → Run cases | 1 : N (always 1 for single runs, ≤ 500 for batch runs) |

## Anatomy of a scenario

A scenario's messages use the same shape as modern chat APIs. This is what the editor and the server both consume:

```json
{
  "role": "system" | "user" | "assistant" | "tool",
  "parts": [
    { "part_kind": "text", "content": "..." },
    { "part_kind": "tool-call", "tool_name": "...", "tool_call_id": "...", "args": { ... } },
    { "part_kind": "tool-return", "tool_name": "...", "tool_call_id": "...", "content": ... }
  ]
}
```

Three part kinds exist:

- **`text`** — free-form message content. This is where you write user requests, assistant responses, or system instructions. Text parts are rendered through the template engine, so they can reference scenario variables with `{{variable}}` and can include `@{prompt}@` to inject the rendered prompt template.
- **`tool-call`** — what the assistant would have called. Contains the tool's `name`, an optional `tool_call_id` you can reuse to pair it with a return, and `args` as JSON. The args object is rendered recursively — any string field inside it supports the full template grammar.
- **`tool-return`** — the result your tool would have produced. Same structure: `tool_name`, optional `tool_call_id`, and a `content` value. The content is rendered recursively in the same way as `args`.

### A worked multi-turn example

Here is a scenario that exercises a prompt which is supposed to call a `fetch_weather` tool, then answer in natural language.

```text
Role: system
  Text:        @{prompt}@

Role: user
  Text:        What's the weather in {{city}} today?

Role: assistant
  Tool call:   tool_name = fetch_weather
               tool_call_id = call_001
               args = { "city": "{{city}}" }

Role: tool
  Tool return: tool_name = fetch_weather
               tool_call_id = call_001
               content = { "temp_c": 19, "conditions": "{{weather_summary}}" }

Role: user
  Text:        Thanks. Also, what should I wear?
```

The `system` message uses `@{prompt}@` to inject the prompt template (which itself is rendered against `{{city}}` and any other scenario variables first). The `user` text uses `{{city}}` directly, so you would define both `city` and `weather_summary` in the scenario's variables panel.

When you click **Run**, the backend renders this whole conversation, sends it to the configured model through the gateway, and records the response as a run.

## Identifiers you will see

Prompts carry three identifiers. You will encounter all of them.

| Identifier | Example | Where you see it |
|---|---|---|
| **Display name** | `Welcome Email` | Prompts list, page titles, search |
| **Slug** | `welcome-email` | URL path (`/prompts/welcome-email/`) |
| **Internal variable name** | `prompt__welcome_email` | SDK consumers (`logfire.var(name=...)`), Managed Variables list |

The internal name is derived from the slug by prefixing `prompt__` and converting hyphens to underscores. You only need to know about it if you are fetching the prompt from your application through the SDK, which today uses the generic `logfire.var(name=...)` call with the internal name. See [Known limitations](./limitations.md#sdk-callers-see-the-internal-name) for the tracking on a dedicated `logfire.prompt(slug=...)` helper that will hide this detail.

!!! tip "Slug rules"
    Slugs must be 1–100 characters, lowercase letters and digits only, hyphens allowed. The system derives an internal variable name by replacing hyphens with underscores, which means `order-confirmation` and `order_confirmation` would collide on the internal name. Pick one style per project.
