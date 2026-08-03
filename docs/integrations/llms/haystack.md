---
title: "Pydantic Logfire Integrations: Haystack"
description: "Send deepset Haystack's native OpenTelemetry agent and pipeline traces to Pydantic Logfire with the first-party opentelemetry-haystack package."
integration: otel
---
# Haystack

[Haystack](https://haystack.deepset.ai/) is deepset's framework for building agents and retrieval pipelines
(package `haystack-ai`). You can send traces of agent steps, tool calls, model requests, and pipeline components
to **Logfire**.

Haystack's first-party `opentelemetry-haystack` package connects its tracing system to
[OpenTelemetry](https://opentelemetry.io/), the open standard **Logfire** uses to receive telemetry.
[`logfire.configure()`][logfire.configure] installs the application-wide OpenTelemetry destination, and
`OpenTelemetryTracer` sends Haystack's own spans to it.

## Installation

```bash
pip install logfire "haystack-ai>=3.0" "opentelemetry-haystack>=1.0"
```

## Usage

Haystack omits prompt, response, tool argument, and tool result content from its spans by default. Set
`HAYSTACK_CONTENT_TRACING_ENABLED=true` before importing Haystack to capture that content. This sends potentially
sensitive application data to **Logfire**, so leave it disabled if that data should not leave your application.

```python skip-run="true" skip-reason="external-connection"
import os

os.environ['HAYSTACK_CONTENT_TRACING_ENABLED'] = 'true'

from haystack import tracing
from haystack.components.agents import Agent
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack.tools import Tool
from haystack_integrations.tracing.opentelemetry import OpenTelemetryTracer
from opentelemetry import trace

import logfire

logfire.configure()
tracing.enable_tracing(OpenTelemetryTracer(trace.get_tracer('haystack')))


def lookup_incident(incident_id: str) -> str:
    return f'{incident_id} is resolved; owner=platform-observability'


lookup_tool = Tool(
    name='lookup_incident',
    description='Look up the current status and owner of an incident by ID.',
    parameters={
        'type': 'object',
        'properties': {'incident_id': {'type': 'string'}},
        'required': ['incident_id'],
    },
    function=lookup_incident,
)

agent = Agent(
    chat_generator=OpenAIChatGenerator(model='gpt-4o-mini'),  # needs OPENAI_API_KEY
    tools=[lookup_tool],
    system_prompt='Use operational tools to verify facts before answering.',
    max_agent_steps=3,
)
result = agent.run(
    messages=[ChatMessage.from_user("Use lookup_incident for incident_id='incident-42'.")]
)
print(result['last_message'].text)
```

You'll see Haystack's `haystack.agent.run` trace in **Logfire**, with child spans for each agent step, model
request, and tool call.

!!! warning
    Don't also enable `openinference-instrumentation-haystack` for the same application. Both integrations trace
    Haystack operations, so enabling both can produce duplicate spans.

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
