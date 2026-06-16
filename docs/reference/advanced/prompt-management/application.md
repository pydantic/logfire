---
title: "Use Prompts in Your Application"
description: "How to promote a prompt version, fetch it from the SDK, and render it in your application."
---

# Use Prompts in Your Application

Once a prompt looks good in the editor, the production workflow is:

1. Save a version on the Prompts page.
2. Promote the version by moving a label such as `production`.
3. Fetch that labeled prompt from your application.
4. Render the template with runtime variables before sending it to your model,
   preferably with `logfire.template_var()`.

## Promote a version

Saving a version and promoting a version are separate steps.

- Save the version you want on the Prompts page.
- Move the serving label on the Managed Variables page for that prompt.

This lets you iterate on drafts without changing what production imports.

## Fetch and render the prompt from the SDK

Each prompt is exposed to application code through its backing managed variable:

```text
prompt__<slug_with_underscores>
```

If your prompt slug is `welcome-email`, the SDK name is
`prompt__welcome_email`.

Install the variables extra in applications that fetch prompt variables:

```bash
pip install 'logfire[variables]'
```

For prompts with runtime `{{...}}` inputs, prefer `logfire.template_var(...)`.
It resolves the prompt variable, expands `@{...}@` composition references,
renders the remaining Handlebars template with your typed inputs, and returns
the final prompt text.

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class WelcomeEmailInputs(BaseModel):
    customer_name: str
    topic: str


prompt_var = logfire.template_var(
    name='prompt__welcome_email',
    type=str,
    default='',
    inputs_type=WelcomeEmailInputs,
)

with prompt_var.get(
    WelcomeEmailInputs(customer_name='Taylor', topic='your recent order'),
    label='production',
) as resolved:
    prompt = resolved.value

# Pass `prompt` to your model client here.
```

If your prompt composes shared fragments, keep those fragments as managed variables
and reference them from the prompt with `@{variable_name}@`. The SDK resolves
those references during `.get()`. See the
[Prompt composition walkthrough](./composition-walkthrough.md) for the full
workflow.

## Manual rendering

If you need to control rendering yourself, fetch the prompt with
`logfire.var(...)`. In that mode, `.get()` still expands `@{...}@` composition
references, but your application renders the remaining `{{...}}` placeholders.

```python skip="true"
import logfire
from pydantic_handlebars import render

logfire.configure()

prompt_var = logfire.var(name='prompt__welcome_email', type=str, default='')

with prompt_var.get(label='production', targeting_key='customer-123') as resolved:
    template = resolved.value

prompt = render(
    template,
    {
        'customer': {
            'name': 'Taylor',
            'tier': 'enterprise',
        },
        'topic': 'your recent order',
        'is_urgent': False,
    },
)

# Pass `prompt` to your model client here.
```

When rendering manually, keep simple templates to flat variables such as
`{{customer_name}}`. For dotted paths, conditionals, loops, or composed
fragments, use a renderer that supports the same Handlebars features documented
in [Template Reference](./template-reference.md).

## Labels and rollouts

When you want rollout percentages or targeting rules to select the prompt
version, omit `label` and pass a stable `targeting_key` instead. Use
`label='production'` only when you want to bypass rollout and request that label
explicitly.
