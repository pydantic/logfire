---
title: Agent Frameworks
description: "How to send telemetry from popular AI agent frameworks — in Python, TypeScript, Go, Rust, and .NET — to Pydantic Logfire, and how to use managed prompts with each."
---
# Agent Frameworks

**Pydantic Logfire** is built on [OpenTelemetry](https://opentelemetry.io/), so it can ingest traces from many
artificial intelligence (AI) agent frameworks. Each guide either shows a verified integration or explains the
framework's current limitation. Supported examples show four things:

- **How to send telemetry to Logfire** — the exact setup for that framework.
- **A native agent and tool call** you can adapt to your application.
- **What you'll see in Logfire** — including any limits in the specialized large language model (LLM) or
  Agents views.
- **How to use managed prompts** — authoring and versioning prompts in
  [Prompt Management](../../reference/advanced/prompt-management/index.md) and fetching them at runtime.

!!! tip "Just tracing model calls?"
    These pages cover agent frameworks. If you call a model-provider SDK or LLM library directly (OpenAI, Anthropic, Google Gen AI, LiteLLM, and more), see [**AI & LLM integrations**](../llms/index.md).

There are four integration patterns, depending on the framework:

1. **Native OpenTelemetry (OTel)** — the framework already emits OTel spans through the global tracer provider. In
   Python, calling [`logfire.configure()`][logfire.configure] is enough to collect those native spans (e.g. Pydantic
   AI, AutoGen, Google ADK, Strands, and Semantic Kernel). A guide may also enable model-client tracing. In
   other languages, point the standard OTel software development kit (SDK) at Logfire's OpenTelemetry Protocol
   (OTLP) endpoint.
2. **A first-party adapter or bridge** — an integration package connects the framework's own tracing system to
   OTel (e.g. Haystack's `opentelemetry-haystack`, Vercel's `@ai-sdk/otel`, and Mastra's
   `@mastra/otel-exporter`). Rig uses the Logfire Rust SDK to install a `tracing` subscriber that bridges its native
   Rust `tracing` spans to OTel.
3. **A third-party instrumentor** — an [OpenInference](https://github.com/Arize-ai/openinference) or
   [OpenLLMetry](https://github.com/traceloop/openllmetry) package adds the spans. Because
   [`logfire.configure()`][logfire.configure] sets the global provider, the instrumentor's spans flow to
   Logfire automatically (e.g. CrewAI, smolagents, Agno).
4. **OTLP over the wire** — for languages and frameworks that already emit compatible telemetry, send to Logfire's
   OTLP endpoint directly (or via an [OpenTelemetry Collector](../../how-to-guides/otel-collector/otel-collector-overview.md)).

All four patterns can send traces to the **Live** and **Explore** views. The specialized **LLMs** and **Agents**
views also depend on the span attributes and parent-child relationships the framework emits. Receiving valid
OTLP data does not by itself guarantee that every specialized view can interpret it. Where a framework has a
known limitation, its guide calls that out explicitly.

The examples do not add manual wrapper spans to simulate agent support. If a framework has no complete native,
official, or maintained third-party OpenTelemetry path, its guide says that it is not fully supported.

!!! tip "At a glance"
    The [**support matrix**](support-matrix.md) summarizes which Logfire views — Live, Explore, LLMs, and Agents —
    work with each framework, and where a framework has a known limitation.

## Python

| Framework | Guide |
| --------- | ----- |
| Pydantic AI | [Pydantic AI](../llms/pydanticai.md) |
| OpenAI Agents SDK | [OpenAI](../llms/openai.md#openai-agents) |
| LangChain | [LangChain](../llms/langchain.md) |
| LangGraph | [LangGraph](../llms/langgraph.md) |
| CrewAI | [CrewAI](../llms/crewai.md) |
| AutoGen | [AutoGen](../llms/autogen.md) |
| Google ADK | [Google ADK](../llms/google-adk.md) |
| smolagents | [smolagents](../llms/smolagents.md) |
| Strands Agents | [Strands Agents](../llms/strands.md) |
| Agno | [Agno](../llms/agno.md) |
| Haystack | [Haystack](../llms/haystack.md) |
| Semantic Kernel | [Semantic Kernel (Python)](../llms/semantic-kernel.md) |
| Letta | [Letta](../llms/letta.md) |
| Claude Agent SDK | [Claude Agent SDK](../llms/claude-agent-sdk.md) |

## TypeScript / JavaScript

| Framework | Guide |
| --------- | ----- |
| Vercel AI SDK | [Vercel AI SDK](vercel-ai-sdk.md) |
| Mastra | [Mastra](mastra.md) |
| LangChain.js / LangGraph.js | [LangChain.js](langchain-js.md) |
| OpenAI Agents SDK (TS) | [OpenAI Agents SDK (TS) — not fully supported](openai-agents-js.md) |
| VoltAgent | [VoltAgent](voltagent.md) |
| LlamaIndex.TS | [LlamaIndex.TS](llamaindex-ts.md) |
| Eve | [Eve](eve.md) |

## Go

| Framework | Guide |
| --------- | ----- |
| Firebase Genkit | [Genkit (Go)](genkit-go.md) |
| Eino | [Eino (Go) — not fully supported](eino.md) |

## Rust

| Framework | Guide |
| --------- | ----- |
| Rig | [Rig (Rust)](rig.md) |

## .NET

| Framework | Guide |
| --------- | ----- |
| Semantic Kernel | [Semantic Kernel (.NET)](semantic-kernel-dotnet.md) |
| Microsoft Agent Framework | [Microsoft Agent Framework (.NET)](agent-framework-dotnet.md) |

## Related LLM integrations

[LlamaIndex Python](../llms/llamaindex.md), [DSPy](../llms/dspy.md), and
[Instructor](../llms/instructor.md) have useful model or workflow telemetry integrations, but their current
guides do not demonstrate native agent tool loops. They remain in the broader [LLM integrations](../llms/index.md)
rather than being presented here as verified agent examples.

!!! tip "Don't see your framework?"
    Any OpenTelemetry-compatible library works with Logfire. See
    [Use Alternative Clients](../../how-to-guides/alternative-clients.md) for the generic OTLP setup in any
    language, and let us know on [Slack](https://pydantic.dev/docs/logfire/join-slack/) what you'd like us to
    document next.
