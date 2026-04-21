---
title: "Define Scenarios"
description: "How to build scenarios — the reusable inputs that exercise a prompt — including multi-turn conversations and tool-calling flows."
---

# Define scenarios

A scenario is how you rehearse a prompt. Each scenario is a sequence of messages plus a set of variables. When you click **Run**, Logfire uses the scenario to build a realistic conversation, renders the prompt template into it, and sends the whole thing to the configured model through the gateway.

## The default scenario

Every new prompt starts with a **default scenario** containing a single message:

- Role: `system`
- Content: `@{prompt}@`

That one message is what turns the prompt template into a real system prompt during a run. If you never add another scenario and never change the default, the run will execute with just the prompt as system message and no user input — useful when your prompt is the whole instruction (for example, for a structured-output extractor).

For any realistic iteration you will want to add at least one `user` message that describes a representative request.

## Adding messages

Use the scenario editor to append messages of four possible roles. Each message is a list of **parts** — most scenarios only need a single `text` part per message, but tool-calling conversations need a mix.

### Text messages

The common case. Add a message, pick the role, and write the content. Content is a template — you can reference scenario variables with `{{variable}}` and, in any message, insert the rendered prompt with `@{prompt}@`.

```text
Role: system
  Text: @{prompt}@

Role: user
  Text: I am having trouble with {{topic}}. Can you help?
```

### Message roles

| Role | When to use |
|---|---|
| `system` | Static instructions the model should treat as non-user input. Usually contains `@{prompt}@`. |
| `user` | The end-user's input. This is typically where your scenario variables live. |
| `assistant` | A prior response from the model. Use for seeding multi-turn state, few-shot examples, or replaying prior tool calls. |
| `tool` | A tool's return value. Pairs with a prior `assistant` message that contained a tool call. |

## Scenario variables

The variables panel sits alongside the editor. Each variable has a name and a value. Two styles:

- **Plain** — `customer_name = Taylor`. Reachable as `{{customer_name}}` in templates.
- **Dotted** — `customer.name = Taylor`, `customer.tier = gold`. Unpacked into a nested object; reachable as `{{customer.name}}` and `{{customer.tier}}`.

The editor lists the variables the template and scenario messages reference — a quick visual sanity check that your names match.

!!! tip "Use scenarios, not hard-coded strings"
    It is tempting to write a scenario like *"What's the weather in Amsterdam today?"* with the city hard-coded. Prefer *"What's the weather in {{city}} today?"* with `city = Amsterdam` in the variables panel. When you later link the scenario to a dataset for a [batch run](#batch-runs), the variable column becomes the axis of evaluation — the hard-coded version cannot be swept over a dataset.

## Tool-calling conversations

Scenarios represent a tool-calling exchange using two part kinds: `tool-call` on an `assistant` message, and `tool-return` on a `tool` message. The two are paired by a shared `tool_call_id`.

```text
Role: assistant
  Tool call:
    tool_name    = fetch_weather
    tool_call_id = call_001
    args         = { "city": "{{city}}" }

Role: tool
  Tool return:
    tool_name    = fetch_weather
    tool_call_id = call_001
    content      = { "temp_c": 19, "conditions": "{{weather_summary}}" }
```

Both `args` (on `tool-call`) and `content` (on `tool-return`) are JSON values. String fields anywhere inside them are rendered through the template engine — including nested strings inside arrays and objects. Non-string values (numbers, booleans, nulls) pass through unchanged.

The tools your assistant is allowed to call during a run are configured separately — see [Tools](./tools.md). Scenarios only describe what tool calls and returns *look like*; they do not change what the model is permitted to do.

## Multiple scenarios on a prompt

A prompt can have as many scenarios as you want. Use them to capture distinct intents: a short question, a long ambiguous request, a tool-heavy flow, an edge case. Running the prompt against several scenarios is the standard way to spot that a template change helps one intent but regresses another.

Scenarios have a position — they render in the editor in the order you arrange them — and one is marked as the **default**. The default is the scenario that runs when you click Run without explicitly picking a scenario first.

## Batch runs

A scenario can be linked to a **dataset** for a batch run. In that mode, Logfire iterates over every case in the dataset (up to 500 per batch call), maps dataset columns to the scenario's variables, and executes the scenario once per case. Each case produces its own rendered messages, its own model output, and its own cost/latency numbers, all queryable under the single batch run record.

!!! warning "Cost"
    A batch run calls the gateway once per case. Before running 500 cases against a paid model, double-check the scenario and confirm the model/settings you want. See [Known limitations](./limitations.md#no-batch-cost-ceiling) — there is currently no cost ceiling or approval flow for batch runs; every run spends real gateway budget.

## Seeing what the model actually sees

Both the editor preview and every run record surface the **rendered messages** — the concrete JSON that gets sent to the model after all template rendering. When a scenario behaves in a surprising way, the rendered messages are the first thing to check: you can compare what you wrote against what the engine produced.
