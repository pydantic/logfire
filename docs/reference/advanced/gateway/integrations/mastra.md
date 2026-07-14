---
title: "Connect Mastra to the AI Gateway"
description: "Send Mastra model requests through the Logfire AI Gateway."
---

# Connect Mastra to the AI Gateway

Send requests from your Mastra agents through Logfire to track model usage and apply gateway spending limits without changing your tools or workflow.

[Mastra](https://mastra.ai/) is a TypeScript framework for building AI agents and workflows. The example creates an OpenAI-compatible provider that uses the gateway key and route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Mastra project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Mastra

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="mastra-gateway.mts" hl_lines="14-15" skip-run="true" skip-reason="external-connection"
import { createOpenAI } from '@ai-sdk/openai';
import { Mastra } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const gateway = createOpenAI({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const weatherTool = createTool({
  id: 'get-weather',
  description: 'Get current weather for a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

const weatherAgent = new Agent({
  id: 'weather-agent',
  name: 'Weather Agent',
  instructions:
    'You are a concise weather assistant. Ask for a location if none is provided. Use the weatherTool to fetch current weather data.',
  model: gateway('gpt-5.4-mini'),
  tools: { weatherTool },
});

const mastra = new Mastra({
  agents: { weatherAgent },
});

const result = await mastra.getAgent('weatherAgent').generate('What is the weather in London?');

console.log(result.text);
```

## Verify it worked

Run the example from your terminal. It prints the agent's response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
