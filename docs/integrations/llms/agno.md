---
title: "Pydantic Logfire Integrations: Agno"
description: "Instrument Agno agents (formerly Phidata) with Pydantic Logfire using OpenInference. Trace agent runs, tool calls, and model requests."
integration: otel
---
# Agno

[Agno](https://docs.agno.com) (formerly **Phidata**) is a framework for building multi-agent systems with
memory, knowledge, and tools. You can send full traces of every agent run, tool call, and model request to
**Logfire**.

Agno works with **Logfire** via the [OpenInference](https://github.com/Arize-ai/openinference) instrumentor.
Because [`logfire.configure()`][logfire.configure] sets up the global OpenTelemetry tracer provider, the
instrumentor's spans are exported to **Logfire** automatically.

## Installation

```bash
pip install logfire agno openai openinference-instrumentation-agno
```

## Usage

Call [`logfire.configure()`][logfire.configure] and then `AgnoInstrumentor().instrument()` **before** creating
and running your agent:

```python skip-run="true" skip-reason="external-connection"
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.tools.duckduckgo import DuckDuckGoTools
from openinference.instrumentation.agno import AgnoInstrumentor

import logfire

logfire.configure()
AgnoInstrumentor().instrument()

agent = Agent(
    name='Web Search Agent',
    model=OpenAIChat(id='gpt-4o'),
    tools=[DuckDuckGoTools()],
    instructions='Answer questions concisely, using web search when helpful.',
    markdown=True,
)
agent.print_response('What is Pydantic Logfire, in one sentence?')
```

You'll see a trace in **Logfire** with the agent run at the top and the underlying tool calls and model
requests nested beneath it.

!!! note
    Agno's own docs show configuring a raw OTLP exporter. With **Logfire** you don't need to — just call
    [`logfire.configure()`][logfire.configure], which reads your `LOGFIRE_TOKEN` (or `logfire auth`
    credentials) and sets up export and region handling for you.

## Managed prompts

Keep your agents' instructions in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from pydantic import BaseModel

import logfire

logfire.configure()


class InstructionInputs(BaseModel):
    audience: str


instructions_var = logfire.template_var(
    name='prompt__assistant_instructions',
    type=str,
    default='Answer questions concisely.',
    inputs_type=InstructionInputs,
)

with instructions_var.get(InstructionInputs(audience='developers'), label='production') as resolved:
    instructions = resolved.value

agent = Agent(
    name='Assistant',
    model=OpenAIChat(id='gpt-4o'),
    instructions=instructions,
)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
