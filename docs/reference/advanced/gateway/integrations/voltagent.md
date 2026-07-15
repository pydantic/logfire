---
title: "Connect VoltAgent to the AI Gateway"
description: "Send VoltAgent model requests through the Logfire AI Gateway."
---

# Connect VoltAgent to the AI Gateway

Send requests from your VoltAgent agents through Logfire to track model usage and apply spending limits.

[VoltAgent](https://voltagent.dev/) is a TypeScript framework for building AI agents with tool use and its own observability features. The example creates an OpenAI-compatible provider that uses the gateway key and route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing VoltAgent project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure VoltAgent

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="voltagent-gateway.mts" hl_lines="13-14" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run the example from your terminal. It prints the agent's response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
