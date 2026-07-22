---
title: "Pydantic Logfire Integrations: OpenAI Agents SDK (TypeScript)"
description: "Send OpenAI Agents SDK (TypeScript / @openai/agents) traces to Pydantic Logfire by bridging the Agents tracing API to OpenTelemetry."
integration: otel
---
# OpenAI Agents SDK (TypeScript)

The [OpenAI Agents SDK for TypeScript](https://openai.github.io/openai-agents-js/) (`@openai/agents`) has its
own tracing system but ships no built-in OpenTelemetry exporter. To send its traces to **Logfire**, configure
the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/) (which registers a global
OpenTelemetry tracer provider exporting to **Logfire**) and add a small custom `TracingProcessor` that turns
Agents spans into OpenTelemetry spans.

!!! note
    The first-class `logfire.instrument_openai_agents()` helper on the [OpenAI](../llms/openai.md) page is
    **Python-only**. For the TypeScript SDK, the bridge below is the working pattern.

## Installation

```bash
npm install @openai/agents @pydantic/logfire-node @opentelemetry/api zod
```

!!! note "Zod version"
    `@openai/agents` 0.11+ requires **Zod v4** (`zod@^4`). Older 0.0.x releases required pinning to
    `zod@<=3.25`. Match the Zod version to your installed `@openai/agents`.

## Usage

```typescript title="index.ts"
// Run with: OPENAI_API_KEY=... LOGFIRE_TOKEN=... node --experimental-strip-types index.ts
import * as logfire from '@pydantic/logfire-node';
import { trace, SpanStatusCode } from '@opentelemetry/api';
import { Agent, run, addTraceProcessor } from '@openai/agents';
import type { Span, Trace } from '@openai/agents';

// 1. Configure Logfire -> registers a global OTel tracer provider exporting to Logfire.
//    Reads LOGFIRE_TOKEN from env; region (US/EU) is inferred from the token.
logfire.configure({ serviceName: 'agents-demo' });

const tracer = trace.getTracer('openai-agents');

// 2. Bridge: turn each Agents span into an OTel span on Logfire's provider.
const otelSpans = new Map<string, ReturnType<typeof tracer.startSpan>>();
addTraceProcessor({
  async onTraceStart(_t: Trace) {},
  async onSpanStart(span: Span<any>) {
    const s = tracer.startSpan(span.spanData?.type ?? 'agent.span');
    s.setAttribute('agents.span_id', span.spanId);
    otelSpans.set(span.spanId, s);
  },
  async onSpanEnd(span: Span<any>) {
    const s = otelSpans.get(span.spanId);
    if (!s) return;
    s.setAttribute('agents.data', JSON.stringify(span.spanData ?? {}));
    if (span.error) s.setStatus({ code: SpanStatusCode.ERROR, message: String(span.error) });
    s.end();
    otelSpans.delete(span.spanId);
  },
  async onTraceEnd(_t: Trace) {},
  async forceFlush() {},
  async shutdown() {},
});

// 3. Tiny agent + one LLM call.
const agent = new Agent({ name: 'Haiku bot', instructions: 'Reply with one short haiku.' });
const result = await run(agent, 'Write a haiku about telemetry.');
console.log(result.finalOutput);

await logfire.forceFlush?.(); // ensure spans are exported before exit
```

`addTraceProcessor` keeps OpenAI's own default trace backend too; use `setTraceProcessors([...])` instead to
send **only** to **Logfire**.

!!! warning "Common pitfalls"
    - **Configure Logfire first**, before registering the bridge, so the global provider exists when
      `trace.getTracer()` is called. **Flush on exit** or short-lived scripts drop spans.
    - **`OPENAI_API_KEY` is required** for the model call (and for the SDK's default trace exporter, unless you
      use `setTraceProcessors`).
    - **Tracing is on by default** in Node/Deno/Bun, disabled in browsers and when `NODE_ENV=test`. Disable
      globally with `OPENAI_AGENTS_DISABLE_TRACING=1`.
    - **ESM / Node version.** Both packages are ESM — use a recent Node LTS with `"type": "module"` (or `tsx`).
    - The bridge above is minimal. For production fidelity (parent/child nesting via `span.parentId`, GenAI
      semantic-convention attributes), expand it to set OTel context from each Agents span's `parentId`.

If you prefer pure env-var OTLP config instead of `@pydantic/logfire-node`, point any standard OTel `NodeSDK`
at `OTEL_EXPORTER_OTLP_ENDPOINT=https://logfire-us.pydantic.dev` with
`OTEL_EXPORTER_OTLP_HEADERS='Authorization=your-write-token'`, then register the bridge processor.

## Managed prompts

Author and version prompts in [Prompt Management](../../reference/advanced/prompt-management/index.md) and
fetch them with the [Logfire TypeScript SDK](https://pydantic.dev/docs/logfire/typescript-sdk/):

```typescript
import { defineTemplateVar } from '@pydantic/logfire-node/vars';

const instructions = defineTemplateVar<string, { style: string }>('prompt__agent_instructions', {
  default: 'Reply with one short {{style}}.',
  templateInputsSchema: {
    type: 'object',
    properties: { style: { type: 'string' } },
    required: ['style'],
  },
});

const resolved = await instructions.get({ style: 'haiku' });
const agent = new Agent({ name: 'Poet', instructions: resolved.value });
```

See [Use Prompts in Your Application](../../reference/advanced/prompt-management/application.md) for the full
workflow.
