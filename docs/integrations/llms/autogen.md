---
title: "Pydantic Logfire Integrations: AutoGen"
description: "Instrument Microsoft AutoGen agents with Pydantic Logfire using OpenInference. Trace agent runs, tool calls, and LLM messages."
integration: otel
---
# AutoGen

[AutoGen](https://microsoft.github.io/autogen/) is Microsoft's framework for building multi-agent applications.
You can send full traces of agent runs, tool calls, and LLM messages to **Logfire**.

AutoGen works with **Logfire** via the [OpenInference](https://github.com/Arize-ai/openinference) instrumentor.
Because [`logfire.configure()`][logfire.configure] sets up the global OpenTelemetry tracer provider, the
instrumentor's spans are exported to **Logfire** automatically.

!!! note "AutoGen vs. AG2"
    "AutoGen" split into two projects. This page covers **Microsoft AutoGen** (the `autogen-agentchat` /
    `autogen-core` v0.4+ rewrite), which is the most widely used branch. The community fork
    [AG2](https://docs.ag2.ai/) (package `ag2`) has its own, different API and its own OpenTelemetry support —
    make sure the instrumentor you install matches the framework you use.

## Installation

Install `logfire`, Microsoft AutoGen, and the matching OpenInference instrumentor:

```bash
pip install logfire "autogen-agentchat>=0.5.0" "autogen-ext[openai]" openinference-instrumentation-autogen-agentchat
```

## Usage

```python skip-run="true" skip-reason="external-connection"
import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from openinference.instrumentation.autogen_agentchat import AutogenAgentChatInstrumentor

import logfire

logfire.configure()
AutogenAgentChatInstrumentor().instrument()


async def main():
    model_client = OpenAIChatCompletionClient(model='gpt-4o')  # needs OPENAI_API_KEY
    agent = AssistantAgent(
        name='assistant',
        model_client=model_client,
        system_message='You are a helpful assistant.',
    )
    result = await agent.run(task='Say hello to Logfire in one short sentence.')
    print(result.messages[-1].content)
    await model_client.close()


asyncio.run(main())
```

You'll see a trace in **Logfire** with the agent run at the top and the underlying LLM messages and any tool
calls nested beneath it.

!!! warning
    The `openinference-instrumentation-autogen-agentchat` package only instruments **Microsoft AutoGen**.
    For the AG2 fork, use AG2's own OpenTelemetry support (`pip install "ag2[openai,tracing]"`) instead — the
    `-agentchat` instrumentor will produce no spans for it.

## Managed prompts

Keep your agents' system messages in [Prompt Management](../../reference/advanced/prompt-management/index.md)
and fetch them at runtime with the Logfire SDK:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel

import logfire

logfire.configure()


class SystemInputs(BaseModel):
    tone: str


system_var = logfire.template_var(
    name='prompt__assistant_system',
    type=str,
    default='You are a helpful assistant.',
    inputs_type=SystemInputs,
)

with system_var.get(SystemInputs(tone='friendly'), label='production') as resolved:
    system_message = resolved.value

agent = AssistantAgent(
    name='assistant',
    model_client=OpenAIChatCompletionClient(model='gpt-4o'),
    system_message=system_message,
)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
