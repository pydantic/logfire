---
title: "Connect Strands Agents to the AI Gateway"
description: "Send Strands Agents model requests through the Logfire AI Gateway."
---

# Connect Strands Agents to the AI Gateway

Send requests from your Strands Agents application through Logfire to track model usage and apply spending limits.

[Strands Agents](https://strandsagents.com/) is AWS's open-source framework for building AI agents. Both examples configure its OpenAI model provider with an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Strands Agents project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## TypeScript

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="strands-agents-gateway.mts" hl_lines="13 15" skip-run="true" skip-reason="external-connection"
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

Set the equivalent `api_key` and `base_url` values on the Python model provider.

```python title="strands-agents-gateway.py" hl_lines="8-9" skip-run="true" skip-reason="external-connection"
import os

from strands import Agent
from strands.models.openai import OpenAIModel

model = OpenAIModel(
    client_args={
        'api_key': os.environ['LOGFIRE_GATEWAY_API_KEY'],
        'base_url': 'https://gateway-us.pydantic.dev/proxy/openai',
    },
    model_id='gpt-5.4-mini',
)

agent = Agent(model=model, callback_handler=None)
response = agent('What is the weather in London?')

print(response)
```

## Verify it worked

Run either example from your terminal. It prints the agent's response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
