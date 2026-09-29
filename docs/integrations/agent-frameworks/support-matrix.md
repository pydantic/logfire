---
title: Agent framework coverage in Logfire
description: "How telemetry from each agent framework appears in Logfire's general observability and curated AI views."
---

# Agent framework coverage in Logfire

Logfire can ingest, query, and correlate telemetry from any framework that emits OpenTelemetry (OTel), the open industry standard for collecting traces, metrics, and logs. Those traces appear in **Live** and **Explore** alongside the rest of your application and infrastructure. Logfire also turns recognized AI attributes and trace relationships into purpose-built **LLMs** and **Agents** views.

This matrix describes how richly each integration populates those product surfaces. It is not a yes-or-no list of frameworks that Logfire supports:

- **Live & Explore** means the integration's OpenTelemetry is available in Logfire's general-purpose observability views and SQL query layer.
- **Curated LLMs view** means Logfire recognizes model calls and adds them to the model inventory.
- **Curated Agents view** means Logfire recognizes agent roots and adds them to the agent-run inventory.
- **Agent model & tokens** and **Agent cost** mean the aggregate values shown in the Agents list and Metrics tab. Seeing these fields on a raw span does not guarantee that Logfire can associate the model call with its agent run.
- **Agent Tools** and **Agent Messages** mean the corresponding tabs in an agent run's detail panel. Raw tool or message attributes can still appear in Live and Explore when these columns are empty.

An individual run can estimate cost from its model and token counts even when aggregate agent cost is unavailable. Aggregate cost requires the instrumentation to record `operation.cost` on a model call that Logfire can associate with the agent.

!!! tip "A dash does not mean the framework is unsupported"
    A dash in a curated-view column means that Logfire does not yet normalize that field into that particular view. When **Live & Explore** is available, the underlying telemetry is still searchable, queryable, and correlated with the rest of your system.

Legend: **● Available** &nbsp;·&nbsp; **◐ Partial or setup-dependent** &nbsp;·&nbsp; **— Not populated in this view**.

## Native OTel GenAI

These frameworks emit native `gen_ai.*` spans. Differences in operation names, trace relationships, and optional content recording still affect the specialized views.

| Framework | Live & Explore | Curated LLMs view | Curated Agents view | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Pydantic AI](../llms/pydanticai.md) | ● | ● | ● | ● | ● | ● | ● |
| [Google ADK](../llms/google-adk.md) | ● | ● | ● | ● | ◐ | ◐ | ◐ |
| [Strands Agents](../llms/strands.md) [^nested-native] | ● | ● | ● | — | — | — | ◐ |
| [Semantic Kernel](../llms/semantic-kernel.md) [^semantic-kernel-python] | ● | — | ● | — | — | — | — |
| [AutoGen](../llms/autogen.md) | ● | ● | ● | ● | — | ◐ | ◐ |
| [Mastra](mastra.md) | ● | ● | ● | ● | ◐ | — | ● |
| [Vercel AI SDK](vercel-ai-sdk.md) [^nested-native] | ● | ● | ● | — | — | ◐ | ● |
| [Rig](rig.md) [^rig] | ● | ● | ● | — | — | — | — |
| [Microsoft Agent Framework (.NET)](agent-framework-dotnet.md) | ● | ● | ● | ● | ◐ | ◐ | ◐ |
| [Semantic Kernel (.NET)](semantic-kernel-dotnet.md) | ● | ● | ◐ | ● | ◐ | — | ◐ |

## OpenInference and other bridges

Logfire reads OpenInference LLM and agent spans. It can aggregate model and token data when an LLM span has a recognized agent ancestor. OpenInference does not populate aggregate agent cost in the current reader.

The Agents Info tab can show a system prompt reconstructed from OpenInference input messages. The Tools tab can show definitions when the instrumentor emits `llm.tools.*.tool.json_schema`. The full Agents Messages tab does not yet read OpenInference messages.

