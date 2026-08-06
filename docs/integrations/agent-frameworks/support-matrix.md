---
title: Agent framework support matrix
description: "At-a-glance view of which Logfire views work with each agent framework — tracing, the LLMs view, and the Agents view — and where a framework has a known limitation."
---

# Agent framework support matrix

Every framework that sends OpenTelemetry (OTel) spans to Logfire gets the **Live** and **Explore** views, the
trace waterfall, annotations, dashboards, and alerts. The specialized **LLMs** and **Agents** views need specific
span attributes and parent-child relationships, so their support varies by framework.

This page summarizes what each framework's guide describes about Logfire's views. The determining factor is
**how the framework emits its spans**:

- **Native OTel-GenAI semconv** (`gen_ai.*`): the LLMs and Agents views understand these directly, so model, token,
  **cost**, and — where the framework emits them — tool and message data all populate.
- **Instrumentor or bridge** (e.g. [OpenInference](https://github.com/Arize-ai/openinference) /
  [OpenLLMetry](https://github.com/traceloop/openllmetry), a framework's own OTel bridge, or a Logfire-native
  instrumentor): agent runs and token counts populate, but cost, the tools tab, and message/prompt content are not
  yet read from these conventions.

Legend: **●** full &nbsp;·&nbsp; **◐** partial or framework-dependent &nbsp;·&nbsp; **○** not yet.

## Full agent support — native OTel-GenAI

These frameworks emit `gen_ai.*` spans, so the Agents view shows runs, tokens, model, and cost. Tools and message
content appear when the framework emits them (see each guide).

| Framework | Live & Explore | Agents view | Tokens & model | Cost | Tools | Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| [Pydantic AI](../llms/pydanticai.md) | ● | ● | ● | ● | ● | ● |
| [Google ADK](../llms/google-adk.md) | ● | ● | ● | ● | ◐ | ◐ |
| [Strands Agents](../llms/strands.md) | ● | ● | ● | ● | ○ | ◐ |
| [Semantic Kernel](../llms/semantic-kernel.md) | ● | ● | ● | ● | ○ | ○ |
| [AutoGen](../llms/autogen.md) | ● | ● | ● | ● | ◐ | ◐ |
| [Mastra](mastra.md) | ● | ● | ● | ● | ○ | ● |
| [Vercel AI SDK](vercel-ai-sdk.md) | ● | ● | ● | ● | ◐ | ● |
| [Rig](rig.md) | ● | ● | ● | ● | ◐ | ◐ |
| [Microsoft Agent Framework (.NET)](agent-framework-dotnet.md) | ● | ● | ● | ● | ◐ | ◐ |
| [Semantic Kernel (.NET)](semantic-kernel-dotnet.md) | ● | ◐ | ● | ● | ○ | ◐ |

## Agent runs and tokens — instrumentor or bridge

Detected as agents with per-run token counts. Cost, the tools tab, and message/prompt content are not yet read
from these conventions.

| Framework | Live & Explore | Agents view | Tokens & model | Cost | Tools | Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| [Agno](../llms/agno.md) | ● | ● | ● | ○ | ○ | ○ |
| [smolagents](../llms/smolagents.md) | ● | ● | ● | ○ | ○ | ○ |
| [LangGraph](../llms/langgraph.md) | ● | ● | ● | ○ | ○ | ○ |
| [OpenAI Agents SDK (Python)](../llms/openai.md#openai-agents) | ● | ● | ● | ○ | ○ | ○ |
| [CrewAI](../llms/crewai.md) [^crewai] | ● | ● | ○ | ○ | ○ | ○ |
| [Eve](eve.md) [^eve] | ● | ◐ | ● | ○ | ○ | ○ |

## Detected agents — custom conventions

Detected as agent runs from a framework-specific key. Model-call metrics depend on how the framework emits its
LLM calls; in the configurations we tested they are not captured as model calls.

| Framework | Live & Explore | Agents view | Tokens & model | Cost | Tools | Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| [Genkit (Go)](genkit-go.md) | ● | ● | ○ | ○ | ○ | ○ |
| [VoltAgent](voltagent.md) | ● | ● | ○ | ○ | ○ | ○ |

## Tracing only

These emit valid OTel spans — so Live, Explore, dashboards, and alerts all work — but do not currently produce an
agent-run span the Agents view recognizes (they emit an LLM or chain span, or a non-agent convention).

| Framework | Live & Explore | Agents view | Notes |
| --- | :---: | :---: | --- |
| [Haystack](../llms/haystack.md) | ● | ○ | Emits a chain/LLM span, not an agent-run span. |
| [LlamaIndex (TS)](llamaindex-ts.md) | ● | ○ | Emits an LLM chat span only. |
| [LangChain (JS)](langchain-js.md) | ● | ○ | Traced via LangSmith's own convention. |
| [Instructor](../llms/instructor.md) | ● | ○ | LLM-only; not an agent framework. |
| [Eino (Go)](eino.md) | ● | ○ | No agent-run convention we detect today. |
| [Letta](../llms/letta.md) | ● | ○ | Server traces flow via an OpenTelemetry Collector; no agent-run span is detected. |
| [OpenAI Agents SDK (TS)](openai-agents-js.md) | ◐ | ○ | No OpenTelemetry exporter yet; instrument the underlying model client for LLM spans only. |
| [Claude Agent SDK](../llms/claude-agent-sdk.md) | ● | ○ | Emits native gen_ai `invoke_agent`/`chat`/`execute_tool` spans (LLMs view, tokens, and cost populate), but sets no `gen_ai.agent.name`, so the Agents view does not detect the run. |

[^crewai]: CrewAI is detected and named on the Agents view, but the CrewAI instrumentation in our tests emits no
    LLM spans, so token, model, and cost columns are empty.

[^eve]: Eve agent runs and conversations are detected, but aggregate Agent metrics can miss turns or double-count
    repeated token attributes (tracking issue #28737).

!!! note "This reflects tested configurations"
    Marks are derived from real captured telemetry for each framework. A different SDK version or instrumentation
    setup can change what appears — each framework's guide documents the exact setup we tested.
