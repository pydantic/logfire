---
title: "Connect Vercel AI SDK to the AI Gateway"
description: "Send Vercel AI SDK model requests through the Logfire AI Gateway."
---

# Connect Vercel AI SDK to the AI Gateway

Send requests from your Vercel AI SDK application through Logfire to track model usage and apply gateway spending limits without changing your tools.

The [Vercel AI SDK](https://ai-sdk.dev/) is a TypeScript toolkit for AI web applications, including streaming, tool use, and multiple model providers. The example creates an OpenAI provider that uses an OpenAI-compatible gateway route.

## Before you start

- Complete the [AI Gateway prerequisites](index.md#before-you-start), including setting `LOGFIRE_GATEWAY_API_KEY` in your terminal.
- Use an existing Vercel AI SDK project with the packages imported below installed.

!!! note "Model data passes through Logfire"
    This configuration sends prompts, tool inputs, and model responses through the Logfire AI Gateway and the selected model provider. If gateway telemetry is enabled, Logfire stores the conversation content in your selected project. Calls to built-in providers count toward your gateway spend.

## Configure Vercel AI SDK

Set `apiKey` to your gateway key and `baseURL` to the OpenAI-compatible gateway route. Copy the route and a supported model name from the Gateway **Connect** tab.

```typescript title="vercel-ai-sdk-gateway.mts" hl_lines="12-13" skip-run="true" skip-reason="external-connection"
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

## Verify it worked

Run the example from your terminal. It prints the model response. That confirms the client reached the gateway. Organization admins can also open **AI Engineering** > **Gateway** > **Spending** to see usage for the key. If telemetry is enabled, open the selected project's **Live** view to inspect the request trace.

## Troubleshooting

- **The example cannot read `LOGFIRE_GATEWAY_API_KEY`:** set the environment variable in the same terminal where you run the example.
- **The request returns an authentication or model error:** copy the URL and model name again from the Gateway **Connect** tab, and confirm that the selected route supports the OpenAI request format.
