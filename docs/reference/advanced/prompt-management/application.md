---
title: "Use Prompts in Your Application"
description: "How to promote a prompt version, fetch it from the SDK, and render it in your application."
---

# Use Prompts in Your Application

Once a prompt looks good in the editor, the production workflow is:

1. Save a version on the Prompts page.
2. Promote the version by moving a label such as `production`.
3. Fetch that labeled prompt from your application.
4. Render the template with runtime variables before sending it to your model.

## Promote a version

Saving a version and promoting a version are separate steps.

- Save the version you want on the Prompts page.
- Move the serving label on the Managed Variables page for that prompt.

This lets you iterate on drafts without changing what production imports.

## Fetch the prompt from the SDK

Today, application code fetches prompts with `logfire.var(...)`.

```python
template = logfire.var(name='prompt__welcome_email', label='production').value
```

The `name` currently follows the pattern `prompt__<slug_with_underscores>`.

If your prompt slug is `welcome-email`, the SDK name is `prompt__welcome_email`.

## Render the template in your application

The SDK returns the template string. Your application renders it with runtime variables before passing the result to your model client.

If you keep your templates to flat variables such as `{{customer_name}}`, simple substitution is often enough.

If you want to use dotted paths or Handlebars block helpers, use a renderer that supports the same Handlebars features documented in [Template Reference](./template-reference.md).

## Example

```python
import logfire

template = logfire.var(name='prompt__welcome_email', label='production').value
rendered_prompt = template.replace('{{customer_name}}', customer_name)
```

Here is a slightly more complete example:

```python
import logfire


def render_prompt(template: str, variables: dict[str, str]) -> str:
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f'{{{{{key}}}}}', value)
    return rendered


prompt_template = logfire.var(name='prompt__welcome_email', label='production').value
prompt = render_prompt(prompt_template, {'customer_name': customer_name})

# Pass `prompt` to your model client here.
```
