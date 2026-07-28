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
   preferably with `logfire.template_prompt()`.

## Promote a version

Saving a version and promoting a version are separate steps.

- Save the version you want on the Prompts page.
- Move the serving label on the Managed Variables page for that prompt.

This lets you iterate on drafts without changing what production imports.

## Fetch and render the prompt from the SDK

`logfire.prompt()` and `logfire.template_prompt()` fetch a prompt by its slug.
They are `logfire.var()` / `logfire.template_var()` specialized to prompts: they
apply Logfire's prompt naming convention for you, so you pass the slug
(`welcome-email`) rather than the backing managed-variable name
(`prompt__welcome_email`).

Install the variables extra in applications that fetch prompts:

```bash
pip install 'logfire[variables]'
```

!!! note "API Key Required"
    Prompts resolve through the managed-variables API, which requires an **API key**
    with the `project:read_variables` scope — this is different from the write token
    (`LOGFIRE_TOKEN`) used to send traces and logs. Set it via the `LOGFIRE_API_KEY`
    environment variable or pass `logfire.configure(api_key=...)`. **Without it, the
    SDK never contacts Logfire for prompts and `.get()` silently returns your code
    `default`.** See [Remote Variables](../managed-variables/remote.md) for details.

For prompts with runtime `{{...}}` inputs, prefer `logfire.template_prompt(...)`.
It resolves the prompt, expands `@{...}@` composition references, renders the
remaining Handlebars template with your typed inputs, and returns the final
prompt text.

```python skip="true"
from pydantic import BaseModel

import logfire

logfire.configure()


class WelcomeEmailInputs(BaseModel):
    customer_name: str
    topic: str


welcome_email = logfire.template_prompt(
    'welcome-email',
    default='',
    inputs_type=WelcomeEmailInputs,
)

with welcome_email.get(
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

## Create prompts from code

If a prompt only exists in your code so far, you don't have to recreate it by
hand in the UI. `logfire.variables_push()` pushes everything declared in code —
managed variables *and* prompts. For each prompt that doesn't exist in the
project yet, it creates the prompt and publishes your code `default` as version
1, so it appears on the Prompts page ready for iteration and serves exactly what
your code default already said. Prompts that already exist are never modified by
a push — publish new versions on the Prompts page, over MCP, or via the prompts
API.

```python skip="true"
import logfire

logfire.configure()

welcome_email = logfire.prompt(
    'welcome-email',
    default='Write a short welcome email about {{topic}} for {{customer_name}}.',
    description='Transactional welcome email prompt',
)

if __name__ == '__main__':
    logfire.variables_push()
```

Pushing requires the API key to carry the `project:write_variables` scope in
addition to `project:read_variables`.

## Manual rendering

If you need to control rendering yourself, fetch the prompt with
`logfire.prompt(...)`. In that mode, `.get()` still expands `@{...}@` composition
references, but your application renders the remaining `{{...}}` placeholders.

```python skip="true"
import logfire
from pydantic_handlebars import render

logfire.configure()

welcome_email = logfire.prompt('welcome-email', default='')

with welcome_email.get(label='production', targeting_key='customer-123') as resolved:
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
