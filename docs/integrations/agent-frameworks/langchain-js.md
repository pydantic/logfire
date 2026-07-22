---
title: "Pydantic Logfire Integrations: LangChain.js"
description: "Send LangChain.js and LangGraph.js telemetry to Pydantic Logfire via the LangSmith OpenTelemetry exporter over OTLP."
integration: otel
---
# LangChain.js / LangGraph.js

[LangChain.js](https://js.langchain.com/) (and [LangGraph.js](https://langchain-ai.github.io/langgraphjs/))
trace through **LangSmith**, whose JS SDK ships native OpenTelemetry export. Point that OTLP exporter at
**Logfire** and your traces flow straight in — no Logfire-specific JS code required.

## Installation

```bash
npm install langchain @langchain/core @langchain/openai langsmith \
  @opentelemetry/api @opentelemetry/sdk-trace-base @opentelemetry/exporter-trace-otlp-proto
```

(Add `@langchain/langgraph` if you build with LangGraph.)

## Usage

Set the LangSmith env vars and the OTLP endpoint **before importing** any LangChain code, and call
`initializeOTEL()` once at process start:

```typescript title="index.ts"
// Run with: OPENAI_API_KEY=... LOGFIRE_WRITE_TOKEN=... npx tsx index.ts

// 1. Env MUST be set before importing langchain/langsmith.
process.env.LANGSMITH_OTEL_ENABLED = 'true';
process.env.LANGSMITH_TRACING = 'true';
process.env.LANGSMITH_OTEL_ONLY = 'true';
process.env.OTEL_EXPORTER_OTLP_ENDPOINT = 'https://logfire-us.pydantic.dev/v1/traces';
process.env.OTEL_EXPORTER_OTLP_HEADERS = `Authorization=${process.env.LOGFIRE_WRITE_TOKEN}`;

// 2. Initialize OTel before importing LangChain.
import { initializeOTEL } from 'langsmith/experimental/otel/setup';
const { DEFAULT_LANGSMITH_SPAN_PROCESSOR } = initializeOTEL();

import { ChatOpenAI } from '@langchain/openai';
import { HumanMessage } from '@langchain/core/messages';

async function main() {
  const model = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
  const res = await model.invoke([new HumanMessage("What's 123 + 456?")]);
  console.log(res.content);

  // 3. Flush spans to Logfire before the process exits.
  await DEFAULT_LANGSMITH_SPAN_PROCESSOR.forceFlush?.();
  await DEFAULT_LANGSMITH_SPAN_PROCESSOR.shutdown();
}

main();
```

For a LangGraph agent, swap the model call for `createReactAgent({ llm: model, tools: [...] })` from
`@langchain/langgraph/prebuilt` and `.invoke(...)` it — the same OTel setup captures the graph and tool spans.

!!! warning "Common pitfalls"
    - **Import order is critical.** The `LANGSMITH_*` env vars and `initializeOTEL()` must run before importing
      `langchain` / `langsmith` / `@langchain/*`.
    - **Endpoint URL.** The LangSmith JS exporter treats `OTEL_EXPORTER_OTLP_ENDPOINT` as the full URL, so give
      it the `/v1/traces` form (use `logfire-eu.pydantic.dev` for the EU region).
    - **Header format.** `Authorization=<write-token>` — the raw Logfire write token, no `Bearer` prefix.
    - **`LANGSMITH_OTEL_ONLY=true`** stops LangSmith from also shipping traces to its own backend, so you don't
      need a `LANGSMITH_API_KEY`.
    - **Flush on exit.** Short-lived scripts and serverless must `await ...shutdown()` (or `forceFlush()`) or
      spans are lost. Use the HTTP/protobuf exporter (`@opentelemetry/exporter-trace-otlp-proto`), not gRPC.

## Managed prompts

Author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and
fetch them with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/):

```typescript
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

const systemPrompt = defineTemplateVar<string, { topic: string }>('prompt__system', {
  default: 'You are a helpful assistant about {{topic}}.',
  templateInputsSchema: {
    type: 'object',
    properties: { topic: { type: 'string' } },
    required: ['topic'],
  },
});

const resolved = await systemPrompt.get({ topic: 'math' });
// Use resolved.value as the SystemMessage content for your chain or agent.
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
