---
title: "AI Gateway: OpenAI Agents SDK"
description: "Route OpenAI Agents SDK model calls through the Logfire AI Gateway."
---

# OpenAI Agents SDK

The [OpenAI Agents software development kit (SDK)](https://openai.github.io/openai-agents-python/) is OpenAI's official SDK for building systems where multiple AI agents collaborate, hand off tasks, and call tools. To route its model calls through the Logfire AI Gateway, configure an OpenAI-compatible model provider with the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

## TypeScript

```typescript title="openai-agents-sdk-gateway.mts" skip-run="true" skip-reason="external-connection"
import { Agent, OpenAIProvider, Runner } from '@openai/agents';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const provider = new OpenAIProvider({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const runner = new Runner({ modelProvider: provider });

const agent = new Agent({
  name: 'Weather Agent',
  instructions: 'You are a concise weather assistant.',
  model: 'gpt-5.4-mini',
});

const result = await runner.run(agent, 'What is the weather in London?');

console.log(result.finalOutput);
```

## Python

```python title="openai-agents-sdk-gateway.py" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
    base_url="https://gateway-us.pydantic.dev/proxy/openai",
)

agent = Agent(
    name="Weather Agent",
    instructions="You are a concise weather assistant.",
    model=OpenAIChatCompletionsModel(
        model="gpt-5.4-mini",
        openai_client=client,
    ),
)


async def main() -> None:
    set_tracing_disabled(True)
    result = await Runner.run(agent, "What is the weather in London?")
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
```
