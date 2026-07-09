---
title: "AI Gateway: LangChain"
description: "Route LangChain model calls through the Logfire AI Gateway."
---

# LangChain

[LangChain](https://www.langchain.com/) is a framework for building LLM-powered applications. To route its model calls through the Logfire AI Gateway, configure `ChatOpenAI` with the gateway URL, using a key from the Gateway **API Keys** tab.

## TypeScript

```typescript title="langchain-gateway.mts" skip-run="true" skip-reason="external-connection"
import { createAgent, tool } from 'langchain';
import { ChatOpenAI } from '@langchain/openai';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const model = new ChatOpenAI({
  model: 'gpt-5.4-mini',
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  configuration: {
    baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
  },
});

const getWeather = tool(
  ({ city }) => `It's always sunny in ${city}!`,
  {
    name: 'get_weather',
    description: 'Get weather for a city',
    schema: z.object({
      city: z.string(),
    }),
  }
);

const agent = createAgent({
  model,
  tools: [getWeather],
});

const result = await agent.invoke({
  messages: [{ role: 'user', content: 'What is the weather in London?' }],
});

console.log(result);
```

## Python

```python title="langchain-gateway.py" skip-run="true" skip-reason="external-connection"
import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI


def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's always sunny in {city}!"


model = ChatOpenAI(
    model="gpt-5.4-mini",
    api_key=os.environ["LOGFIRE_GATEWAY_API_KEY"],
    base_url="https://gateway-us.pydantic.dev/proxy/openai",
)

agent = create_agent(model=model, tools=[get_weather])

result = agent.invoke(
    {"messages": [{"role": "user", "content": "What is the weather in London?"}]}
)

print(result["messages"][-1].content)
```
