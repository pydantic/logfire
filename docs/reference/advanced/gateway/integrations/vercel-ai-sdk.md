---
title: "AI Gateway: Vercel AI SDK"
description: "Route Vercel AI SDK model calls through the Logfire AI Gateway."
---

# Vercel AI SDK

The [Vercel AI software development kit (SDK)](https://ai-sdk.dev/) is a TypeScript toolkit for building AI-powered web applications, with support for streaming, tool use, and multiple model providers. To route its model calls through the Logfire AI Gateway, create an OpenAI-compatible provider pointed at the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

```typescript title="vercel-ai-sdk-gateway.mts" skip-run="true" skip-reason="external-connection"
import { createOpenAI } from '@ai-sdk/openai';
import { generateText, stepCountIs, tool } from 'ai';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const gateway = createOpenAI({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const weatherTool = tool({
  description: 'Get the weather in a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

const { text } = await generateText({
  model: gateway('gpt-5.4-mini'),
  prompt: 'What is the weather in London?',
  tools: { weatherTool },
  stopWhen: stepCountIs(5),
});

console.log(text);
```
