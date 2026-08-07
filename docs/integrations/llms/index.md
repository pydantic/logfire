---
title: "AI & LLM integrations"
description: "Instrument the LLM SDK or agent framework you already use and see every model call in Logfire: the prompt, tool calls, tokens, cost, and latency."
---

# AI & LLM integrations

Trace the model calls, agent steps, and tool calls in your AI app. Instrument the SDK or agent framework you already use with a few lines, and the resulting spans show up in Logfire, with prompts, tokens, cost, and latency where the integration captures them.

!!! tip "Looking for an agent framework?"
    These pages cover model-provider SDKs and LLM libraries. If you build on an agent framework (CrewAI, LangGraph, Agno, VoltAgent, and more, across Python, TypeScript, Go, Rust, and .NET), see [**Agent Frameworks**](../agent-frameworks/index.md) for per-framework setup and which Logfire views each populates.

!!! note "Instrument vs. gateway"
    These pages **instrument** the calls you already make, so you can see them in Logfire. To instead **route** your calls through Logfire for spending caps and provider failover, see [Connect an agent to the AI Gateway](../../reference/advanced/gateway/integrations/index.md).

<div class="integration-grid">
  <a class="integration-card" href="pydanticai.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/pydantic-ai.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/pydantic-ai.svg) center/contain no-repeat"></span>
    <span class="integration-name">Pydantic AI</span>
  </a>
  <a class="integration-card" href="openai.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/openai.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/openai.svg) center/contain no-repeat"></span>
    <span class="integration-name">OpenAI</span>
  </a>
  <a class="integration-card" href="google-genai.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/google-gemini.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/google-gemini.svg) center/contain no-repeat"></span>
    <span class="integration-name">Google Gen AI</span>
  </a>
  <a class="integration-card" href="anthropic.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/anthropic.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/anthropic.svg) center/contain no-repeat"></span>
    <span class="integration-name">Anthropic</span>
  </a>
  <a class="integration-card" href="langchain.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/langchain.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/langchain.svg) center/contain no-repeat"></span>
    <span class="integration-name">LangChain</span>
  </a>
  <a class="integration-card" href="litellm.md">
    <span class="integration-logo integration-logo--plainmark">Li</span>
    <span class="integration-name">LiteLLM</span>
  </a>
  <a class="integration-card" href="dspy.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/dspy.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/dspy.svg) center/contain no-repeat"></span>
    <span class="integration-name">DSPy</span>
  </a>
  <a class="integration-card" href="mcp.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/mcp.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/mcp.svg) center/contain no-repeat"></span>
    <span class="integration-name">MCP</span>
  </a>
  <a class="integration-card" href="llamaindex.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/llamaindex.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/llamaindex.svg) center/contain no-repeat"></span>
    <span class="integration-name">LlamaIndex</span>
  </a>
  <a class="integration-card" href="mirascope.md">
    <span class="integration-logo integration-logo--glyph" style="-webkit-mask: url(../../images/integrations/llms/mirascope.svg) center/contain no-repeat; mask: url(../../images/integrations/llms/mirascope.svg) center/contain no-repeat"></span>
    <span class="integration-name">Mirascope</span>
  </a>
  <a class="integration-card" href="magentic.md">
    <span class="integration-logo integration-logo--plainmark">Ma</span>
    <span class="integration-name">Magentic</span>
  </a>
</div>

## Not listed?

Any OpenTelemetry-compatible LLM SDK can send to Logfire. See [Alternative clients](../../how-to-guides/alternative-clients.md) for the generic pattern.
