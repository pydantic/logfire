---
title: "Pydantic Logfire Integrations: Strands Agents"
description: "Send AWS Strands Agents telemetry to Pydantic Logfire. Strands' native OpenTelemetry spans flow to Logfire with no extra exporter."
integration: otel
---
# Strands Agents

[Strands Agents](https://strandsagents.com/) (the `strands-agents` package, by AWS) has **native OpenTelemetry
tracing**. It emits spans through the OTel *global* tracer provider, so once
[`logfire.configure()`][logfire.configure] has set **Logfire** as the global provider, Strands traces flow to
**Logfire** automatically — no extra exporter needed.

## Installation

```bash
pip install logfire strands-agents strands-agents-tools
```

## Usage

Call [`logfire.configure()`][logfire.configure] **before** you construct your `Agent`:

```python skip-run="true" skip-reason="external-connection"
import os

from strands import Agent, tool

import logfire

# Logfire registers itself as the global OTel tracer provider.
logfire.configure()

# Opt in to the latest GenAI semantic conventions for rich prompt/tool/token rendering.
os.environ['OTEL_SEMCONV_STABILITY_OPT_IN'] = 'gen_ai_latest_experimental'


@tool
def weather(city: str) -> str:
    """Get the current weather for a city."""
    return f"It's sunny in {city}."


agent = Agent(
    tools=[weather],
    # trace_attributes are attached to every span this agent produces.
    trace_attributes={'session.id': 'demo-1', 'user.id': 'you@example.com'},
)

result = agent("What's the weather in Lisbon?")
print(result)
```

You'll see a trace in **Logfire** with the agent invocation, the model (LLM) call, and the `weather` tool call
as a nested timeline.

!!! warning
    Do **not** call `StrandsTelemetry().setup_otlp_exporter()` when using **Logfire**. Per the Strands docs,
    you should skip `StrandsTelemetry` when a global tracer provider is already configured — your existing
    OpenTelemetry setup is used automatically. Calling `setup_otlp_exporter()` would register a competing
    provider and send traces to a separate endpoint instead of **Logfire**.

!!! note "Model provider"
    A bare `Agent(...)` defaults to **Amazon Bedrock** (and needs AWS credentials). To run without AWS, pass
    another model, e.g. `Agent(model='gpt-4o', ...)` with `OPENAI_API_KEY` set.

## Managed prompts

Keep your agents' system prompts in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from strands import Agent
from pydantic import BaseModel

import logfire

logfire.configure()


class SystemInputs(BaseModel):
    role: str


system_var = logfire.template_var(
    name='prompt__strands_system',
    type=str,
    default='You are a helpful assistant.',
    inputs_type=SystemInputs,
)

with system_var.get(SystemInputs(role='a travel assistant'), label='production') as resolved:
    system_prompt = resolved.value

agent = Agent(system_prompt=system_prompt)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
