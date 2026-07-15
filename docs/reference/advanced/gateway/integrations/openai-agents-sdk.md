---
title: "Connect OpenAI Agents SDK to the AI Gateway"
description: "Send OpenAI Agents SDK model requests through the Logfire AI Gateway."
---

# Connect OpenAI Agents SDK to the AI Gateway

Send requests from your OpenAI Agents SDK agents through Logfire to track model usage and apply spending limits without changing your handoffs or tools.

The [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) builds systems where agents collaborate, hand off tasks, and call tools. Both examples configure its model provider with an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing OpenAI Agents SDK project with the packages imported by your chosen example installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## TypeScript

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="openai-agents-sdk-gateway.mts" hl_lines="11-12" skip-run="true" skip-reason="external-connection"
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

Pass the same key and route to `AsyncOpenAI`. The example disables the Agents SDK's own tracing; gateway telemetry still records the model request when you enable it in Logfire.

```python title="openai-agents-sdk-gateway.py" hl_lines="8-9" skip-run="true" skip-reason="external-connection"
import asyncio
import os

from agents import Agent, OpenAIChatCompletionsModel, Runner, set_tracing_disabled
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=os.environ['LOGFIRE_GATEWAY_API_KEY'],
    base_url='https://gateway-us.pydantic.dev/proxy/openai',
)

agent = Agent(
    name='Weather Agent',
    instructions='You are a concise weather assistant.',
    model=OpenAIChatCompletionsModel(
        model='gpt-5.4-mini',
        openai_client=client,
    ),
)


async def main() -> None:
    set_tracing_disabled(True)
    result = await Runner.run(agent, 'What is the weather in London?')
    print(result.final_output)


if __name__ == '__main__':
    asyncio.run(main())
```

## Verify it worked

Run either example from your terminal. It prints the agent's final response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
