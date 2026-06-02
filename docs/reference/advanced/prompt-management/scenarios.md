---
title: "Test Prompts"
description: "How to test prompts with scenarios, datasets, and run records."
---

# Test Prompts

Prompt Management includes a testing surface around the prompt template itself:

- **Scenarios** are saved test cases.
- **Datasets** let you run the same scenario across many cases.
- **Runs** are the records you inspect afterward to see what happened.

These are for testing and evaluation. They are not part of the runtime surface your application consumes.

## Scenarios

A scenario is a saved test case for a prompt. Each scenario is a sequence of messages plus a set of variables. When you click **Run**, Logfire uses the scenario to build a realistic conversation, renders the prompt template into it, and sends the whole thing to the configured model through the gateway.

Scenarios are most useful when you want repeatable testing in the prompt editor: representative user inputs, few-shot or multi-turn setup, or tool-calling rehearsal.

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
    It is tempting to write a scenario like *"What's the weather in Amsterdam today?"* with the city hard-coded. Prefer *"What's the weather in {{city}} today?"* with `city = Amsterdam` in the variables panel. When you later link the scenario to a dataset for a [batch run](#datasets-and-batch-runs), the variable column becomes the axis of evaluation — the hard-coded version cannot be swept over a dataset.

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

Scenarios only describe what tool calls and returns *look like*; they do not change what the model is permitted to do.

### Configure tools for testing

The list of tools the model is allowed to call is configured on the prompt's settings panel. These tool definitions are part of the testing surface in Prompt Management: they affect future test runs in the UI, but they are not part of the runtime prompt template your application imports.

A tool definition has three fields:

| Field | Type | Notes |
|---|---|---|
| `name` | string | The tool's name as the model will see it. |
| `description` | string or null | Optional free-text description passed to the model. |
| `parameters` | JSON object | A JSON Schema describing the tool's arguments. |

Example:

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

Two behaviors matter:

- **Edits apply immediately.** Changing a tool updates the prompt's test settings right away, so the next run uses the new definition.
- **Versions do not snapshot tools.** A version freezes only the prompt template text, not the tool definitions used for testing.

## Multiple scenarios on a prompt

A prompt can have as many scenarios as you want. Use them to capture distinct intents: a short question, a long ambiguous request, a tool-heavy flow, an edge case. Running the prompt against several scenarios is the standard way to spot that a template change helps one intent but regresses another.

Scenarios have a position — they render in the editor in the order you arrange them — and one is marked as the **default**. The default is the scenario that runs when you click Run without explicitly picking a scenario first.

## Datasets and batch runs

A scenario can be linked to a **dataset** for a batch run. In that mode, Logfire iterates over every case in the dataset (up to 500 per batch call), maps dataset columns to the scenario's variables, and executes the scenario once per case. Each case produces its own rendered messages, its own model output, and its own cost/latency numbers, all queryable under the single batch run record.

Use this when you want to evaluate the same prompt setup across many representative cases instead of trying inputs one by one.

!!! warning "Cost"
    A batch run calls the gateway once per case. Before running a large batch against a paid model, double-check the scenario, dataset mapping, and model settings. Each case spends real gateway budget.

For dataset authoring and management, see the [datasets docs](../../../evaluate/datasets/index.md).

## Runs

Every run record shows you how the prompt behaved under a particular test setup. Use runs to inspect:

- the model output,
- rendered messages,
- tool calls,
- latency and token usage,
- cost, and
- per-case results for batch runs.

When a scenario behaves in a surprising way, the rendered messages are the first thing to check: you can compare what you wrote against what the engine produced.
