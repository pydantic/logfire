---
title: "Writing Prompt Templates"
description: "How to write Logfire prompt templates with variables and standard Handlebars helpers."
---

# Writing templates

A prompt template is a string. At render time, Logfire walks that string with a Handlebars engine and substitutes in the current variables.

!!! note "Your application renders the template at runtime"
    Prompt Management stores the template, but your application is responsible for substituting runtime variables before sending the rendered prompt to your model client. See [Use Prompts in Your Application](./application.md).

If you already know Handlebars, the short version is: Logfire uses the standard Handlebars.js helper set, with no custom helpers enabled by default.

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
    If a template references a variable you did not define (for example, you wrote `{{name}}` but never added a `name` variable), Handlebars renders an empty string rather than raising an error. The editor surfaces the list of variables the template references so you can spot typos before running.

## Scenario-specific rendering

The prompt editor reuses the same template engine for saved test scenarios, including scenario messages, tool-call arguments, and tool-return content.

Two scenario-only details are documented separately because they are part of testing a prompt rather than authoring the prompt template itself:

- the `@{prompt}@` alias, which injects the rendered prompt into a scenario message,
- recursive rendering inside tool-call `args` and tool-return `content`.

See [Test Prompts](./scenarios.md) for the workflow and [Template reference](./template-reference.md#scenario-only-additions) for the exact rules.

## What is not supported

Only the standard Handlebars.js helper set is enabled on both the editor and the server. In particular, the following are *not* available:

- **Custom helpers** — for example, `{{uppercase name}}`, `{{json obj}}`, `{{eq a b}}`. (The server's Handlebars engine can be extended with a set of 16 extra helpers, but the prompt-rendering pipeline explicitly disables them to keep editor preview and server execution identical.)
- **Partials** — `{{> partialName}}` is not used by the feature.
- **Inline helpers** — Handlebars' `{{#*inline "name"}}` block is not used.

If you need transformation logic that is not expressible in plain Handlebars, do that work in your application code against the rendered template, not inside the template itself.

## Rendering from your application

The Logfire SDK returns the prompt template unchanged, so your application renders it before passing the result to your model client.

If you want to keep rendering simple in application code, prefer flat variables such as `{{customer_name}}`. If you want to use dotted paths or block helpers, make sure your application uses a renderer that supports the same Handlebars features described here.

See [Use Prompts in Your Application](./application.md) for the current integration workflow.

See the full grammar and its error behavior in the [Template reference](./template-reference.md).
