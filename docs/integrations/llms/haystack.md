---
title: "Pydantic Logfire Integrations: Haystack"
description: "Instrument deepset Haystack pipelines with Pydantic Logfire using OpenInference. Trace each component, generator, and LLM call."
integration: otel
---
# Haystack

[Haystack](https://haystack.deepset.ai/) is deepset's framework for building LLM applications and pipelines
(package `haystack-ai`). You can send full traces of every pipeline component and LLM call to **Logfire**.

Haystack works with **Logfire** via the [OpenInference](https://github.com/Arize-ai/openinference)
instrumentor. Because [`logfire.configure()`][logfire.configure] sets up the global OpenTelemetry tracer
provider, the instrumentor's spans are exported to **Logfire** automatically.

## Installation

```bash
pip install logfire haystack-ai openinference-instrumentation-haystack
```

## Usage

Haystack omits prompt and response content from its spans by default. Set
`HAYSTACK_CONTENT_TRACING_ENABLED=true` (before your app starts) to capture it, then call
[`logfire.configure()`][logfire.configure] and `HaystackInstrumentor().instrument()`:

```python skip-run="true" skip-reason="external-connection"
import os

os.environ['HAYSTACK_CONTENT_TRACING_ENABLED'] = 'true'

from haystack import Pipeline
from haystack.components.builders import ChatPromptBuilder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from openinference.instrumentation.haystack import HaystackInstrumentor

import logfire

logfire.configure()
HaystackInstrumentor().instrument()

pipeline = Pipeline()
pipeline.add_component('prompt_builder', ChatPromptBuilder())
pipeline.add_component('llm', OpenAIChatGenerator(model='gpt-4o-mini'))
pipeline.connect('prompt_builder.prompt', 'llm.messages')

result = pipeline.run(
    {
        'prompt_builder': {
            'template': [ChatMessage.from_user('Tell me a one-line fun fact about {{topic}}.')],
            'template_variables': {'topic': 'the Roman Empire'},
        }
    }
)
print(result['llm']['replies'][0].text)
```

You'll see a trace in **Logfire** with the pipeline run at the top and a span for each component, including the
LLM request and response.

## Managed prompts

Keep your pipeline's prompt templates in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from haystack.dataclasses import ChatMessage
from pydantic import BaseModel

import logfire

logfire.configure()


class FactInputs(BaseModel):
    topic: str


prompt_var = logfire.template_var(
    name='prompt__fun_fact',
    type=str,
    default='Tell me a one-line fun fact about {{topic}}.',
    inputs_type=FactInputs,
)

with prompt_var.get(FactInputs(topic='the Roman Empire'), label='production') as resolved:
    user_message = ChatMessage.from_user(resolved.value)

# Pass `user_message` straight to your generator / pipeline.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
