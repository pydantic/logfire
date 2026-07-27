---
title: "AI & LLM integrations"
description: "Instrument the LLM SDK or agent framework you already use and see every model call in Logfire: the prompt, tool calls, tokens, cost, and latency."
---

# AI & LLM integrations

Trace the model calls, agent steps, and tool calls in your AI app. Instrument the SDK or agent framework you already use with a few lines, and the resulting spans show up in Logfire, with prompts, tokens, cost, and latency where the integration captures them.

<div class="integration-grid">
  <a class="integration-card" href="pydanticai/">
    <span class="integration-logo"><img src="../../images/integrations/llms/pydantic-ai.svg" alt="" loading="lazy"></span>
    <span class="integration-name">Pydantic AI</span>
  </a>
  <a class="integration-card" href="openai/">
    <span class="integration-logo integration-logo--mark">O</span>
    <span class="integration-name">OpenAI</span>
  </a>
  <a class="integration-card" href="google-genai/">
    <span class="integration-logo"><img src="../../images/integrations/llms/google-gemini.svg" alt="" loading="lazy"></span>
    <span class="integration-name">Google Gen AI</span>
  </a>
  <a class="integration-card" href="anthropic/">
    <span class="integration-logo"><img src="../../images/integrations/llms/anthropic.svg" alt="" loading="lazy"></span>
    <span class="integration-name">Anthropic</span>
  </a>
  <a class="integration-card" href="langchain/">
    <span class="integration-logo"><img src="../../images/integrations/llms/langchain.svg" alt="" loading="lazy"></span>
    <span class="integration-name">LangChain</span>
  </a>
  <a class="integration-card" href="litellm/">
    <span class="integration-logo integration-logo--mark">Li</span>
    <span class="integration-name">LiteLLM</span>
  </a>
  <a class="integration-card" href="dspy/">
    <span class="integration-logo"><img src="../../images/integrations/llms/dspy.svg" alt="" loading="lazy"></span>
    <span class="integration-name">DSPy</span>
  </a>
  <a class="integration-card" href="mcp/">
    <span class="integration-logo"><img src="../../images/integrations/llms/mcp.svg" alt="" loading="lazy"></span>
    <span class="integration-name">MCP</span>
  </a>
  <a class="integration-card" href="claude-agent-sdk/">
    <span class="integration-logo"><img src="../../images/integrations/llms/claude-agent-sdk.svg" alt="" loading="lazy"></span>
    <span class="integration-name">Claude Agent SDK</span>
  </a>
  <a class="integration-card" href="llamaindex/">
    <span class="integration-logo"><img src="../../images/integrations/llms/llamaindex.svg" alt="" loading="lazy"></span>
    <span class="integration-name">LlamaIndex</span>
  </a>
  <a class="integration-card" href="mirascope/">
    <span class="integration-logo"><img src="../../images/integrations/llms/mirascope.svg" alt="" loading="lazy"></span>
    <span class="integration-name">Mirascope</span>
  </a>
  <a class="integration-card" href="magentic/">
    <span class="integration-logo integration-logo--mark">Ma</span>
    <span class="integration-name">Magentic</span>
  </a>
</div>

## Not listed?

Any OpenTelemetry-compatible LLM SDK can send to Logfire. See [Alternative clients](../../how-to-guides/alternative-clients.md) for the generic pattern.
