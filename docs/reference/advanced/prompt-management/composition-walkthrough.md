---
title: "Prompt Composition Walkthrough"
description: "Build a Prompt Management prompt from reusable managed-variable and prompt fragments."
---

# Prompt composition walkthrough

Prompt composition lets one prompt reuse text or structured values from managed
variables and other prompts. Use `@{variable_name}@` references for shared
fragments, and keep `{{runtime_input}}` placeholders for the values supplied by a
scenario or by your application at request time.

This walkthrough builds a support-agent prompt from:

- `support_brand_profile`: a JSON managed variable with product and escalation
  facts.
- `support_safety_rules`: a text managed variable with reusable safety guidance.
- `support_agent`: the prompt that composes those fragments and renders
  per-request values such as `{{customer_name}}`.

## 1. Create reusable fragments

Open **Managed Variables** and create a JSON variable named
`support_brand_profile`. Save a version with this value:

```json
{
  "company": "Acme Support",
  "product": "OrderDesk",
  "escalation_email": "tier2@example.com"
}
```

Create a second managed variable named `support_safety_rules` with type **Text**.
Save a version with this value:

```text
Never reveal private account data. Acknowledge uncertainty. Ask for missing
operational details before taking any irreversible action.
```

Route the label you will use for testing and production, such as `production`, to
the saved versions. The prompt will resolve references through the
same managed-variable targeting and label rules used by application code.

## 2. Create the composed prompt

Open **Prompt Management**, create a prompt named `Support Agent`, and use this
template:

```handlebars
You are the support assistant for @{support_brand_profile.product}@, made by @{support_brand_profile.company}@.

You are helping {{customer_name}} (on the {{tier}} plan).

@{support_safety_rules}@

{{#if is_urgent}}
This issue is urgent. Escalate to @{support_brand_profile.escalation_email}@ after your first reply.
{{else}}
This issue is not marked urgent. Keep your reply concise and action-oriented.
{{/if}}
```

There are two kinds of placeholders here:

- `@{support_brand_profile.product}@`, `@{support_safety_rules}@`, and
  `@{support_brand_profile.escalation_email}@` are composition references. They
  are expanded from managed variables before the prompt is rendered.
- `{{customer_name}}`, `{{tier}}`, and `{{#if is_urgent}}` are Handlebars
  template expressions. They are rendered from scenario variables in the editor,
  and from application inputs in production.

The prompt editor detects both groups. The reference insertion menu can insert
managed-variable references, and the template parameters panel lists the
`{{...}}` values your scenario or application must provide.

## 3. Test with a scenario

Use the default system message:

```text
@{prompt}@
```

Add a user message:

```handlebars
Customer question: {{question}}
```

Add these scenario variables:

| Name | Value |
|------|-------|
| `customer_name` | `Maya Chen` |
| `tier` | `enterprise` |
| `is_urgent` | `true` |
| `question` | `The checkout page is charging customers twice.` |

Run the scenario. The rendered system message should contain the composed brand
profile and safety rules, plus the scenario-specific customer details:

```text
You are the support assistant for OrderDesk, made by Acme Support.

You are helping Maya Chen (on the enterprise plan).

Never reveal private account data. Acknowledge uncertainty. Ask for missing
operational details before taking any irreversible action.

This issue is urgent. Escalate to tier2@example.com after your first reply.
```

If a `@{...}@` reference cannot be resolved, the run reports a validation error.
For prompt references, Logfire can suggest the backing variable name. For
example, a reference to `@{support_agent}@` may suggest
`@{prompt__support_agent}@`.

## 4. Edit one fragment

Go back to `support_safety_rules` in **Managed Variables** and save a new version:

```text
Never reveal private account data. Confirm the customer's identity before
discussing billing. Ask for missing operational details before taking any
irreversible action.
```

Move the serving label to the new version, then run the prompt scenario again.
The support prompt picks up the changed safety text without editing or saving a
new prompt version. That is the main benefit of composition: shared text is
owned once, while prompts refer to it by name.

## 5. Reuse another prompt

Prompts are backed by managed variables whose names use
`prompt__<slug_with_underscores>`. If you create a prompt with slug
`support-style`, another prompt can reference it as:

```handlebars
@{prompt__support_style}@
```

Use prompt references for reusable prompt-sized sections, such as a style guide,
a routing policy, or a domain-specific decision procedure. Use regular managed
variables for smaller text fragments and structured facts.

## 6. Ship the composed prompt

Save a prompt version and promote it by moving the serving label on the prompt's
backing managed variable. In application code, fetch the prompt as usual
(remember prompts resolve via `LOGFIRE_API_KEY`, not the write token — see
[Use Prompts in Your Application](./application.md#fetch-and-render-the-prompt-from-the-sdk)):

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class SupportPromptInputs(BaseModel):
    customer_name: str
    tier: str
    is_urgent: bool


prompt_var = logfire.template_prompt(
    'support-agent',
    default='',
    inputs_type=SupportPromptInputs,
)

with prompt_var.get(
    SupportPromptInputs(customer_name='Maya Chen', tier='enterprise', is_urgent=True),
    label='production',
    targeting_key='customer-123',
) as resolved:
    prompt = resolved.value
```

`prompt_var.get(...)` expands the `@{...}@` references using the current managed
variable configuration, then renders the remaining `{{...}}` placeholders with
the request-specific inputs before returning the final prompt text. If you fetch
the prompt with `logfire.prompt()` instead, render the remaining Handlebars
placeholders yourself before sending the final prompt to your model.

## Rendering order

For prompt scenarios, Logfire renders in this order:

1. Expand composition references such as `@{support_safety_rules}@` in the prompt
   template.
2. Render the prompt template's `{{...}}` placeholders with scenario variables.
3. Preserve the scenario-only `@{prompt}@` alias, expand other composition
   references in scenario messages or tool fields, and render their `{{...}}`
   placeholders with the same scenario variables.
4. Replace the scenario-only `@{prompt}@` alias with the rendered prompt.

For application code, `logfire.template_prompt()` uses the same order: expand
`@{...}@` references during resolution, then render `{{...}}` placeholders with
the inputs passed to `get(inputs)`. If you use `logfire.prompt()` to fetch the raw
template, your application is responsible for rendering those remaining
Handlebars placeholders.

## When to use composition

Use composition when a fragment has its own owner, version history, or rollout:

- shared safety, brand, tone, or escalation instructions,
- structured facts that many prompts need,
- a reusable prompt section consumed by several prompts,
- a fragment that should be canaried or rolled back independently.

Keep request-specific values as `{{...}}` placeholders. Composition is for
managed configuration; templating is for per-run inputs.
