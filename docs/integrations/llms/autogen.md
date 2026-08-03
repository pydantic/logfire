---
title: "Pydantic Logfire Integrations: AutoGen"
description: "Send Microsoft AutoGen's native OpenTelemetry agent and tool traces to Pydantic Logfire, with model request tracing from the Logfire OpenAI integration."
integration: otel
---
# AutoGen

[AutoGen](https://microsoft.github.io/autogen/) is Microsoft's framework for building multi-agent applications.
You can send full traces of agent runs, tool calls, and large language model (LLM) messages to **Logfire**.

AutoGen emits native [OpenTelemetry](https://opentelemetry.io/) spans, which are structured records of agent
creation, agent runs, and tool execution. [`logfire.configure()`][logfire.configure] installs the application-wide
OpenTelemetry destination, so AutoGen sends those spans to **Logfire** automatically. AutoGen leaves model-client
tracing to the client library, so [`logfire.instrument_openai()`][logfire.Logfire.instrument_openai] adds the model
requests and responses made by `OpenAIChatCompletionClient`.

!!! note "AutoGen vs. AG2"
    "AutoGen" split into two projects. This page covers **Microsoft AutoGen** (the `autogen-agentchat` /
    `autogen-core` v0.4+ rewrite), which is the most widely used branch. The community fork
    [AG2](https://docs.ag2.ai/) (package `ag2`) has its own, different application programming interface (API)
    and its own OpenTelemetry support —
    make sure the packages and tracing setup match the framework you use.

## Installation

Install `logfire` and Microsoft AutoGen:

```bash
pip install logfire "autogen-agentchat>=0.7.5" "autogen-ext[openai]>=0.7.5"
```

## Usage

```python skip-run="true" skip-reason="external-connection"
import asyncio

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

import logfire

logfire.configure()
logfire.instrument_openai()


async def main():
    model_client = OpenAIChatCompletionClient(model='gpt-4o')  # needs OPENAI_API_KEY

    def lookup_incident(incident_id: str) -> str:
        """Look up the current status and owner of an incident by ID."""
        return f'{incident_id} is resolved; owner=platform-observability'

    try:
        agent = AssistantAgent(
            name='assistant',
            model_client=model_client,
            tools=[lookup_incident],
            reflect_on_tool_use=True,
            max_tool_iterations=2,
            system_message='Use operational tools to verify facts before answering.',
        )
        result = await agent.run(
            task="Use lookup_incident for incident_id='incident-42', then report its status and owner."
        )
        print(result.messages[-1].content)
    finally:
        await model_client.close()


asyncio.run(main())
```

You'll see the native AutoGen agent run in **Live** and **Agents**, with the `lookup_incident` tool call and
instrumented OpenAI model requests nested beneath it.

!!! warning
    Don't also enable `openinference-instrumentation-autogen-agentchat`. It wraps the same agent and tool methods
    that current AutoGen versions trace natively, which can produce duplicate spans. For the AG2 fork, use AG2's
    own OpenTelemetry support (`pip install "ag2[openai,tracing]"`) instead.

## Managed prompts

Keep your agents' system messages in [Prompt Management](../../reference/advanced/prompt-management/index.md)
and fetch them at runtime with the Logfire software development kit (SDK):

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel

import logfire

logfire.configure()
logfire.instrument_openai()


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
