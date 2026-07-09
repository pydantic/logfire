---
title: "AI Gateway: Mastra"
description: "Route Mastra model calls through the Logfire AI Gateway."
---

# Mastra

[Mastra](https://mastra.ai/) is a TypeScript framework for building AI agents and workflows. To route its model calls through the Logfire AI Gateway, create an OpenAI-compatible provider pointed at the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

```typescript title="mastra-gateway.mts" skip-run="true" skip-reason="external-connection"
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
