---
title: "Pydantic Logfire Integrations: Google ADK"
description: "Send Google Agent Development Kit (ADK) telemetry to Pydantic Logfire. ADK's native OpenTelemetry spans flow to Logfire with no extra instrumentor."
integration: otel
---
# Google ADK

[Google ADK](https://adk.dev/) (the Agent Development Kit, `google-adk`) is Google's framework for building and
deploying agents. ADK has **native OpenTelemetry instrumentation** and resolves its tracer from the *global*
tracer provider — so once [`logfire.configure()`][logfire.configure] has set **Logfire** as the global
provider, ADK's agent, LLM, and tool spans flow to **Logfire** automatically, with no instrumentor.

## Installation

```bash
pip install logfire google-adk
```

## Usage

Call [`logfire.configure()`][logfire.configure] **before** you run the agent. That's the entire integration:

```python skip-run="true" skip-reason="external-connection"
import asyncio

from google.adk.agents import Agent  # Agent is an alias of LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

import logfire

# Sets the global OTel tracer provider — ADK's native spans flow here automatically.
logfire.configure(service_name='adk-demo')


def get_weather(city: str) -> dict:
    """Return the current weather for a city."""
    return {'status': 'success', 'report': f"It's sunny and 25C in {city}."}


agent = Agent(
    name='weather_agent',
    model='gemini-2.5-flash',
    instruction='You are a helpful assistant. Use tools to answer questions.',
    tools=[get_weather],
)


async def main():
    runner = InMemoryRunner(agent=agent, app_name='weather_app')
    session = await runner.session_service.create_session(app_name='weather_app', user_id='user1')
    message = types.Content(role='user', parts=[types.Part(text='Weather in Paris?')])
    async for event in runner.run_async(user_id='user1', session_id=session.id, new_message=message):
        if event.is_final_response():
            print(event.content.parts[0].text)


if __name__ == '__main__':
    asyncio.run(main())
```

You'll see a trace in **Logfire** with the agent run, the underlying LLM (Gemini) call, and the `get_weather`
tool call nested as a timeline.

!!! note "Capturing message content"
    ADK attaches prompt and response text to spans only when you opt in. Set these environment variables
    before running for the richest traces:

    ```python
    import os

    os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
    os.environ['OTEL_SEMCONV_STABILITY_OPT_IN'] = 'gen_ai_latest_experimental'
    ```

!!! tip "Optional: OpenInference attributes"
    For richer GenAI semantic-convention attributes you can additionally enable the OpenInference layer. It
    composes with **Logfire** because it also writes to the global provider:

    ```bash
    pip install openinference-instrumentation-google-adk
    ```

    ```python
    from openinference.instrumentation.google_adk import GoogleADKInstrumentor

    GoogleADKInstrumentor().instrument()  # after logfire.configure()
    ```

    The native spans are usually sufficient on their own — add this only if you want the OpenInference schema.

!!! warning
    `gemini-*` models need credentials: set `GOOGLE_API_KEY` (AI Studio) or `GOOGLE_GENAI_USE_VERTEXAI=true`
    with Vertex AI configured. You don't need `OTEL_EXPORTER_OTLP_*` env vars — `logfire.configure()` sets up
    the exporter and region for you.

## Managed prompts

Keep your agents' instructions in
[Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
from google.adk.agents import Agent
from pydantic import BaseModel

import logfire

logfire.configure()


class InstructionInputs(BaseModel):
    persona: str


instruction_var = logfire.template_var(
    name='prompt__weather_agent_instruction',
    type=str,
    default='You are a helpful assistant. Use tools to answer questions.',
    inputs_type=InstructionInputs,
)

with instruction_var.get(InstructionInputs(persona='a friendly meteorologist'), label='production') as resolved:
    instruction = resolved.value

agent = Agent(name='weather_agent', model='gemini-2.5-flash', instruction=instruction)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
