---
title: "Pydantic Logfire Integrations: Semantic Kernel (Python)"
description: "Send Microsoft Semantic Kernel (Python) telemetry to Pydantic Logfire. SK's native OpenTelemetry spans flow to Logfire once you enable its GenAI diagnostics."
integration: otel
---
# Semantic Kernel (Python)

[Microsoft Semantic Kernel](https://learn.microsoft.com/en-us/semantic-kernel/) for Python emits native
OpenTelemetry spans, metrics, and logs to the **global** OpenTelemetry providers. Because
[`logfire.configure()`][logfire.configure] sets those global providers, SK's telemetry flows to **Logfire**
automatically once you enable SK's experimental GenAI diagnostics with an environment variable.

!!! note
    Unlike the [.NET version](../agent-frameworks/semantic-kernel-dotnet.md), Semantic Kernel for Python does
    **not** require a source allowlist — it uses the global tracer/meter directly. So
    [`logfire.configure()`][logfire.configure] plus the diagnostics env var is the whole integration.

## Installation

```bash
pip install logfire semantic-kernel
```

## Usage

Set the diagnostics flag in your terminal before starting the script. The `SENSITIVE` variant records prompts
and completions; use `SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS=true` instead for metadata only.

```bash
export SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE=true
```

Then call [`logfire.configure()`][logfire.configure] before creating the agent:

```python skip-run="true" skip-reason="external-connection"
import asyncio

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function

import logfire

# Sets the global OTel tracer + meter provider exporting to Logfire.
logfire.configure(service_name='semantic-kernel-agent')


class WeatherPlugin:
    @kernel_function(description='Get the weather for a city')
    def get_weather(self, city: str) -> str:
        return f'The weather in {city} is sunny, 21C.'


async def main() -> None:
    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(ai_model_id='gpt-4o-mini'),  # uses OPENAI_API_KEY
        name='weather_agent',
        instructions='Use the weather plugin before answering.',
        plugins=[WeatherPlugin()],
    )
    response = await agent.get_response(messages="What's the weather in Paris?")
    print(response.message.content)


if __name__ == '__main__':
    asyncio.run(main())
```

You'll see an `invoke_agent` span in **Live** and **Agents**, with child `chat.completions` and function-invocation
spans. With the `SENSITIVE` flag enabled, the conversation is also available in the agent-run detail.

!!! warning "Common pitfalls"
    - **No diagnostics, no `gen_ai` spans.** Without the `SEMANTICKERNEL_EXPERIMENTAL_GENAI_*` env var, you get
      function/kernel spans but no AI-connector spans. Set it before the kernel runs. Use the `_SENSITIVE`
      variant only when you want prompts/completions recorded.
    - **Don't replace the global provider.** Don't call `set_tracer_provider()` / `set_meter_provider()`
      yourself after [`logfire.configure()`][logfire.configure] — that would override **Logfire**'s exporter.

## Managed prompts

Keep your prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and fetch them at
runtime:

```bash
pip install 'logfire[variables]'
```

```python skip="true"
import asyncio

from pydantic import BaseModel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function

import logfire

logfire.configure()


class WeatherPlugin:
    @kernel_function(description='Get the weather for a city')
    def get_weather(self, city: str) -> str:
        return f'The weather in {city} is sunny, 21C.'


class WeatherInputs(BaseModel):
    city: str


prompt_var = logfire.template_var(
    name='prompt__weather_instructions',
    type=str,
    default='Use the weather plugin to answer questions about {{city}}.',
    inputs_type=WeatherInputs,
)

with prompt_var.get(WeatherInputs(city='Paris'), label='production') as resolved:
    prompt = resolved.value

async def main():
    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(ai_model_id='gpt-4o-mini'),
        name='weather_agent',
        instructions=prompt,
        plugins=[WeatherPlugin()],
    )
    response = await agent.get_response(messages="What's the weather in Paris?")
    print(response.message.content)


if __name__ == '__main__':
    asyncio.run(main())
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
