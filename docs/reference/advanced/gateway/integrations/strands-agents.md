---
title: "AI Gateway: Strands Agents"
description: "Route Strands Agents model calls through the Logfire AI Gateway."
---

# Strands Agents

[Strands Agents](https://strandsagents.com/) is AWS's open-source framework for building AI agents. To route its model calls through the Logfire AI Gateway, configure the OpenAI-compatible model provider with the gateway URL, using a key from the Gateway **API Keys** tab.

## TypeScript

```typescript title="strands-agents-gateway.mts" skip-run="true" skip-reason="external-connection"
import { Agent } from '@strands-agents/sdk';
import { OpenAIModel } from '@strands-agents/sdk/models/openai';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const model = new OpenAIModel({
  api: 'chat',
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  clientConfig: {
    baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
  },
  modelId: 'gpt-5.4-mini',
});

const agent = new Agent({ model, printer: false });
const response = await agent.invoke('What is the weather in London?');

console.log(response.lastMessage ?? response);
```

## Python

```python title="strands-agents-gateway.py" skip-run="true" skip-reason="external-connection"
import os

from strands import Agent
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    client_args={
        "api_key": os.environ["LOGFIRE_GATEWAY_API_KEY"],
        "base_url": "https://gateway-us.pydantic.dev/proxy/openai",
    },
    model_id="gpt-5.4-mini",
)

agent = Agent(model=model, callback_handler=None)
response = agent("What is the weather in London?")

print(response)
```
