---
title: "AI & LLM Observability"
description: "Monitor, debug, and optimize your AI agents and LLM applications with Pydantic Logfire. Full-stack observability for the AI era."
---

# AI & LLM Observability

**Pydantic Logfire** is an AI-native observability platform built by the team behind Pydantic (the validation layer used by OpenAI, Anthropic, and most AI frameworks).

What does "AI-native" mean? Two things:

1. **Designed for AI development workflows.** Logfire has purpose-built features for LLM applications: conversation panels, token tracking, cost monitoring, tool call inspection. It integrates with [pydantic-evals](https://github.com/pydantic/pydantic-evals) for systematic testing. And unlike AI-only observability tools that only see the LLM layer, Logfire is built on [OpenTelemetry](https://opentelemetry.io/) and traces your entire application stack, so you can debug whether a problem is in the AI or the backend.

2. **Designed to be queried by AI.** Logfire exposes all observability data via SQL (PostgreSQL-compatible syntax). This means your coding agent can query production data directly, asking arbitrary questions without being limited to predefined dashboards or APIs. We provide an [MCP server](how-to-guides/mcp-server.md) that makes this seamless. Other tools may offer MCP integrations, but without raw SQL access, agents are constrained to whatever queries someone anticipated. With Logfire, they can ask anything.

If your framework has OTel instrumentation, it works with Logfire automatically.

## AI-Specific Features

Logfire includes purpose-built features for AI/LLM workloads:

### LLM Panels

Visual inspection of conversations, tool calls, and responses. See the full context of every LLM interaction.

### Token Tracking

See token usage per request and per model. Understand where your tokens are going.

### Cost Monitoring

Track spending across providers. Set up alerts when costs exceed thresholds.

### Tool Call Inspection

See arguments, responses, and latency for each tool call. Essential for debugging agent behavior.

### Streaming Support

Debug streaming responses with full visibility into each chunk.

### Multi-turn Conversations

Trace entire conversation flows across multiple turns and tool calls.

### Evaluations

[pydantic-evals](https://github.com/pydantic/pydantic-evals) is a code-first evaluation framework that integrates with Logfire. A key difference from other eval tools: pydantic-evals can evaluate any Python function, not just LLM calls. This means you can test your tools, your data pipelines, your entire agent workflow. Define evals in Python, run them locally or in CI, and view results in Logfire. Unlike UI-managed evals in other tools, pydantic-evals treats evaluations as code: version-controlled, programmatically managed, and integrated with your existing test infrastructure.

## Quick Start

```python
import logfire
from openai import OpenAI

logfire.configure()
logfire.instrument_openai()

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

That's it. Three lines to instrument your AI calls.

## Framework Integrations

Logfire works with any framework that has OpenTelemetry instrumentation. Our convenient wrappers are optional shortcuts, not requirements.

### Python Frameworks with Logfire Wrappers

One function call instruments each framework:

- [Pydantic AI](integrations/llms/pydanticai.md) - `logfire.instrument_pydantic_ai()`
- [OpenAI](integrations/llms/openai.md) - `logfire.instrument_openai()`
- [Anthropic](integrations/llms/anthropic.md) - `logfire.instrument_anthropic()`
- [LangChain](integrations/llms/langchain.md) - Built-in OTel support
- [LlamaIndex](integrations/llms/llamaindex.md) - `logfire.instrument_llamaindex()`
- [LiteLLM](integrations/llms/litellm.md) - `logfire.instrument_litellm()`
- [Google GenAI](integrations/llms/google-genai.md) - `logfire.instrument_google_genai()`
- [MCP](integrations/llms/mcp.md) - Model Context Protocol support

### JavaScript/TypeScript

The [Logfire JS SDK](integrations/javascript/index.md) supports Node.js, browsers, Next.js, Cloudflare Workers, and Deno.

Frameworks like [Vercel AI SDK](integrations/javascript/vercel-ai.md) have built-in OpenTelemetry support. Configure OTel to send to Logfire and it works automatically.

### Any OTel-Compatible Framework

If your framework has OpenTelemetry instrumentation, it works with Logfire. No special integration needed, just standard OTel configuration.

## Why Full-Stack Context Matters for AI

The core limitation of AI-only observability tools is that they only see the LLM layer.

When debugging AI applications, you need to answer three questions:

1. What triggered this LLM call?
2. What did the AI access (databases, APIs, tools)?
3. What happened with the response?

AI-only tools can only show you the middle part. They're missing the context that makes debugging possible.

### Why This Matters for Agents

What separates agents from simple chat completions is the agentic loop of tool calling. An agent doesn't just generate text. It reasons, calls tools, observes results, and iterates.

Here's the problem: tool execution data comes from application tracing, not from the LLM framework.

When an agent calls a tool to query a database, the LLM framework knows:

- "Tool `search_products` was called with `query='red shoes'`"
- "Tool returned 47 results"

But it has no idea:

- That the database query took 3 seconds because it did a full table scan
- That 200 products matched but were filtered by inventory status
- That the connection pool was exhausted so it waited 2 seconds for a connection

AI-only observability tools only see what the LLM framework sees. They'll show you the tool call and the result, but not what happened inside the tool.

### A Concrete Example

User asks your e-commerce agent: "What shoes can I get by Friday?" The agent recommends products that won't arrive until next week. Why?

With an AI-only tool, you see the agent called `search_products(category='shoes')` and returned 5 products. You can see the tool call and response, but you can't tell why the delivery constraint wasn't respected.

With Logfire, you can diagnose both types of problems:

**Scenario A** (AI problem):
The trace shows: Agent called `search_products(category='shoes')` with no delivery filter → tool returned products sorted by relevance → agent presented them without checking delivery dates.

*Diagnosis:* The agent didn't realize it needed to account for the "by Friday" constraint. It needs better instructions about handling delivery requirements. This is an AI/prompt problem, and an AI-only tool could catch this too.

**Scenario B** (tool/backend problem):
The trace shows: Agent called `search_products(category='shoes', delivery_by='2025-01-24')` → tool executed query with `WHERE estimated_delivery <= '2025-01-24'` → but the `estimated_delivery` column is stale (last updated 3 days ago) → returned products with outdated delivery estimates.

*Diagnosis:* The agent did the right thing! The problem is stale data in the backend. This is an infrastructure problem, not an AI problem. An AI-only tool would just show "agent called tool, got results" with no visibility into why the results were wrong.

The point is that you often can't tell which type of problem you have until you see both the AI reasoning and what actually happened in the backend. AI-only tools can help you catch Scenario A. Only full-stack observability catches Scenario B, and helps you fix the right thing.

## Works With Any Language

Logfire is built on OpenTelemetry, the industry standard for observability. We provide polished SDKs for Python, JavaScript/TypeScript, and Rust, but any language with OpenTelemetry support can send data to Logfire.

### First-Party SDKs

We maintain SDKs for **Python**, **JavaScript/TypeScript** (Node.js, browsers, Next.js, Cloudflare Workers, Deno), and **Rust**. The Python SDK has the deepest integrations since that's where most AI development happens, but the JS/TS SDK is fully featured for polyglot applications.

### Any OTel-Compatible Language

Go, Java, .NET, Ruby, PHP, Elixir: if it has an OTel SDK, it works with Logfire. See [alternative clients](how-to-guides/alternative-clients.md) for setup examples.

### Polyglot Architectures

Modern AI applications are rarely single-language. A Python AI backend with a TypeScript frontend, or Go microservices calling Python ML models, are common patterns. Since Logfire accepts data from any OTel source, you can see spans from all of these in the same trace without stitching together data from multiple tools.

## No Lock-In

Logfire is built on OpenTelemetry, which means your instrumentation is portable. If you instrument your code with the Logfire SDK, you're really just configuring OpenTelemetry with sensible defaults. You can [configure the SDK to send data to other backends](how-to-guides/alternative-backends.md) if you want, or use standard OTel libraries directly and just point them at Logfire's OTLP endpoint. No proprietary agents or formats to worry about.

## SQL-Based Analysis

Logfire exposes your observability data via a SQL interface powered by [DataFusion](https://datafusion.apache.org/), which uses PostgreSQL-compatible syntax:

```sql
SELECT
    span_name,
    attributes->>'gen_ai.usage.input_tokens' as input_tokens,
    attributes->>'gen_ai.usage.output_tokens' as output_tokens,
    duration
FROM records
WHERE span_name LIKE 'llm%'
ORDER BY start_timestamp DESC
LIMIT 100
```

No proprietary query language to learn. This matters for two reasons:

**For humans:** SQL is familiar. You can write ad-hoc queries, build custom dashboards, export to any BI tool.

**For agents:** Your coding agent probably writes better SQL than you do anyway. Point it at your Logfire data via our [MCP server](how-to-guides/mcp-server.md) and let it answer questions about production behavior. "Why did latency spike yesterday?" "Which users are hitting token limits?" "Show me all traces where the agent made more than 5 tool calls." The agent can ask anything because it has full SQL access, not just predefined API endpoints.

## Comparison to AI-Only Tools

Tools like Langfuse, Arize, and LangSmith focus specifically on LLM observability. They're good at what they do, but they only see the LLM layer. When your agent calls a tool that queries a database or hits an API, those tools see the tool call and the result, not what happened in between.

Logfire takes a different approach: since it's built on OpenTelemetry and can ingest traces from your entire application, you get AI observability as part of full-stack observability rather than in isolation. The [concrete example above](#a-concrete-example) illustrates why this matters in practice.

[See detailed comparisons →](comparisons/index.md)

## Getting Started

1. [Create a Logfire account](https://logfire.pydantic.dev)
2. Install the SDK: `pip install logfire`
3. Configure and instrument:

```python
import logfire

logfire.configure()
logfire.instrument_openai()  # Or your framework of choice
```

[Full getting started guide →](index.md)

## Learn More

- [LLM Panels](guides/web-ui/llm-panels.md) - Detailed guide to LLM visualization
- [Integrations](integrations/index.md) - All supported frameworks
- [Why Logfire?](why.md) - General platform overview
- [Comparisons](comparisons/index.md) - How Logfire compares to alternatives
