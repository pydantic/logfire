---
title: "Pydantic Logfire Integrations: smolagents"
description: "Instrument Hugging Face smolagents with Pydantic Logfire using OpenInference. Trace agent steps, code execution, tool calls, and LLM requests."
integration: otel
---
# smolagents

[smolagents](https://huggingface.co/docs/smolagents) is Hugging Face's minimal library for building agents that
"think in code". You can send full traces of every agent step, tool call, and LLM request to **Logfire**.

smolagents works with **Logfire** via the [OpenInference](https://github.com/Arize-ai/openinference)
instrumentor. Because [`logfire.configure()`][logfire.configure] sets up the global OpenTelemetry tracer
provider, the instrumentor's spans are exported to **Logfire** automatically.

## Installation

```bash
pip install logfire smolagents openinference-instrumentation-smolagents
```

## Usage

Call [`logfire.configure()`][logfire.configure] and then `SmolagentsInstrumentor().instrument()` **before**
building and running your agent:

```python skip-run="true" skip-reason="external-connection"
import os

from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from smolagents import CodeAgent, OpenAIServerModel, WebSearchTool

import logfire

logfire.configure()
SmolagentsInstrumentor().instrument()

model = OpenAIServerModel(
    model_id='gpt-4o',
    api_base='https://api.openai.com/v1',
    api_key=os.environ['OPENAI_API_KEY'],
)
agent = CodeAgent(tools=[WebSearchTool()], model=model)
agent.run('What is the current population of Tokyo? Search the web.')
```

You'll see a trace in **Logfire** with the agent run at the top and a span for each step, including the code it
generated, the tools it called, and the underlying LLM requests.

!!! warning
    Don't pass a `tracer_provider` argument to `instrument()` — omit it so the instrumentor uses the global
    provider that [`logfire.configure()`][logfire.configure] set up. Passing your own provider would bypass
    **Logfire**.

## Managed prompts

Keep the user-facing instructions you send to your agent in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from smolagents import CodeAgent, OpenAIServerModel, WebSearchTool
from pydantic import BaseModel

import logfire

logfire.configure()


class TaskInputs(BaseModel):
    city: str


task_var = logfire.template_var(
    name='prompt__population_task',
    type=str,
    default='What is the current population of {{city}}? Search the web.',
    inputs_type=TaskInputs,
)

with task_var.get(TaskInputs(city='Tokyo'), label='production') as resolved:
    task = resolved.value

model = OpenAIServerModel(model_id='gpt-4o')
agent = CodeAgent(tools=[WebSearchTool()], model=model)
agent.run(task)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
