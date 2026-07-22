---
title: "Pydantic Logfire Integrations: VoltAgent"
description: "Send VoltAgent (TypeScript agent framework) telemetry to Pydantic Logfire using its OpenTelemetry span processors over OTLP."
integration: otel
---
# VoltAgent

[VoltAgent](https://voltagent.dev/) is a TypeScript agent framework whose observability is built on
OpenTelemetry. You construct a `VoltAgentObservability` with span processors that wrap a standard OTLP exporter
pointed at **Logfire**, then pass it to `new VoltAgent({ ... })`.

## Installation

```bash
npm install @voltagent/core @ai-sdk/openai \
  @opentelemetry/sdk-trace-base @opentelemetry/exporter-trace-otlp-proto
```

## Usage

```typescript title="agent.ts"
import { VoltAgent, Agent, VoltAgentObservability } from '@voltagent/core';
import { openai } from '@ai-sdk/openai';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';

const logfireExporter = new OTLPTraceExporter({
  url: 'https://logfire-us.pydantic.dev/v1/traces', // full path; EU: logfire-eu.pydantic.dev
  headers: { Authorization: process.env.LOGFIRE_WRITE_TOKEN! }, // raw token, no "Bearer"
});

const observability = new VoltAgentObservability({
  spanProcessors: [new BatchSpanProcessor(logfireExporter)],
});

const agent = new Agent({
  name: 'weather-agent',
  instructions: 'A helpful assistant that answers questions.',
  model: openai('gpt-4o-mini'),
});

new VoltAgent({
  agents: { agent },
  observability,
});

const res = await agent.generateText('What is a good city to visit in spring?');
console.log(res.text);
```

Set `OPENAI_API_KEY` and `LOGFIRE_WRITE_TOKEN`, then run. The agent run and model call appear in **Logfire**.

!!! warning "Common pitfalls"
    - **Full `/v1/traces` URL.** When you pass `url` explicitly to `OTLPTraceExporter`, it does not append the
      path — give the full `/v1/traces` URL. The `Authorization` header value is the raw write token.
    - **VoltOps is a separate path.** The built-in VoltOps remote export
      (`VOLTAGENT_PUBLIC_KEY` / `VOLTAGENT_SECRET_KEY`) is independent; for **Logfire** use the explicit
      `spanProcessors` route shown here.
    - Adding `spanProcessors` doesn't disable VoltAgent's local dev console — local debugging stays available
      alongside the **Logfire** export.

## Managed prompts

Author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and
fetch them with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/):

```typescript
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

const instructionsVar = defineTemplateVar<string, { role: string }>('prompt__agent_instructions', {
  default: 'A helpful assistant that answers questions about {{role}}.',
  templateInputsSchema: {
    type: 'object',
    properties: { role: { type: 'string' } },
    required: ['role'],
  },
});

const resolved = await instructionsVar.get({ role: 'travel' });
// Use resolved.value as the Agent's `instructions`.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
