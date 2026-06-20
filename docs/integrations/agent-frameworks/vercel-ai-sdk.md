---
title: "Pydantic Logfire Integrations: Vercel AI SDK"
description: "Send Vercel AI SDK (the `ai` package) telemetry to Pydantic Logfire using its built-in OpenTelemetry support."
integration: otel
---
# Vercel AI SDK

The [Vercel AI SDK](https://ai-sdk.dev/) (the `ai` npm package) has built-in OpenTelemetry support. You enable
it per call with `experimental_telemetry: { isEnabled: true }`, and it writes to the global OpenTelemetry
tracer. Configure the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/) (which
registers that global tracer pointed at **Logfire**) at process start, and your spans flow in.

## Installation

```bash
npm install ai @ai-sdk/openai @pydantic/logfire-node zod
```

## Usage

Configure Logfire **first** so the global tracer exists before any `ai` call:

```typescript title="agent.ts"
import * as logfire from '@pydantic/logfire-node';

logfire.configure({ serviceName: 'vercel-ai-agent' }); // sets the global OTel tracer provider

import { generateText, tool, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

const weather = tool({
  description: 'Get the weather for a city',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => ({ city, tempC: 21 }),
});

async function main() {
  const { text } = await generateText({
    model: openai('gpt-4o-mini'),
    prompt: 'What is the weather in Paris? Use the tool.',
    tools: { weather },
    stopWhen: stepCountIs(5),
    experimental_telemetry: { isEnabled: true, functionId: 'weather-agent' },
  });
  console.log(text);
  await logfire.shutdown(); // flush spans before exit
}

main();
```

Set your `OPENAI_API_KEY` and `LOGFIRE_TOKEN`, then run with `npx tsx agent.ts`. You'll see spans for the
prompt, response, token counts, and tool calls in **Logfire**.

!!! warning "Common pitfalls"
    - **Configure Logfire before importing/calling `ai`**, or spans go to the no-op global tracer and silently
      vanish.
    - **Flush on exit.** Short-lived scripts must `await logfire.shutdown()` or the batch processor drops
      unflushed spans.
    - **Content capture.** `recordInputs` / `recordOutputs` default to `true`, so prompts and completions are
      captured. Set them to `false` in `experimental_telemetry` to redact sensitive content.

!!! tip "Next.js"
    In Next.js, register OpenTelemetry in `instrumentation.ts` (e.g. with `@vercel/otel`'s `registerOTel`) and
    set `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev` plus
    `OTEL_EXPORTER_OTLP_HEADERS='Authorization=<write-token>'`. The `experimental_telemetry` call is identical.

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
