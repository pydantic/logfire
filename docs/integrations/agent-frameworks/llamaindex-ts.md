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
npm install @traceloop/node-server-sdk llamaindex @llamaindex/openai @llamaindex/workflow zod
```

## Usage

Initialize OpenLLMetry before dynamically importing LlamaIndex. This lets OpenLLMetry install its module hooks
before the framework loads:

```typescript title="main.ts"
import * as traceloop from '@traceloop/node-server-sdk';
import { z } from 'zod';

traceloop.initialize({
  appName: 'llamaindex-ts-logfire',
  disableBatch: true, // flush immediately (dev only)
  baseUrl: 'https://logfire-us.pydantic.dev', // EU: https://logfire-eu.pydantic.dev
  // Use `headers` (raw token), NOT `apiKey` — `apiKey` would send "Authorization: Bearer <token>",
  // which Logfire rejects.
  headers: { Authorization: process.env.LOGFIRE_TOKEN ?? '' },
});

async function main() {
  const [LlamaIndex, { openai }, { agent }] = await Promise.all([
    import('llamaindex'),
    import('@llamaindex/openai'),
    import('@llamaindex/workflow'),
  ]);

  let toolCalls = 0;
  const lookupIncident = LlamaIndex.tool({
    name: 'lookup_incident',
    description: 'Look up an incident by ID.',
    parameters: z.object({ incidentId: z.string() }),
    execute: ({ incidentId }) => {
      toolCalls += 1;
      return `${incidentId} is resolved; owner=platform-observability`;
    },
  });

  const myAgent = agent({
    llm: openai({ model: 'gpt-4o-mini' }),
    tools: [lookupIncident],
  });

  const result = await myAgent.run(
    "Use lookup_incident with incidentId='incident-42', then report the status and owner.",
  );
  if (toolCalls !== 1) throw new Error(`Expected one tool call, received ${toolCalls}`);
  console.log(result.data.result);

  await traceloop.forceFlush(); // ensure spans ship before exit
}

main();
```

Run it with `LOGFIRE_TOKEN=<write-token> OPENAI_API_KEY=<key> npx tsx main.ts`, then open the Live view of your
project. The example fails unless the native LlamaIndex agent executes `lookup_incident`; the resulting trace
contains the agent run, its model calls, and that tool call.

!!! warning "Common pitfalls"
    - **Import order is the #1 issue.** `traceloop.initialize()` must run before `llamaindex` and
      `@llamaindex/openai` load. Keep those imports dynamic and after initialization as shown.
    - **`baseUrl`, not the full path.** Give the bare host; the SDK appends `/v1/traces`. The auth header value
      is the raw Logfire write token (no `Bearer` prefix). The env-var equivalent is
      `TRACELOOP_BASE_URL` + `TRACELOOP_HEADERS="Authorization=<token>"`.
    - **`disableBatch: true` is dev-only.** In production, drop it and rely on graceful shutdown / `forceFlush()`.

## Managed prompts

You can author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md)
and fetch them at runtime with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/)
using `defineTemplateVar`:

```typescript
import * as logfire from '@pydantic/logfire-node';
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

logfire.configure({ serviceName: 'llamaindex-ts-logfire' });

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
