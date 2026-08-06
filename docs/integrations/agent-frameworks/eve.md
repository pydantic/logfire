---
title: Trace Eve agents with Pydantic Logfire
description: "Send Eve agent turns, model calls, tool calls, token usage, and conversations to Pydantic Logfire."
integration: otel
---
# Trace Eve agents with Pydantic Logfire

See what an [Eve](https://vercel.com/eve) agent did, which model and tools it called, how long each step took,
and how many tokens the model used.

Eve emits [OpenTelemetry](https://opentelemetry.io/) (OTel), the open industry standard for collecting
traces, metrics, and logs. Eve discovers `agent/instrumentation.ts` automatically and runs it before the
agent starts. You configure that file to send Eve's traces to Logfire.

## Before you start

You need:

- An Eve project. Run `npx eve@latest init my-agent` to create one.
- A Logfire project and write token. Copy the token from **Project → Settings → Write tokens**.
- Credentials for your chosen model, configured through `eve link` or the model provider's environment
  variables.

Install the packages that connect Eve's OpenTelemetry data to Logfire:

```bash
npm install @vercel/otel @opentelemetry/exporter-trace-otlp-proto \
  @opentelemetry/sdk-trace-base
```

## Send Eve traces to Logfire

Create `agent/instrumentation.ts`:

```typescript title="agent/instrumentation.ts"
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-proto';
import { SimpleSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { registerOTel } from '@vercel/otel';
import { defineInstrumentation } from 'eve/instrumentation';

const writeToken = process.env.LOGFIRE_WRITE_TOKEN;
if (!writeToken) {
  throw new Error('LOGFIRE_WRITE_TOKEN is required');
}

export default defineInstrumentation({
  setup: ({ agentName }) =>
    registerOTel({
      serviceName: agentName,
      spanProcessors: [
        new SimpleSpanProcessor(
          new OTLPTraceExporter({
            url: 'https://logfire-us.pydantic.dev/v1/traces',
            headers: {
              Authorization: writeToken,
            },
          }),
        ),
      ],
    }),
  recordInputs: true,
  recordOutputs: true,
});
```

The example sends each completed span (one unit of work: a single operation, with a name, a start, and a
duration) immediately. This is important for Eve agents running on Vercel Workflow because a serverless instance
can pause before a batch of completed spans is sent.

Use `https://logfire-eu.pydantic.dev/v1/traces` instead if your Logfire project is in the European Union region.

!!! warning "Prompts and responses leave your application"
    With `recordInputs` and `recordOutputs` set to `true`, Eve sends model inputs, outputs, tool arguments, and
    tool results to Logfire. This data is stored in your Logfire project. Set either option to `false` before
    sending sensitive data that you do not want Logfire to store.

Set the write token in your terminal, then start the agent:

```bash
export LOGFIRE_WRITE_TOKEN='<your-write-token>'
npm run dev
```

Do not put the token in `agent/instrumentation.ts` or commit it to source control. For a Vercel deployment,
add `LOGFIRE_WRITE_TOKEN` in the project's environment-variable settings.

## Verify the trace

Send the agent a message such as:

```text
Reply with EVE_LOGFIRE_OK.
```

Open your Logfire project's **Live** view. You should see an Eve turn containing the agent invocation, model
step, and model call. Open the trace to inspect the input, `EVE_LOGFIRE_OK` response, duration, model, and
token usage. The exact span names depend on your Eve and artificial intelligence (AI) software development kit
(SDK) versions.

The large language model (LLM) call also appears on the **LLMs** page. Logfire currently detects Eve agent runs
and their conversations, but aggregate Agent metrics can miss turns or count repeated token attributes more
than once. Use the **LLMs** page for exact model-call usage while
[full Eve Agent analytics support](https://github.com/pydantic/platform/issues/28737) is in progress. Eve runs
also appear in the specialized **Agents** view; the [support matrix](support-matrix.md) shows which columns each
view populates.

## Troubleshoot missing traces

- **No Eve service appears in Live:** confirm the file is exactly `agent/instrumentation.ts`, default-exports
  `defineInstrumentation(...)`, and is present in the deployed build. Run `npx eve info` to inspect Eve's
  discovery diagnostics.
- **The exporter returns 401:** pass the raw write token as the `Authorization` header value. Do not add a
  `Bearer` prefix.
- **Local traces work but some Vercel Workflow traces are missing:** keep `SimpleSpanProcessor` as shown
  above. A timer-based batch can remain in memory when the serverless instance pauses.
- **The service appears as the wrong name:** Eve derives `agentName` from the package name, falling back to
  the application directory. Set a meaningful `name` in `package.json`.

## Next steps

Add tools or subagents to your Eve project and repeat the verification. Their work appears as nested spans in
the same trace, so you can see which step caused a slow response or error.
