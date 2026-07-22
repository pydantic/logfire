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

Set `SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE=true` (to record prompts and
completions; use the non-`SENSITIVE` variant for metadata only) and call
[`logfire.configure()`][logfire.configure]:

```python skip-run="true" skip-reason="external-connection"
import asyncio
import os

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from semantic_kernel.functions import kernel_function

import logfire

# Emit gen_ai spans including prompts/completions. Set before configuring.
os.environ['SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS_SENSITIVE'] = 'true'

# Sets the global OTel tracer + meter provider exporting to Logfire.
logfire.configure(service_name='semantic-kernel-agent')


class WeatherPlugin:
    @kernel_function(description='Get the weather for a city')
    def get_weather(self, city: str) -> str:
        return f'The weather in {city} is sunny, 21C.'


async def main() -> None:
    kernel = Kernel()
    kernel.add_service(OpenAIChatCompletion(ai_model_id='gpt-4o-mini'))  # uses OPENAI_API_KEY
    kernel.add_plugin(WeatherPlugin(), plugin_name='weather')

    answer = await kernel.invoke_prompt("What's the weather in Paris? Use the weather plugin.")
    print(answer)


if __name__ == '__main__':
    asyncio.run(main())
```

You'll see SK's `chat.completions` spans (with `gen_ai.*` attributes), token-usage metrics, and
function-invocation spans in **Logfire**.

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
from pydantic import BaseModel
from semantic_kernel import Kernel

import logfire

logfire.configure()


class WeatherInputs(BaseModel):
    city: str


prompt_var = logfire.template_var(
    name='prompt__weather',
    type=str,
    default="What's the weather in {{city}}? Use the weather plugin.",
    inputs_type=WeatherInputs,
)

with prompt_var.get(WeatherInputs(city='Paris'), label='production') as resolved:
    prompt = resolved.value

kernel = Kernel()
# ... add services/plugins ...
answer = await kernel.invoke_prompt(prompt)
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
