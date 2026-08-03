---
title: Agent Frameworks
description: "How to send telemetry from popular AI agent frameworks — in Python, TypeScript, Go, Rust, and .NET — to Pydantic Logfire, and how to use managed prompts with each."
---
# Agent Frameworks

**Pydantic Logfire** is built on [OpenTelemetry](https://opentelemetry.io/), so it can ingest traces from
essentially any artificial intelligence (AI) agent framework. Each guide below shows four things:

- **How to send telemetry to Logfire** — the exact setup for that framework.
- **An example agent configuration** you can adapt to your application.
- **What you'll see in Logfire** — including any limits in the specialized large language model (LLM) or
  Agents views.
- **How to use managed prompts** — authoring and versioning prompts in
  [Prompt Management](../../reference/advanced/prompt-management/index.md) and fetching them at runtime.

There are four integration patterns, depending on the framework:

1. **Native OpenTelemetry (OTel)** — the framework already emits OTel spans through the global tracer provider. In
   Python, calling [`logfire.configure()`][logfire.configure] is enough to collect those native spans (e.g. Pydantic
   AI, AutoGen, Google ADK, Strands, Semantic Kernel, and Rig). A guide may also enable model-client tracing. In
   other languages, point the standard OTel software development kit (SDK) at Logfire's OpenTelemetry Protocol
   (OTLP) endpoint.
2. **A first-party adapter** — the framework's maintainers provide an OTel integration package that connects its
   own tracing system to the global provider (e.g. Haystack's `opentelemetry-haystack`, Vercel's `@ai-sdk/otel`,
   and Mastra's `@mastra/otel-exporter`).
3. **A third-party instrumentor** — an [OpenInference](https://github.com/Arize-ai/openinference) or
   [OpenLLMetry](https://github.com/traceloop/openllmetry) package adds the spans. Because
   [`logfire.configure()`][logfire.configure] sets the global provider, the instrumentor's spans flow to
   Logfire automatically (e.g. CrewAI, smolagents, Agno).
4. **OTLP over the wire** — for languages and frameworks without an in-process exporter, send to Logfire's
   OTLP endpoint directly (or via an [OpenTelemetry Collector](../../how-to-guides/otel-collector/otel-collector-overview.md)).

All four patterns can send traces to the **Live** and **Explore** views. The specialized **LLMs** and **Agents**
views also depend on the span attributes and parent-child relationships the framework emits. Receiving valid
OTLP data does not by itself guarantee that every specialized view can interpret it. Where a framework has a
known limitation, its guide calls that out explicitly.

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
| LlamaIndex | [LlamaIndex](../llms/llamaindex.md) |
| DSPy | [DSPy](../llms/dspy.md) |
| Instructor | [Instructor](../llms/instructor.md) |
| Semantic Kernel | [Semantic Kernel (Python)](../llms/semantic-kernel.md) |
| Letta | [Letta](../llms/letta.md) |
| Claude Agent SDK | [Claude Agent SDK](../llms/claude-agent-sdk.md) |

## TypeScript / JavaScript

| Framework | Guide |
| --------- | ----- |
| Vercel AI SDK | [Vercel AI SDK](vercel-ai-sdk.md) |
| Mastra | [Mastra](mastra.md) |
| LangChain.js / LangGraph.js | [LangChain.js](langchain-js.md) |
| OpenAI Agents SDK (TS) | [OpenAI Agents SDK (TS)](openai-agents-js.md) |
| VoltAgent | [VoltAgent](voltagent.md) |
| LlamaIndex.TS | [LlamaIndex.TS](llamaindex-ts.md) |
| Eve | [Eve](eve.md) |

## Go

| Framework | Guide |
| --------- | ----- |
| Firebase Genkit | [Genkit (Go)](genkit-go.md) |
| Eino | [Eino (Go)](eino.md) |

## Rust

| Framework | Guide |
| --------- | ----- |
| Rig | [Rig (Rust)](rig.md) |

## .NET

| Framework | Guide |
| --------- | ----- |
| Semantic Kernel | [Semantic Kernel (.NET)](semantic-kernel-dotnet.md) |
| Microsoft Agent Framework | [Microsoft Agent Framework (.NET)](agent-framework-dotnet.md) |

!!! tip "Don't see your framework?"
    Any OpenTelemetry-compatible library works with Logfire. See
    [Use Alternative Clients](../../how-to-guides/alternative-clients.md) for the generic OTLP setup in any
    language, and let us know on [Slack](https://pydantic.dev/docs/logfire/join-slack/) what you'd like us to
    document next.
