---
title: "OpenAI Agents SDK TypeScript compatibility with Pydantic Logfire"
description: "Current support status for sending OpenAI Agents SDK TypeScript agent telemetry to Pydantic Logfire."
---
# OpenAI Agents SDK (TypeScript)

The [OpenAI Agents SDK for TypeScript](https://openai.github.io/openai-agents-js/) (`@openai/agents`) has a
native tracing system, but it does not currently ship an OpenTelemetry exporter or a maintained OpenTelemetry
adapter. There is therefore no complete, supported path for sending its agent and tool traces to **Logfire**.

## Current support

The SDK exposes a `TracingProcessor` interface, so an application can write its own exporter. A small custom
processor can create generic OpenTelemetry spans, but doing that correctly requires mapping every supported
agent, model, tool, handoff, guardrail, error, and streaming event to stable semantic attributes and preserving
their parent-child relationships. A partial bridge can make a trace look plausible while silently losing the
data needed by Logfire's specialized LLMs, Agents, and conversation views.

For that reason, this guide does not recommend a hand-written span bridge or claim full TypeScript support.
Instrumenting the underlying OpenAI model client separately may show model requests in Logfire, but it does not
trace the OpenAI Agents SDK's agent or tool lifecycle.

## Supported alternative

The OpenAI Agents SDK for Python has first-class Logfire instrumentation. If Python is an option, use
[`logfire.instrument_openai_agents()`](../llms/openai.md#openai-agents) to capture its native agent runs, model
calls, and tools without creating synthetic wrapper spans.

Complete TypeScript support requires a maintained OpenTelemetry processor that follows the generative AI
semantic conventions. Until one exists and is verified end to end, treat the TypeScript SDK as **not fully
supported** by Logfire.
