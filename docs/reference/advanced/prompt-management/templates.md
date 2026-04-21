---
title: "Writing Prompt Templates"
description: "How to use variables, block helpers, and the @{prompt}@ alias to compose Logfire prompt templates and scenarios."
---

# Writing templates

A prompt template is a string. At render time, Logfire walks that string with a Handlebars engine and substitutes in the scenario's variables. Scenario messages use the same engine, so every `text` part, every `tool-call` args field, and every `tool-return` content field is a mini-template.

If you already know Handlebars, the short version is: Logfire uses the standard Handlebars.js helper set, no extensions enabled by default, plus one non-Handlebars convention — the literal string `@{prompt}@` — which is substituted after Handlebars rendering to inject the rendered prompt template into scenario messages.

If you do not, keep reading. The surface you need is small.

## Simple variables

Use double braces to insert a value:

```handlebars
Hi {{customer_name}}, thanks for contacting us about {{topic}}.
```

If the scenario's variables panel has `customer_name = Taylor` and `topic = your recent order`, the template renders as:

```text
Hi Taylor, thanks for contacting us about your recent order.
```

Variable names in the scenario panel can use plain identifiers (`customer_name`, `topic`) or dotted keys (`customer.name`, `customer.tier`). Dotted keys are unpacked into a nested object, so `customer.name = Taylor` and `customer.tier = gold` both become reachable inside the template as `{{customer.name}}` and `{{customer.tier}}`.

```handlebars
Hi {{customer.name}} ({{customer.tier}} tier), ...
```

## Conditionals and loops

The standard Handlebars block helpers work:

=== "`{{#if}}`"

    ```handlebars
    {{#if customer.vip}}
    This customer is VIP — escalate immediately.
    {{/if}}
    ```

=== "`{{#unless}}`"

    ```handlebars
    {{#unless order.paid}}
    Remind them that payment is pending.
    {{/unless}}
    ```

=== "`{{#each}}`"

    ```handlebars
    Previous orders:
    {{#each recent_orders}}
    - {{this.id}} ({{this.total}} USD)
    {{/each}}
    ```

=== "`{{#with}}`"

    ```handlebars
    {{#with customer}}
    Name: {{name}}
    Tier: {{tier}}
    {{/with}}
    ```

!!! note "Undefined variables render as empty strings"
    If a template references a variable you did not define (for example, you wrote `{{name}}` but never added a `name` variable), Handlebars renders an empty string rather than raising an error. The scenario editor surfaces the list of variables the template references so you can spot typos before running.

## The `@{prompt}@` alias

Scenario messages often need to reference *"the prompt template itself"* — for example, to place the rendered prompt as the system message. Using `{{prompt}}` for this would be fragile (it would collide with a user-defined variable named `prompt`), so Logfire uses the non-Handlebars token `@{prompt}@` instead.

At render time, the server first renders the **prompt template** against the scenario variables to produce the *rendered prompt*. Then it renders **each scenario message**, and finally replaces every literal occurrence of `@{prompt}@` in the scenario message's rendered text with the rendered prompt.

```handlebars
# Prompt template
You are a support agent for {{product}}. Be concise.
```

```text
# Scenario — system message
@{prompt}@
```

Rendered with `product = Logfire`:

```text
You are a support agent for Logfire. Be concise.
```

Key rules:

- `@{prompt}@` only works inside **scenario messages**. Using it inside the prompt template itself is an error (*"Reserved prompt placeholder @{prompt}@ can only be used in scenario messages"*).
- `{{prompt}}` is **not** reserved. If you define a variable called `prompt` in the scenario panel, it substitutes normally; if you do not, it renders empty.
- `@{prompt}@` is a plain string replacement, not a Handlebars construct. It cannot be nested inside block helpers that haven't executed yet — render order is always *template first, then scenario messages, then alias substitution*.

## Nested rendering inside tool calls and returns

`tool-call` args and `tool-return` content are JSON values. The renderer walks the JSON recursively and renders every string field through the template engine. This means you can parameterize a tool's arguments:

```json
{
  "tool_name": "fetch_weather",
  "args": { "city": "{{city}}", "units": "metric" }
}
```

With `city = Amsterdam`, the args become `{ "city": "Amsterdam", "units": "metric" }`.

Non-string fields (numbers, booleans, nulls, nested objects) pass through unchanged. Strings inside arrays are rendered too.

## What is not supported

Only the standard Handlebars.js helper set is enabled on both the editor and the server. In particular, the following are *not* available:

- **Custom helpers** — for example, `{{uppercase name}}`, `{{json obj}}`, `{{eq a b}}`. (The server's Handlebars engine can be extended with a set of 16 extra helpers, but the prompt-rendering pipeline explicitly disables them to keep editor preview and server execution identical.)
- **Partials** — `{{> partialName}}` is not used by the feature.
- **Inline helpers** — Handlebars' `{{#*inline "name"}}` block is not used.

If you need transformation logic that is not expressible in plain Handlebars, do that work in your application code against the rendered template, not inside the template itself.

## Rendering from your application

The Logfire SDK returns the prompt template unchanged — your application is responsible for rendering it before passing the result to your model client.

!!! warning "Today the SDK hand-rolls a simple regex renderer"
    The [demo integration](https://github.com/pydantic/platform/blob/main/src/demos/logfire_demo/demo_prompt_variables_pydantic_ai.py) uses a plain `{{variable}}` regex substitution and supports only flat identifier variables. It does **not** support dotted paths or block helpers. That gap is tracked in [Known limitations](./limitations.md#sdk-rendering-helper) — an official `logfire.render_prompt()` helper is planned so that SDK-rendered output matches what you see in the Logfire UI.

    Until that helper ships, either keep your templates to flat `{{variable}}` substitution in anything you consume through the SDK, or vendor pydantic-handlebars into your application and render there.

See the full grammar and its error behavior in the [Template reference](./template-reference.md).
