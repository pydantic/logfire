---
title: "Pydantic Logfire Integrations: LlamaIndex.TS"
description: "Send LlamaIndex.TS (TypeScript) agent telemetry to Pydantic Logfire via OpenLLMetry / Traceloop over OTLP."
integration: otel
---
# LlamaIndex.TS

[LlamaIndex.TS](https://developers.llamaindex.ai/typescript) is the TypeScript edition of LlamaIndex. Its
documented observability path is [OpenLLMetry / Traceloop](https://github.com/traceloop/openllmetry-js), which
is built on OpenTelemetry and emits standard OTLP — so you point its exporter at **Logfire**'s OTLP endpoint
with your [write token](../../how-to-guides/create-write-tokens.md).

## Installation

```bash
npm install @traceloop/node-server-sdk llamaindex @llamaindex/openai @llamaindex/workflow
```

## Usage

Keep the instrumentation in a **separate file that is imported first**, so it loads before any LlamaIndex code:

```typescript title="instrumentation.ts"
// MUST be imported before llamaindex
import * as traceloop from '@traceloop/node-server-sdk';
import * as LlamaIndex from 'llamaindex';

traceloop.initialize({
  appName: 'llamaindex-ts-logfire',
  disableBatch: true, // flush immediately (dev only)
  baseUrl: 'https://logfire-us.pydantic.dev', // EU: https://logfire-eu.pydantic.dev
  // Use `headers` (raw token), NOT `apiKey` — `apiKey` would send "Authorization: Bearer <token>",
  // which Logfire rejects. The `headers` format is comma-separated `key=value` pairs.
  headers: `Authorization=${process.env.LOGFIRE_TOKEN}`,
  // Pass the framework module explicitly so ESM auto-patching attaches (camelCase key `llamaIndex`):
  instrumentModules: {
    llamaIndex: LlamaIndex,
  },
});
```

```typescript title="main.ts"
import './instrumentation'; // FIRST — registers the OTel hooks
import { agent } from '@llamaindex/workflow';
import { openai } from '@llamaindex/openai';
import * as traceloop from '@traceloop/node-server-sdk';

async function main() {
  const myAgent = agent({
    llm: openai({ model: 'gpt-4o-mini' }),
    tools: [],
  });

  const result = await myAgent.run('Say hello to Logfire in one sentence.');
  console.log(result.data.result);

  await traceloop.forceFlush(); // ensure spans ship before exit
}

main();
```

Run it with `LOGFIRE_TOKEN=<write-token> OPENAI_API_KEY=<key> npx tsx main.ts`, then open the Live view of your
project — you'll see the agent run, its LLM calls, and any tool calls as a nested trace.

!!! warning "Common pitfalls"
    - **Import order is the #1 issue.** `traceloop.initialize()` must run before `llamaindex` /
      `@llamaindex/openai` are imported. Use a dedicated `instrumentation.ts` imported on the first line (or
      Node's `--import ./instrumentation.ts`).
    - **`instrumentModules` is mandatory under ESM/bundlers.** Auto-patching relies on intercepting `require`;
      under ESM the modules are already resolved, so pass them explicitly as shown.
    - **`baseUrl`, not the full path.** Give the bare host; the SDK appends `/v1/traces`. The auth header value
      is the raw Logfire write token (no `Bearer` prefix). The env-var equivalent is
      `TRACELOOP_BASE_URL` + `TRACELOOP_HEADERS="Authorization=<token>"`.
    - **`disableBatch: true` is dev-only.** In production, drop it and rely on graceful shutdown / `forceFlush()`.

## Managed prompts

You can author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md)
and fetch them at runtime with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/)
using `defineTemplateVar`:

```typescript
import { configure } from '@pydantic/logfire-node';
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

configure({ serviceName: 'llamaindex-ts-logfire' });

const systemPrompt = defineTemplateVar<string, { topic: string }>('prompt__system', {
  default: 'You are a helpful assistant about {{topic}}.',
  templateInputsSchema: {
    type: 'object',
    properties: { topic: { type: 'string' } },
    required: ['topic'],
  },
});

const resolved = await systemPrompt.get({ topic: 'observability' });
// Pass resolved.value into your agent's system prompt.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the
production workflow (promoting versions, rollout targeting).
