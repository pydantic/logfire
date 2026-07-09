---
title: "Pydantic Logfire Integrations: Mastra"
description: "Send Mastra (TypeScript agent framework) telemetry to Pydantic Logfire using its OpenTelemetry exporter over the OpenTelemetry Protocol."
integration: otel
---
# Mastra

[Mastra](https://mastra.ai/) is a TypeScript agent framework with built-in observability ("AI Tracing"). You
configure it with an `Observability` instance whose exporters send OpenTelemetry data to **Logfire** via the
`@mastra/otel-exporter` package pointed at **Logfire**'s OpenTelemetry Protocol (OTLP) endpoint.

## Installation

Install the packages used by the examples:

=== "npm"

    ```bash
    npm install @mastra/core @mastra/observability @mastra/otel-exporter \
      @opentelemetry/exporter-trace-otlp-proto @opentelemetry/exporter-logs-otlp-proto zod
    ```

=== "pnpm"

    ```bash
    pnpm add @mastra/core @mastra/observability @mastra/otel-exporter \
      @opentelemetry/exporter-trace-otlp-proto @opentelemetry/exporter-logs-otlp-proto zod
    ```

=== "yarn"

    ```bash
    yarn add @mastra/core @mastra/observability @mastra/otel-exporter \
      @opentelemetry/exporter-trace-otlp-proto @opentelemetry/exporter-logs-otlp-proto zod
    ```

=== "bun"

    ```bash
    bun add @mastra/core @mastra/observability @mastra/otel-exporter \
      @opentelemetry/exporter-trace-otlp-proto @opentelemetry/exporter-logs-otlp-proto zod
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
node mastra.mts
```

If you are not using a Node.js version with built-in type stripping, use a TypeScript runner or runtime:

=== "npm"

    ```bash
    npm install --save-dev tsx
    npx tsx mastra.mts
    ```

=== "pnpm"

    ```bash
    pnpm add --save-dev tsx
    pnpm exec tsx mastra.mts
    ```

=== "yarn"

    ```bash
    yarn add --dev tsx
    yarn tsx mastra.mts
    ```

=== "bun"

    ```bash
    bun mastra.mts
    ```

## Usage

```typescript title="mastra.mts"
import { Mastra } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { Observability } from '@mastra/observability';
import { OtelExporter } from '@mastra/otel-exporter';
import { z } from 'zod';

const envSchema = z.object({
  OPENAI_API_KEY: z.string(),
  LOGFIRE_WRITE_TOKEN: z.string(),
});

const env = envSchema.parse(process.env);

const weatherTool = createTool({
  id: 'get-weather',
  description: 'Get current weather for a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

const weatherAgent = new Agent({
  id: 'weather-agent',
  name: 'Weather Agent',
  instructions:
    'You are a concise weather assistant. Ask for a location if none is provided. Use the weatherTool to fetch current weather data.',
  model: 'openai/gpt-5.4-mini',
  tools: { weatherTool },
});

const observability = new Observability({
  configs: {
    otel: {
      serviceName: 'mastra-weather-agent',
      exporters: [
        new OtelExporter({
          provider: {
            custom: {
              endpoint: 'https://logfire-us.pydantic.dev/v1/traces',
              protocol: 'http/protobuf',
              headers: {
                Authorization: env.LOGFIRE_WRITE_TOKEN,
              },
            },
          },
        }),
      ],
    },
  },
});

const mastra = new Mastra({
  agents: { weatherAgent },
  observability,
});

async function main() {
  try {
    const result = await mastra.getAgent('weatherAgent').generate('What is the weather in London?');
    console.log(result.text);
  } finally {
    await mastra.observability.flush();
  }
}

await main();
```

Set `OPENAI_API_KEY` from OpenAI and set `LOGFIRE_WRITE_TOKEN` to a Logfire project write token from your
project settings page in Logfire, then run. In Logfire, the trace starts with an `invoke_agent` span, then shows
the model call, model-step spans, and the `execute_tool` span for the weather tool.

!!! info "Details"
    - The custom OTLP exporter needs the full `/v1/traces` URL and the raw Logfire write token as the
      `Authorization` header value, without a `Bearer` prefix.
    - For EU projects, use `https://logfire-eu.pydantic.dev/v1/traces` for OTLP export.
    - `mastra.observability.flush()` waits for queued telemetry to be sent. These examples call it because the
      script exits immediately after one agent run. You usually do not need this when running a long-lived Mastra
      process such as `mastra dev`; for servers and workers, flush from your shutdown handler.

## Use the Logfire AI Gateway

You can also route the model call through the [Logfire AI Gateway](../../reference/advanced/gateway/index.md).
Use this when you want Logfire-managed provider keys, spending limits, routing, and gateway request telemetry
for the same Mastra agent.

The gateway exposes an OpenAI-compatible route, so Mastra can keep using the AI SDK OpenAI provider. Use a
**gateway API key** from the Gateway **API Keys** tab for the model call and a **Logfire write token** from your
project settings page in Logfire for OTLP export:

=== "npm"

    ```bash
    npm install @ai-sdk/openai
    ```

=== "pnpm"

    ```bash
    pnpm add @ai-sdk/openai
    ```

=== "yarn"

    ```bash
    yarn add @ai-sdk/openai
    ```

=== "bun"

    ```bash
    bun add @ai-sdk/openai
    ```

```typescript title="mastra-gateway.mts"
import { createOpenAI } from '@ai-sdk/openai';
import { Mastra } from '@mastra/core';
import { Agent } from '@mastra/core/agent';
import { createTool } from '@mastra/core/tools';
import { Observability } from '@mastra/observability';
import { OtelExporter } from '@mastra/otel-exporter';
import { z } from 'zod';

const envSchema = z.object({
  LOGFIRE_GATEWAY_API_KEY: z.string(),
  LOGFIRE_WRITE_TOKEN: z.string(),
});

const env = envSchema.parse(process.env);

const gateway = createOpenAI({
  apiKey: env.LOGFIRE_GATEWAY_API_KEY,
  baseURL: 'https://gateway-us.pydantic.dev/proxy/openai',
});

const weatherTool = createTool({
  id: 'get-weather',
  description: 'Get current weather for a location',
  inputSchema: z.object({ location: z.string().describe('City name') }),
  outputSchema: z.object({ output: z.string() }),
  execute: async ({ location }) => ({ output: `The weather in ${location} is sunny` }),
});

const weatherAgent = new Agent({
  id: 'weather-agent',
  name: 'Weather Agent',
  instructions:
    'You are a concise weather assistant. Ask for a location if none is provided. Use the weatherTool to fetch current weather data.',
  model: gateway('gpt-5.4-mini'),
  tools: { weatherTool },
});

const observability = new Observability({
  configs: {
    otel: {
      serviceName: 'mastra-gateway-weather-agent',
      exporters: [
        new OtelExporter({
          provider: {
            custom: {
              endpoint: 'https://logfire-us.pydantic.dev/v1/traces',
              protocol: 'http/protobuf',
              headers: {
                Authorization: env.LOGFIRE_WRITE_TOKEN,
              },
            },
          },
        }),
      ],
    },
  },
});

const mastra = new Mastra({
  agents: { weatherAgent },
  observability,
});

async function main() {
  try {
    const result = await mastra.getAgent('weatherAgent').generate('What is the weather in London?');
    console.log(result.text);
  } finally {
    await mastra.observability.flush();
  }
}

await main();
```

Set `LOGFIRE_GATEWAY_API_KEY` and `LOGFIRE_WRITE_TOKEN`, then run.

!!! info "Details"
    - The example uses the US gateway route. For EU projects, set `baseURL` to
      `https://gateway-eu.pydantic.dev/proxy/openai`.
    - The OTLP telemetry exporter still sends traces to Logfire. For EU projects, use
      `https://logfire-eu.pydantic.dev/v1/traces` for OTLP export.
    - `mastra.observability.flush()` waits for queued telemetry to be sent. This example calls it because the
      script exits immediately after one agent run. You usually do not need this when running a long-lived Mastra
      process such as `mastra dev`; for servers and workers, flush from your shutdown handler.

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
