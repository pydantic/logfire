---
title: "AI Gateway: VoltAgent"
description: "Route VoltAgent model calls through the Logfire AI Gateway."
---

# VoltAgent

[VoltAgent](https://voltagent.dev/) is a TypeScript framework for building AI agents with built-in observability and tool use. To route its model calls through the Logfire AI Gateway, configure an OpenAI-compatible model provider with the gateway URL and set `LOGFIRE_GATEWAY_API_KEY` to a key from the Gateway **API Keys** tab.

```typescript title="voltagent-gateway.mts" skip-run="true" skip-reason="external-connection"
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import { Agent } from '@voltagent/core';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
});

const env = envSchema.parse(process.env);

const gateway = createOpenAICompatible({
  name: 'logfire-gateway',
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const agent = new Agent({
  name: 'weather-agent',
  instructions: 'A helpful assistant that answers questions.',
  model: gateway.chatModel('gpt-5.4-mini'),
});

const response = await agent.generateText('What is the weather in London?');

console.log(response.text);
```
