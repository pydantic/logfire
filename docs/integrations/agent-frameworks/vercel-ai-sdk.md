---
title: "Pydantic Logfire Integrations: Vercel AI SDK"
description: "Send Vercel AI SDK (the `ai` package) telemetry to Pydantic Logfire using its built-in OpenTelemetry support."
integration: otel
---
# Vercel AI SDK

The [Vercel AI SDK](https://ai-sdk.dev/) (the `ai` npm package) has built-in OpenTelemetry support. You enable
it per call with `telemetry: { isEnabled: true }`, and it writes to the global OpenTelemetry tracer. Configure
the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/) and register the AI SDK
OpenTelemetry integration at process start, and your spans flow into **Logfire**.

## Installation

Install the packages used by the examples:

=== "npm"

    ```bash
    npm install ai @ai-sdk/openai @ai-sdk/otel @pydantic/logfire-node zod
    ```

=== "pnpm"

    ```bash
    pnpm add ai @ai-sdk/openai @ai-sdk/otel @pydantic/logfire-node zod
    ```

=== "yarn"

    ```bash
    yarn add ai @ai-sdk/openai @ai-sdk/otel @pydantic/logfire-node zod
    ```

=== "bun"

    ```bash
    bun add ai @ai-sdk/openai @ai-sdk/otel @pydantic/logfire-node zod
    ```

Install development tools if you want to type-check the standalone TypeScript example:

=== "npm"

    ```bash
    npm install --save-dev typescript @types/node
    ```

=== "pnpm"

    ```bash
    pnpm add --save-dev typescript @types/node
    ```

=== "yarn"

    ```bash
    yarn add --dev typescript @types/node
    ```

=== "bun"

    ```bash
    bun add --dev typescript @types/node
    ```

Node.js `v22.18.0+` supports running this `.mts` file directly on the Node.js 22 line with built-in type
stripping. Newer active Node.js versions also support type stripping. This removes TypeScript syntax at runtime,
but it does not type-check your code.

```bash
node vercel-ai-sdk.mts
```

If you are not using a Node.js version with built-in type stripping, use a TypeScript runner or runtime:

=== "npm"

    ```bash
    npm install --save-dev tsx
    npx tsx vercel-ai-sdk.mts
    ```

=== "pnpm"

    ```bash
    pnpm add --save-dev tsx
    pnpm exec tsx vercel-ai-sdk.mts
    ```

=== "yarn"

    ```bash
    yarn add --dev tsx
    yarn tsx vercel-ai-sdk.mts
    ```

=== "bun"

    ```bash
    bun vercel-ai-sdk.mts
    ```

## Usage

```typescript title="vercel-ai-sdk.mts"
import { generateText, registerTelemetry, stepCountIs, tool } from 'ai';
import { openai } from '@ai-sdk/openai';
import { OpenTelemetry } from '@ai-sdk/otel';
import logfire from '@pydantic/logfire-node';
import { z } from 'zod';

const envSchema = z.object({
  OPENAI_API_KEY: z.string(),
  LOGFIRE_WRITE_TOKEN: z.string(),
});

const env = envSchema.parse(process.env);

function configureTelemetry() {
  logfire.configure({
    token: env.LOGFIRE_WRITE_TOKEN,
    serviceName: 'vercel-ai-sdk-weather-agent',
  });

  registerTelemetry(new OpenTelemetry());
}

const weatherTool = tool({
  description: 'Get the weather in a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

async function main() {
  configureTelemetry();

  try {
    const { text } = await generateText({
      model: openai('gpt-5.4-mini'),
      prompt: 'What is the weather in London?',
      tools: { weatherTool },
      stopWhen: stepCountIs(5),
      telemetry: {
        isEnabled: true,
        functionId: 'weather-example',
      },
    });

    console.log(text);
  } finally {
    await logfire.shutdown();
  }
}

await main();
```

Set `OPENAI_API_KEY` from OpenAI and set `LOGFIRE_WRITE_TOKEN` to a Logfire project write token from your
project settings page in Logfire, then run. In Logfire, you will see spans for the model call, prompt, response,
token counts, and tool call.

!!! info "Details"
    - `configureTelemetry()` configures Logfire and registers the AI SDK OpenTelemetry integration before
      calling `generateText()`.
    - `logfire.shutdown()` waits for queued telemetry to be sent. This example calls it because the script exits
      immediately after one model call. In a server or worker process, call it from your shutdown handler.
    - The AI SDK captures inputs and outputs by default. If your prompts or completions contain sensitive data,
      set `recordInputs: false` or `recordOutputs: false` in the `telemetry` options.

## Use the Logfire AI Gateway

You can also route the model call through the [Logfire AI Gateway](../../reference/advanced/gateway/index.md).
Use this when you want Logfire-managed provider keys, spending limits, routing, and gateway request telemetry
for the same AI SDK workflow.

The gateway exposes an OpenAI-compatible route, so the AI SDK can use an OpenAI-compatible provider configured
with your gateway URL. Use a **gateway API key** from the Gateway **API Keys** tab for the model call and a
**Logfire write token** from your project settings page in Logfire for telemetry export:

```typescript title="vercel-ai-sdk-gateway.mts"
import { generateText, registerTelemetry, stepCountIs, tool } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { OpenTelemetry } from '@ai-sdk/otel';
import logfire from '@pydantic/logfire-node';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
  LOGFIRE_WRITE_TOKEN: z.string(),
});

const env = envSchema.parse(process.env);

function configureTelemetry() {
  logfire.configure({
    token: env.LOGFIRE_WRITE_TOKEN,
    serviceName: 'vercel-ai-sdk-gateway-weather-agent',
  });

  registerTelemetry(new OpenTelemetry());
}

const weatherTool = tool({
  description: 'Get the weather in a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

const gateway = createOpenAI({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

async function main() {
  configureTelemetry();

  try {
    const { text } = await generateText({
      model: gateway('gpt-5.4-mini'),
      prompt: 'What is the weather in London?',
      tools: { weatherTool },
      stopWhen: stepCountIs(5),
      telemetry: {
        isEnabled: true,
        functionId: 'weather-example',
      },
    });

    console.log(text);
  } finally {
    await logfire.shutdown();
  }
}

await main();
```

Set `LOGFIRE_GATEWAY_API_KEY` and `LOGFIRE_WRITE_TOKEN`, then run.

!!! info "Details"
    - The example uses the US gateway route. For EU projects, set `baseURL` to
      `https://gateway-eu.pydantic.dev/proxy/openai`.
    - `logfire.shutdown()` waits for queued telemetry to be sent. This example calls it because the script exits
      immediately after one model call. In a server or worker process, call it from your shutdown handler.
    - The AI SDK captures inputs and outputs by default. If your prompts or completions contain sensitive data,
      set `recordInputs: false` or `recordOutputs: false` in the `telemetry` options.

## Managed prompts

Author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and
fetch them with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/):

```typescript
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

const promptVar = defineTemplateVar<string, { city: string }>('prompt__weather', {
  default: 'What is the weather in {{city}}? Use the tool.',
  templateInputsSchema: {
    type: 'object',
    properties: { city: { type: 'string' } },
    required: ['city'],
  },
});

const resolved = await promptVar.get({ city: 'Paris' });
// Pass resolved.value as the `prompt` to generateText.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
