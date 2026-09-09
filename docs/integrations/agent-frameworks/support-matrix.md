---
title: Agent framework support matrix
description: "Which Logfire views work with each agent framework, and which agent-level fields each integration currently provides."
---

# Agent framework support matrix

Every framework that sends OpenTelemetry (OTel), the open industry standard for collecting traces, metrics, and logs, to Logfire appears in **Live** and **Explore**. The specialized **LLMs** and **Agents** views also require attributes and parent-child relationships that Logfire recognizes.

The columns below describe current specialized-view behavior:

- **LLMs** means model calls appear on the LLMs page.
- **Agents** means agent runs appear on the Agents page.
- **Agent model & tokens** and **Agent cost** mean the aggregate values shown in the Agents list and Metrics tab. Seeing these fields on a raw span does not guarantee that Logfire can associate the model call with its agent run.
- **Agent Tools** and **Agent Messages** mean the corresponding tabs in an agent run's detail panel. Raw tool or message attributes can still appear in Live and Explore when these columns are empty.

An individual run can estimate cost from its model and token counts even when aggregate agent cost is unavailable. Aggregate cost requires the instrumentation to record `operation.cost` on a model call that Logfire can associate with the agent.

Legend: **●** full &nbsp;·&nbsp; **◐** partial or configuration-dependent &nbsp;·&nbsp; **○** unavailable in the named view.

## Native OTel GenAI

These frameworks emit native `gen_ai.*` spans. Differences in operation names, trace relationships, and optional content recording still affect the specialized views.

| Framework | Live & Explore | LLMs | Agents | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Pydantic AI](../llms/pydanticai.md) | ● | ● | ● | ● | ● | ● | ● |
| [Google ADK](../llms/google-adk.md) | ● | ● | ● | ● | ◐ | ◐ | ◐ |
| [Strands Agents](../llms/strands.md) [^nested-native] | ● | ● | ● | ○ | ○ | ○ | ◐ |
| [Semantic Kernel](../llms/semantic-kernel.md) [^semantic-kernel-python] | ● | ○ | ● | ○ | ○ | ○ | ○ |
| [AutoGen](../llms/autogen.md) | ● | ● | ● | ● | ○ | ◐ | ◐ |
| [Mastra](mastra.md) | ● | ● | ● | ● | ◐ | ○ | ● |
| [Vercel AI SDK](vercel-ai-sdk.md) [^nested-native] | ● | ● | ● | ○ | ○ | ◐ | ● |
| [Rig](rig.md) [^rig] | ● | ● | ● | ○ | ○ | ○ | ○ |
| [Microsoft Agent Framework (.NET)](agent-framework-dotnet.md) | ● | ● | ● | ● | ◐ | ◐ | ◐ |
| [Semantic Kernel (.NET)](semantic-kernel-dotnet.md) | ● | ● | ◐ | ● | ◐ | ○ | ◐ |

## OpenInference and other bridges

Logfire reads OpenInference LLM and agent spans. It can aggregate model and token data when an LLM span has a recognized agent ancestor. OpenInference does not populate aggregate agent cost in the current reader.

The Agents Info tab can show a system prompt reconstructed from OpenInference input messages. The Tools tab can show definitions when the instrumentor emits `llm.tools.*.tool.json_schema`. The full Agents Messages tab does not yet read OpenInference messages.

| Framework | Live & Explore | LLMs | Agents | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Agno](../llms/agno.md) | ● | ● | ● | ● | ○ | ◐ | ○ |
| [smolagents](../llms/smolagents.md) | ● | ● | ● | ● | ○ | ◐ | ○ |
| [LangGraph](../llms/langgraph.md) | ● | ● | ● | ● | ○ | ◐ | ○ |
| [OpenAI Agents SDK (Python)](../llms/openai.md#openai-agents) | ● | ● | ● | ● | ○ | ◐ | ○ |
| [CrewAI](../llms/crewai.md) [^crewai] | ● | ○ | ● | ○ | ○ | ○ | ○ |
| [Eve](eve.md) [^eve] | ● | ● | ◐ | ◐ | ○ | ○ | ○ |

## Framework-specific conventions

Logfire recognizes the agent root through a framework-specific attribute. Model-call support depends on the telemetry emitted below that root.

| Framework | Live & Explore | LLMs | Agents | Agent model & tokens | Agent cost | Agent Tools | Agent Messages |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| [Traceloop / OpenLLMetry](../../guides/web-ui/agents.md#supported-frameworks) [^traceloop] | ● | ● | ● | ● | ○ | ○ | ◐ |
| [Genkit (Go)](genkit-go.md) | ● | ○ | ● | ○ | ○ | ○ | ○ |
| [VoltAgent](voltagent.md) | ● | ○ | ● | ○ | ○ | ○ | ○ |

## Tracing without Agents support

These integrations send useful traces, but their current agent root is not recognized by the Agents page.

| Framework | Live & Explore | LLMs | Agents | Notes |
| --- | :---: | :---: | :---: | --- |
| [Haystack](../llms/haystack.md) | ● | ● | ○ | Emits OpenInference chain and LLM spans, but no agent span. |
| [LlamaIndex (TS)](llamaindex-ts.md) | ● | ● | ○ | Emits an LLM chat span, but no agent span. |
| [LangChain (JS)](langchain-js.md) | ● | ○ | ○ | Uses LangSmith's trace convention, which the specialized views do not currently interpret. |
| [Instructor](../llms/instructor.md) | ● | ● | ○ | Emits an LLM span and is not an agent framework. |
| [Letta](../llms/letta.md) | ● | ○ | ○ | Sends server traces over OTLP, but no recognized agent span. |
| [OpenAI Agents SDK (TS)](openai-agents-js.md) | ◐ | ◐ | ○ | Has no complete OpenTelemetry exporter; an instrumented model client can provide LLM spans only. |
| [Claude Agent SDK](../llms/claude-agent-sdk.md) | ● | ● | ○ | Emits native `gen_ai` conversation, model, and tool spans, but no `gen_ai.agent.name`. |

## No maintained agent telemetry

| Framework | Live & Explore | LLMs | Agents | Notes |
| --- | :---: | :---: | :---: | --- |
| [Eino (Go)](eino.md) | ○ | ○ | ○ | Has no maintained instrumentation for its agent and tool lifecycle. Surrounding application or model-client spans can still reach Logfire. |

[^nested-native]: The agent run and model call are visible, but an intermediate framework span currently prevents Logfire from assigning the model call to aggregate agent metrics.

[^semantic-kernel-python]: Semantic Kernel emits `chat.completions` model operations. Live and Explore show those spans, but the current LLMs and Agents readers do not recognize that operation for model metrics.

[^rig]: Rig emits the agent run and model call on separate trace IDs. Both traces reach Logfire, but Logfire cannot safely assign the model, tokens, cost, tools, or messages to the agent run.

[^crewai]: CrewAI is detected and named on the Agents page, but its current OpenInference instrumentation does not emit separate LLM spans.

[^eve]: Eve agent runs and conversations are detected, but aggregate Agent metrics can miss turns or count repeated token attributes more than once. Use the LLMs page for exact model-call usage.

[^traceloop]: Logfire recognizes spans created by OpenLLMetry's `@agent` decorator. Model and token aggregation works when the model call is a child of that span. Other detail fields depend on the model-client instrumentation used inside the agent.

!!! note "Framework versions can change telemetry"
    This matrix describes the setup in each linked guide and Logfire's current readers. A framework or instrumentor update can change its span names, attributes, or trace relationships. If your result differs, inspect the trace in Live and compare your package versions with the guide.
