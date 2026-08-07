---
title: "Pydantic Logfire Integrations: Vercel AI SDK"
description: "Send Vercel AI SDK (the `ai` package) telemetry to Pydantic Logfire using its built-in OpenTelemetry support."
integration: otel
---
# Vercel AI SDK

The [Vercel AI SDK](https://ai-sdk.dev/) (the `ai` npm package) supports OpenTelemetry through its official
`@ai-sdk/otel` integration. Attach that integration to a native `ToolLoopAgent` and configure the
[Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/) as the global tracer provider to send
the resulting agent, model, and tool spans to **Logfire**.

## Installation

```bash
npm install 'ai@^7' '@ai-sdk/openai@^4' '@ai-sdk/otel@^1' @pydantic/logfire-node zod
```

## Usage

Configure Logfire **first** so the global tracer exists before any `ai` call:

```typescript title="agent.ts"
import * as logfire from '@pydantic/logfire-node';
import { ToolLoopAgent, stepCountIs, tool } from 'ai';
import { OpenTelemetry } from '@ai-sdk/otel';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

logfire.configure({ serviceName: 'vercel-ai-agent' }); // sets the global OTel tracer provider

let toolCalls = 0;
const weather = tool({
  description: 'Get the weather for a city',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ city }) => {
    toolCalls += 1;
    return { city, tempC: 21 };
  },
});

const agent = new ToolLoopAgent({
  model: openai('gpt-4o-mini'),
  instructions: 'Use the weather tool before answering.',
  tools: { weather },
  stopWhen: stepCountIs(3),
  telemetry: {
    functionId: 'weather-agent',
    integrations: [new OpenTelemetry()],
    isEnabled: true,
  },
});

async function main() {
  try {
    const { text } = await agent.generate({
      prompt: 'What is the weather in Paris? Use the tool.',
    });
    if (toolCalls !== 1) throw new Error(`Expected one tool call, received ${toolCalls}`);
    console.log(text);
  } finally {
    await logfire.shutdown(); // flush success and error spans before exit
  }
}

main();
```

Set your `OPENAI_API_KEY` and `LOGFIRE_TOKEN`, then run with `npx tsx agent.ts`. The example fails unless the
native `ToolLoopAgent` executes `weather`. You'll see spans for the agent, prompt, response, token counts, and
tool call in **Logfire**. Vercel AI SDK runs also appear in the specialized **Agents** view; the
[support matrix](support-matrix.md) shows which columns each view populates.

!!! warning "Common pitfalls"
    - **Register both pieces before running the agent.** Configure Logfire's global tracer provider and attach
      `new OpenTelemetry()` in the agent's `telemetry.integrations`.
    - **Flush on exit.** Short-lived scripts must `await logfire.shutdown()` or the batch processor drops
      unflushed spans.
    - **Content capture.** `recordInputs` / `recordOutputs` default to `true`, so prompts and completions are
      captured. Set them to `false` in `telemetry` to redact sensitive content.

!!! tip "Next.js"
    Install the Next.js OpenTelemetry helper with `npm install @vercel/otel`.
    In Next.js, call `registerOTel(...)` from `@vercel/otel` and
    `registerTelemetry(new OpenTelemetry())` from `ai` and `@ai-sdk/otel` inside the exported `register()`
    function in `instrumentation.ts`. Point the OpenTelemetry Protocol (OTLP) exporter at Logfire with
    `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev` and
    `OTEL_EXPORTER_OTLP_HEADERS='Authorization=<write-token>'`.

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
// Pass resolved.value as the `prompt` to agent.generate().
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
