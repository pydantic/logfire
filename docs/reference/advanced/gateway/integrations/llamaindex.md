---
title: "AI Gateway: LlamaIndex"
description: "Route LlamaIndex model calls through the Logfire AI Gateway."
---

# LlamaIndex

[LlamaIndex](https://developers.llamaindex.ai/) is a framework for building data-augmented large language model (LLM) applications, including retrieval-augmented generation (RAG) pipelines and agent workflows. To route its model calls through the Logfire AI Gateway, configure the OpenAI LLM client with the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

```python title="llamaindex-gateway.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from llama_index.core.workflow import StartEvent, StopEvent, Workflow, step
from llama_index.llms.openai import OpenAI


class WeatherWorkflow(Workflow):
    llm = OpenAI(
        model="gpt-5.4-mini",
        api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
        api_base="https://gateway-us.pydantic.dev/proxy/openai",
    )

    @step
    async def answer(self, ev: StartEvent) -> StopEvent:
        response = await self.llm.acomplete(f"What is the weather in {ev.city}?")
        return StopEvent(result=str(response))


async def main() -> None:
    result = await WeatherWorkflow(timeout=60).run(city="London")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
```
