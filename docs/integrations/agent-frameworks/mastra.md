---
title: "Pydantic Logfire Integrations: Mastra"
description: "Send Mastra (TypeScript agent framework) telemetry to Pydantic Logfire using its OpenTelemetry exporter over OTLP."
integration: otel
---
# Mastra

[Mastra](https://mastra.ai/) is a TypeScript agent framework with built-in observability ("AI Tracing"). You
configure it with an `Observability` instance whose exporters send OpenTelemetry data to **Logfire** via the
`@mastra/otel-exporter` package pointed at **Logfire**'s OTLP endpoint.

## Installation

```bash
npm install @mastra/core @mastra/observability @mastra/otel-exporter \
  @opentelemetry/exporter-trace-otlp-proto @ai-sdk/openai zod
```

## Usage

```typescript title="mastra.ts"
import { Mastra } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { Observability } from '@mastra/observability';
import { OtelExporter } from '@mastra/otel-exporter';
import { openai } from '@ai-sdk/openai';
import { z } from 'zod';

const weatherTool = createTool({
  id: 'get-weather',
  description: 'Get the weather for a city',
  inputSchema: z.object({ city: z.string() }),
  execute: async ({ context }) => ({ city: context.city, tempC: 21 }),
});

const agent = new Agent({
  name: 'weather-agent',
  instructions: 'You are a helpful weather assistant. Use the tool.',
  model: openai('gpt-4o-mini'),
  tools: { weatherTool },
});

export const mastra = new Mastra({
  agents: { agent },
  observability: new Observability({
    configs: {
      otel: {
        serviceName: 'mastra-weather-agent',
        exporters: [
          new OtelExporter({
            provider: {
              custom: {
                // Give the full /v1/traces path for the custom provider.
                endpoint: 'https://logfire-us.pydantic.dev/v1/traces',
                protocol: 'http/protobuf',
                headers: { Authorization: process.env.LOGFIRE_WRITE_TOKEN! },
              },
            },
          }),
        ],
      },
    },
  }),
});

const res = await mastra.getAgent('agent').generate('Weather in Paris?');
console.log(res.text);
```

Set `OPENAI_API_KEY` and `LOGFIRE_WRITE_TOKEN`, then run. The agent run, model call, and tool call appear as a
nested trace in **Logfire**.

!!! warning "Common pitfalls"
    - **Use the current `observability` config.** The older top-level `telemetry: {}` (`OtelConfig`) on
      `new Mastra()` is deprecated; the `Observability` + `OtelExporter` shape shown here is current.
    - **Full `/v1/traces` URL for the `custom` provider**, and the raw write token as the `Authorization`
      header value (no `Bearer`). Use `logfire-eu.pydantic.dev` for the EU region.
    - **Install the matching low-level exporter.** `http/protobuf` needs
      `@opentelemetry/exporter-trace-otlp-proto`; gRPC needs `@opentelemetry/exporter-trace-otlp-grpc` +
      `@grpc/grpc-js`.

## Managed prompts

Author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and
fetch them with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/):

```typescript
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

const instructionsVar = defineTemplateVar<string, { role: string }>('prompt__agent_instructions', {
  default: 'You are a helpful {{role}}.',
  templateInputsSchema: {
    type: 'object',
    properties: { role: { type: 'string' } },
    required: ['role'],
  },
});

const resolved = await instructionsVar.get({ role: 'weather assistant' });
// Use resolved.value as the Agent's `instructions`.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
