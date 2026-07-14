---
title: "Connect LlamaIndex to the AI Gateway"
description: "Send LlamaIndex model requests through the Logfire AI Gateway."
---

# Connect LlamaIndex to the AI Gateway

Send requests from your LlamaIndex workflows through Logfire to track model usage and apply gateway spending limits.

[LlamaIndex](https://developers.llamaindex.ai/) is a framework for building LLM applications over your data. This includes retrieval-augmented generation (RAG), where an application retrieves relevant data before asking a model to answer. The example points LlamaIndex's OpenAI client at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing LlamaIndex project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, retrieved context, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure LlamaIndex

Set `api_key` to your gateway key and `api_base` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```python title="llamaindex-gateway.py" hl_lines="11-12" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from llama_index.core.workflow import StartEvent, StopEvent, Workflow, step
from llama_index.llms.openai import OpenAI


class WeatherWorkflow(Workflow):
    llm = OpenAI(
        model='gpt-5.4-mini',
        api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
        api_base='https://gateway-us.pydantic.dev/proxy/openai',
    )

    @step
    async def answer(self, ev: StartEvent) -> StopEvent:
        response = await self.llm.acomplete(f'What is the weather in {ev.city}?')
        return StopEvent(result=str(response))


async def main() -> None:
    result = await WeatherWorkflow(timeout=60).run(city='London')
    print(result)


if __name__ == '__main__':
    asyncio.run(main())
```

## Verify it worked

Run the example from your terminal. It prints the workflow result. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **Python raises `KeyError: 'LOGFIRE_GATEWAY_API_KEY'`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