| Framework | Live & Explore | Curated LLMs view | Curated Agents view | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Agno](../llms/agno.md) | ● | ● | ● | ● | — | ◐ | — |
| [smolagents](../llms/smolagents.md) | ● | ● | ● | ● | — | ◐ | — |
| [LangGraph](../llms/langgraph.md) | ● | ● | ● | ● | — | ◐ | — |
| [OpenAI Agents SDK (Python)](../llms/openai.md#openai-agents) | ● | ● | ● | ● | — | ◐ | — |
| [CrewAI](../llms/crewai.md) [^crewai] | ● | — | ● | — | — | — | — |
| [Eve](eve.md) [^eve] | ● | ● | ◐ | ◐ | — | — | — |

## Framework-specific conventions

Logfire recognizes the agent root through a framework-specific attribute. Model-call support depends on the telemetry emitted below that root.

| Framework | Live & Explore | Curated LLMs view | Curated Agents view | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Traceloop / OpenLLMetry](../../guides/web-ui/agents.md#supported-frameworks) [^traceloop] | ● | ● | ● | ● | — | — | ◐ |
| [Genkit (Go)](genkit-go.md) | ● | — | ● | — | — | — | — |
| [VoltAgent](voltagent.md) | ● | — | ● | — | — | — | — |

## Tracing beyond the curated Agents view

These integrations send useful telemetry to Live and Explore. Their current agent root is not yet normalized into the curated Agents view, so you inspect the complete trace directly instead.

| Framework | Live & Explore | Curated LLMs view | Curated Agents view | Notes |
| --- | :---: | :---: | :---: | --- |
| [Haystack](../llms/haystack.md) | ● | ● | — | OpenInference chain and LLM spans provide a detailed trace; the instrumentor does not emit a distinct agent root. |
| [LlamaIndex (TS)](llamaindex-ts.md) | ● | ● | — | Its LLM chat span appears in the LLMs view and the complete workflow remains available in Live and Explore. |
| [LangChain (JS)](langchain-js.md) | ● | — | — | Its LangSmith trace convention remains fully inspectable in Live and Explore. |
| [Instructor](../llms/instructor.md) | ● | ● | — | Its model calls appear in the LLMs view; Instructor itself is not an agent framework. |
| [Letta](../llms/letta.md) | ● | — | — | Server traces arrive over OTLP and remain fully inspectable in Live and Explore. |
| [OpenAI Agents SDK (TS)](openai-agents-js.md) | ◐ | ◐ | — | Instrumenting the model client provides LLM spans while the SDK's OpenTelemetry exporter matures. |
| [Claude Agent SDK](../llms/claude-agent-sdk.md) | ● | ● | — | Native `gen_ai` conversation, model, and tool spans provide a detailed trace; the SDK does not yet emit `gen_ai.agent.name`. |

## Bring your own OpenTelemetry

This framework does not currently publish maintained instrumentation for its agent and tool lifecycle. You can still instrument the surrounding application and model client, preserving end-to-end observability in Logfire.

| Framework | Live & Explore | Curated LLMs view | Curated Agents view | Notes |
| --- | :---: | :---: | :---: | --- |
| [Eino (Go)](eino.md) | — | — | — | Add OpenTelemetry around the application or model client to send the surrounding workflow to Logfire. |

[^nested-native]: The agent run and model call are visible, but an intermediate framework span currently prevents Logfire from assigning the model call to aggregate agent metrics.

[^semantic-kernel-python]: Semantic Kernel emits `chat.completions` model operations. Live and Explore show those spans, but the current LLMs and Agents readers do not recognize that operation for model metrics.

[^rig]: Rig emits the agent run and model call on separate trace IDs. Both traces reach Logfire, but Logfire cannot safely assign the model, tokens, cost, tools, or messages to the agent run.

[^crewai]: CrewAI is detected and named on the Agents page, but its current OpenInference instrumentation does not emit separate LLM spans.

[^eve]: Eve agent runs and conversations are detected, but aggregate Agent metrics can miss turns or count repeated token attributes more than once. Use the LLMs page for exact model-call usage.

[^traceloop]: Logfire recognizes spans created by OpenLLMetry's `@agent` decorator. Model and token aggregation works when the model call is a child of that span. Other detail fields depend on the model-client instrumentation used inside the agent.

!!! note "Framework versions can change telemetry"
    This matrix describes the setup in each linked guide and Logfire's current readers. A framework or instrumentor update can change its span names, attributes, or trace relationships. If your result differs, inspect the trace in Live and compare your package versions with the guide.
