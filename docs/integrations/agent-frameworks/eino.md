---
title: "Eino (Go) compatibility with Pydantic Logfire"
description: "Current support status for sending CloudWeGo Eino agent and tool telemetry to Pydantic Logfire."
---
# Eino (Go)

[Eino](https://www.cloudwego.io/docs/eino/) is ByteDance/CloudWeGo's Go framework for large language model
(LLM) and agent applications. Eino can run native ReAct agents and tools, but it does not currently provide a
complete, general-purpose OpenTelemetry integration that can send those agent operations to **Logfire**.

## Current support

Eino's observability API is based on callback handlers. The official handlers in `eino-ext` target specific
vendors, including APMPlus, CozeLoop, Langfuse, and LangSmith. Its OpenTelemetry helper configures a standard
tracer provider, but it does not turn Eino agent, model, and tool callbacks into spans.

That means:

- Pointing an OpenTelemetry Protocol (OTLP) exporter at Logfire does not instrument an Eino agent by itself.
- A native Eino ReAct agent and its tools can run successfully without producing Eino telemetry in Logfire.
- Hand-writing a callback that opens generic spans would omit important agent semantics and is not a supported
  Eino integration. This guide intentionally does not present that as full support.

You can separately instrument an underlying model client when an instrumentation library supports it. Those
model spans can appear in Logfire, but they do not prove that the Eino agent or its tool loop is traced.

## What complete support requires

A complete integration needs a maintained callback handler that maps Eino's agent, model, tool, streaming, and
error lifecycle to OpenTelemetry spans and established generative AI semantic conventions. Once Eino or a
maintained adapter provides that mapping, its standard OTLP exporter can send those spans to Logfire.

Until then, treat Eino as **not fully supported** rather than adding synthetic spans around a working agent.
