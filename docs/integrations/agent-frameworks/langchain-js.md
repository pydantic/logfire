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
  @opentelemetry/api @opentelemetry/sdk-trace-base @opentelemetry/exporter-trace-otlp-proto \
  @opentelemetry/context-async-hooks zod
```

(Add `@langchain/langgraph` if you build with LangGraph.)

## Usage

Set the LangSmith environment variables and the OTLP endpoint in your terminal **before starting** the
application. ECMAScript module (ESM) imports run before statements in the importing file, so assigning these
variables inside `index.ts` would be too late.

```bash
export LANGSMITH_OTEL_ENABLED=true
export LANGSMITH_TRACING=true
export LANGSMITH_OTEL_ONLY=true
export OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev/v1/traces
export OTEL_EXPORTER_OTLP_HEADERS="Authorization=$LOGFIRE_WRITE_TOKEN"
npx tsx index.ts
```

Then initialize OpenTelemetry in a small bootstrap file before dynamically importing the module that uses
LangChain:

```typescript title="index.ts"
import { initializeOTEL } from 'langsmith/experimental/otel/setup';

const { DEFAULT_LANGSMITH_SPAN_PROCESSOR } = initializeOTEL();

async function main() {
  try {
    const { runAgent } = await import('./agent.js');
    await runAgent();
  } finally {
    // Flush spans to Logfire before the process exits.
    await DEFAULT_LANGSMITH_SPAN_PROCESSOR.forceFlush?.();
    await DEFAULT_LANGSMITH_SPAN_PROCESSOR.shutdown();
  }
}

main();
```

```typescript title="agent.ts"
import { ChatOpenAI } from '@langchain/openai';
import { createAgent, tool } from 'langchain';
import { z } from 'zod';

export async function runAgent() {
  let toolCalls = 0;
  const lookupIncident = tool(
    ({ incidentId }) => {
      toolCalls += 1;
      return `${incidentId} is resolved; owner=platform-observability`;
    },
    {
      name: 'lookup_incident',
      description: 'Look up an incident by ID.',
      schema: z.object({ incidentId: z.string() }),
    },
  );
  const model = new ChatOpenAI({ model: 'gpt-4o-mini', temperature: 0 });
  const agent = createAgent({ model, tools: [lookupIncident], name: 'incident-agent' });
  const result = await agent.invoke({
    messages: [
      {
        role: 'user',
        content: "Use lookup_incident with incidentId='incident-42', then report the status and owner.",
      },
    ],
  });
  if (toolCalls !== 1) throw new Error(`Expected one tool call, received ${toolCalls}`);
  console.log(result.messages.at(-1)?.content);
}
```

!!! warning "Common pitfalls"
    - **Set configuration before process start.** Static ESM imports are evaluated before code in `index.ts`,
      so set the `LANGSMITH_*` and `OTEL_*` variables in your terminal or deployment environment and keep the
      LangChain imports behind the dynamic import shown above.
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
