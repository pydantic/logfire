---
title: "Connect LangChain to the AI Gateway"
description: "Send LangChain model requests through the Logfire AI Gateway."
---

# Connect LangChain to the AI Gateway

Send requests from your LangChain agents through Logfire to track model usage and apply gateway spending limits without changing your prompts or tools.

[LangChain](https://www.langchain.com/) is a framework for building LLM-powered applications. Both examples keep the agent in LangChain and point `ChatOpenAI` at an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing LangChain project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## TypeScript

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="langchain-gateway.mts" hl_lines="13 15" skip-run="true" skip-reason="external-connection"
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

Set the equivalent `api_key` and `base_url` values on the Python client.

```python title="langchain-gateway.py" hl_lines="14-15" skip-run="true" skip-reason="external-connection"
import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI


def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's always sunny in {city}!"


model = ChatOpenAI(
    model='gpt-5.4-mini',
    api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

agent = create_agent(model=model, tools=[get_weather])

result = agent.invoke({'messages': [{'role': 'user', 'content': 'What is the weather in London?'}]})

print(result['messages'][-1].content)
```

## Verify it worked

Run either example from your terminal. It prints the agent's final response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
