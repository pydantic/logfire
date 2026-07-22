---
title: "Pydantic Logfire Integrations: Instructor"
description: "Instrument Instructor structured outputs with Pydantic Logfire. Trace each LLM request and Pydantic validation of the response model."
integration: logfire
---
# Instructor

[Instructor](https://python.useinstructor.com/) gives you validated, structured outputs from LLMs by patching
an underlying client (such as OpenAI) and adding a `response_model`. Because it wraps a normal client, the
simplest way to send data to **Logfire** is to instrument that client directly — which is exactly what
[Instructor's own docs](https://python.useinstructor.com/blog/2024/05/01/instructor-logfire/) recommend.

## Installation

```bash
pip install logfire instructor openai
```

## Usage

Call [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] to trace the LLM requests, and
optionally [`logfire.instrument_pydantic()`][logfire.Logfire.instrument_pydantic] to record validation of the
`response_model`:

```python skip-run="true" skip-reason="external-connection"
import instructor
from openai import OpenAI
from pydantic import BaseModel

import logfire

logfire.configure()
logfire.instrument_openai()  # trace the OpenAI client that Instructor wraps
logfire.instrument_pydantic()  # optional: record response_model validation

client = instructor.from_openai(OpenAI())


class UserInfo(BaseModel):
    name: str
    age: int


user = client.chat.completions.create(
    model='gpt-4o-mini',
    response_model=UserInfo,
    messages=[{'role': 'user', 'content': 'John Doe is 30 years old.'}],
)
print(user)
#> name='John Doe' age=30
```

You'll see the LLM conversation in the **Logfire** UI along with the structured output and, if you enabled it,
the **Pydantic** validation of the `UserInfo` model.

!!! tip
    Instrument the **base** OpenAI client, not the Instructor wrapper. Calling
    [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] with no argument instruments all OpenAI
    clients globally, so it works even when Instructor builds the client internally (e.g. via
    `instructor.from_provider('openai/gpt-4o-mini')`).

## Managed prompts

Keep your prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at
runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
import instructor
from openai import OpenAI
from pydantic import BaseModel

import logfire

logfire.configure()
logfire.instrument_openai()


class ExtractInputs(BaseModel):
    text: str


prompt_var = logfire.template_var(
    name='prompt__extract_user',
    type=str,
    default='Extract the user info from: {{text}}',
    inputs_type=ExtractInputs,
)

with prompt_var.get(ExtractInputs(text='John Doe is 30 years old.'), label='production') as resolved:
    content = resolved.value


class UserInfo(BaseModel):
    name: str
    age: int


client = instructor.from_openai(OpenAI())
user = client.chat.completions.create(
    model='gpt-4o-mini',
    response_model=UserInfo,
    messages=[{'role': 'user', 'content': content}],
)
print(user)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
