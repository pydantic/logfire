---
title: "Template Reference"
description: "The authoritative grammar used by Logfire Prompt Management templates: supported helpers, rendering order, and error behavior."
---

# Template reference

This page is the canonical specification for the template grammar used by Prompt Management.

Most prompt authors only need variable substitution and a few standard Handlebars block helpers. Scenario-specific additions, such as `@{prompt}@`, are collected later on this page.

## Grammar at a glance

The supported grammar is **standard Handlebars** with the default helper set. Prompt Management also adds one non-Handlebars convention used only in scenario messages: the `@{prompt}@` alias.

### Mustache expressions

| Form | Meaning |
|---|---|
| `{{name}}` | Insert the value of variable `name` |
| `{{object.field}}` | Insert a nested field — dotted paths resolve against the rendered context |
| `{{object.field.subfield}}` | Arbitrary depth is supported |

HTML escaping is **disabled** for prompt rendering — values are inserted verbatim. There is therefore no practical difference between `{{x}}` and the Handlebars raw form `{{{x}}}` here.

### Block helpers

Prompt Management enables the standard Handlebars block helpers.

| Helper | Purpose |
|---|---|
| `{{#if cond}}…{{else}}…{{/if}}` | Conditional block |
| `{{#unless cond}}…{{/unless}}` | Inverse conditional |
| `{{#each list}}…{{/each}}` | Iterate. `{{this}}`, `@index`, `@first`, `@last` available inside |
| `{{#with obj}}…{{/with}}` | Narrow the context to `obj` for the block |
| `{{lookup obj key}}` | Look up a field by computed key |
| `{{log value}}` | Log to server (no output; useful during debugging) |

## Rendering order for prompt templates

Prompt templates render against the current variable set using standard Handlebars rules.

## Scenario-only additions

Scenarios reuse the same grammar, but the testing surface adds a few extra rules.

### The `@{prompt}@` alias

`@{prompt}@` is **not** a Handlebars token. It is a literal substring that the renderer replaces with the rendered prompt template *after* Handlebars has finished processing a scenario message.

- Valid only inside scenario messages (text parts, tool-call `args`, tool-return `content`).
- Using `@{prompt}@` inside the prompt template itself raises `RenderingError: Reserved prompt placeholder @{prompt}@ can only be used in scenario messages`.
- `{{prompt}}` is **not** reserved. If you define a scenario variable called `prompt`, it substitutes normally.

### Rendering order inside scenarios

```mermaid
flowchart TD
    A[Prompt template] -->|Handlebars render with scenario variables| B[Rendered prompt]
    C[Scenario message] -->|Handlebars render with scenario variables| D[Rendered message]
    B -.inject.-> D
    D -->|Replace every literal @{prompt}@ with Rendered prompt| E[Final message sent to model]
```

1. The **prompt template** is rendered through Handlebars against the scenario's variables, producing the *rendered prompt*.
2. For each **scenario message** (and every templated field within it — text content, tool-call args, tool-return content), the message is rendered through Handlebars against the same scenario variables.
3. Finally, every literal occurrence of `@{prompt}@` in the rendered message is replaced with the rendered prompt from step 1.

This order matters: the prompt template never sees `@{prompt}@` as a payload, and scenario messages never see un-rendered Handlebars from the prompt template.

## Variable naming

Scenario variable names come from the variables panel on the scenario editor. Two styles are supported:

- **Plain identifiers** — `customer_name`, `topic`, `max_retries`. Reachable as `{{customer_name}}`.
- **Dotted paths** — `customer.name`, `customer.tier`. On both surfaces, dotted entries are unpacked into a nested object so they are reachable as `{{customer.name}}` and via `{{#with customer}}{{name}}{{/with}}`.

Dotted paths share prefixes: defining `customer.name` and `customer.tier` creates a single `customer` object with two fields. If the same prefix is used both as a plain identifier and as a dotted path (e.g. `customer = "..."` and `customer.name = "..."`), the dotted entries overwrite the plain value.

## Undefined variables

A reference to a variable that is not defined renders as the empty string. No error is raised.

```handlebars
Hello {{does_not_exist}}!
```

Renders as `Hello !` when `does_not_exist` is not defined.

The scenario editor panel lists the variables the template refers to, so missing values are easy to spot before you run.

## Errors

Rendering errors fall into a small set of categories:

| Error | Cause |
|---|---|
| `Reserved prompt placeholder @{prompt}@ can only be used in scenario messages` | The prompt template contains `@{prompt}@`. Move it into a scenario message. |
| `Unclosed block` / parser errors | The template is malformed Handlebars — typically an unbalanced `{{#if}} … {{/if}}` or `{{#each}} … {{/each}}`. |
| `Missing helper` | You referenced a helper that is not in the default set. Only the standard Handlebars helpers are enabled. |

## Compatibility with the SDK

The Logfire SDK returns the raw template string, so your application renders it locally before passing the result to your model.

If your application uses simple substitution, stick to flat `{{variable}}` references. If you want to use dotted paths or block helpers, use a renderer that supports the same Handlebars features documented here.

See [Use Prompts in Your Application](./application.md) for the current integration workflow.
