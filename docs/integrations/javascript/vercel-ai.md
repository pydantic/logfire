---
title: Pydantic Logfire Vercel AI SDK Integration
description: "Track LLM calls, token usage, tool invocations, and response times in AI applications built with the Vercel AI SDK using Logfire."
integration: logfire
---
# Vercel AI SDK

Logfire works well with AI applications built with the [Vercel AI SDK](https://ai-sdk.dev/). Track LLM calls, token usage, tool invocations, and response times across any supported model provider.

## Node.js Scripts

For standalone Node.js scripts, use the `@pydantic/logfire-node` package combined with the Vercel AI SDK.

### Installation

```bash
npm install @pydantic/logfire-node ai @ai-sdk/your-provider
```

Replace `@ai-sdk/your-provider` with the provider package you're using (e.g., `@ai-sdk/openai`, `@ai-sdk/anthropic`, `@ai-sdk/google`).

### Setup

**1. Create an instrumentation file**

Create an `instrumentation.ts` file that configures Logfire:

```typescript
import logfire from "@pydantic/logfire-node";

logfire.configure({
  token: "your-write-token",
  serviceName: "my-ai-app",
  serviceVersion: "1.0.0",
});
```

You can also use the `LOGFIRE_TOKEN` environment variable instead of passing the token directly.

**2. Import instrumentation first**

In your main script, import the instrumentation file before other imports:

```typescript
import "./instrumentation.ts";
import { generateText } from "ai";
import { yourProvider } from "@ai-sdk/your-provider";

// Your AI code here
```

## Next.js

For Next.js applications, use [Vercel's built-in OpenTelemetry support](https://nextjs.org/docs/app/guides/open-telemetry) with environment variables pointing to Logfire.

### Installation

```bash
npm install @vercel/otel @opentelemetry/api ai @ai-sdk/your-provider
```

### Setup

**1. Add environment variables**

Add these to your `.env.local` file (or your deployment environment):

```
OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-api.pydantic.dev
OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'
```

**2. Create the instrumentation file**

Create `instrumentation.ts` in your project root (or `src` directory if using that structure):

```typescript
import { registerOTel } from "@vercel/otel";

export function register() {
  registerOTel({ serviceName: "my-nextjs-app" });
}
```

This file must be in the root directory, not inside `app` or `pages`. See the [Vercel instrumentation docs](https://vercel.com/docs/tracing/instrumentation) for more configuration options.

**3. Enable telemetry on AI SDK calls**

See the [Enabling Telemetry](#enabling-telemetry) section below.

## Enabling Telemetry

The Vercel AI SDK uses [OpenTelemetry for telemetry](https://ai-sdk.dev/docs/ai-sdk-core/telemetry). To capture traces, add the `experimental_telemetry` option to your AI SDK function calls:

```typescript
const result = await generateText({
  model: yourModel("model-name"),
  prompt: "Your prompt here",
  experimental_telemetry: { isEnabled: true },
});
```

This option works with all AI SDK core functions:

- `generateText` / `streamText`
- `generateObject` / `streamObject`
- `embed` / `embedMany`

## Example: Text Generation with Tools

Here's a complete example showing text generation with a tool and telemetry enabled:

```typescript
import { generateText, tool } from "ai";
import { yourProvider } from "@ai-sdk/your-provider";
import { z } from "zod";

const result = await generateText({
  model: yourProvider("model-name"),
  experimental_telemetry: { isEnabled: true },
  tools: {
    weather: tool({
      description: "Get the weather in a location",
      inputSchema: z.object({
        location: z.string().describe("The location to get the weather for"),
      }),
      execute: async ({ location }) => ({
        location,
        temperature: 72 + Math.floor(Math.random() * 21) - 10,
      }),
    }),
  },
  prompt: "What is the weather in San Francisco?",
});

console.log(result.text);
```

For Node.js scripts, remember to import your instrumentation file at the top of your entry point.

## What You'll See in Logfire

When telemetry is enabled, Logfire captures a hierarchical trace of your AI operations:

- **Parent span** for the AI operation (e.g., `ai.generateText`)
  - **Provider call spans** showing the actual LLM API calls
  - **Tool call spans** for each tool invocation

The captured data includes:

- Prompts and responses
- Model information and provider details
- Token usage (input and output tokens)
- Timing information
- Tool call arguments and results

## Advanced Options

The `experimental_telemetry` option accepts additional configuration:

```typescript
experimental_telemetry: {
  isEnabled: true,
  functionId: "weather-lookup",
  metadata: {
    userId: "user-123",
    environment: "production",
  },
}
```

- `functionId` - A custom identifier that appears in span names, useful for distinguishing different use cases
- `metadata` - Custom key-value pairs attached to the telemetry spans
