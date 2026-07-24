---
title: "For AI engineers"
description: "A starting path for engineers building LLM apps and agents: instrument your app, see the conversations and cost, evaluate output quality, and manage prompts without redeploying."
---

# For AI engineers

You're building on a large language model, and the hardest part isn't the first demo, it's knowing what the model actually did on a real request and whether the answers are good. This path takes you from your first instrumented call to seeing every conversation and its cost, then to measuring quality and changing prompts without shipping code.

Follow these in order. Each link says why it's here.

## Your path

1. **[See what your AI is actually doing](../ai-observability.md)**: start here for the big picture: how Logfire records the model's conversation, its tool calls, tokens (the units a model reads and writes, and bills by), and cost, alongside the code around it. A **trace** is the full record of one request; a **span** is one step inside it.

2. **Instrument your LLM library**: one line turns on tracing for the library you already use:
    - [OpenAI](../integrations/llms/openai.md)
    - [Anthropic](../integrations/llms/anthropic.md)
    - [Pydantic AI](../integrations/llms/pydanticai.md) (for agents)
    - [LangChain](../integrations/llms/langchain.md), [LlamaIndex](../integrations/llms/llamaindex.md), [LiteLLM](../integrations/llms/litellm.md), [Google GenAI](../integrations/llms/google-genai.md)

    See the full list under [LLM integrations](../integrations/index.md).

3. **[Read every LLM call, with tokens and cost](../guides/web-ui/llms.md)**: once data is flowing, the LLMs and providers view breaks down which models you're calling, how many tokens each request used, and what it's costing you.

4. **[Evaluate your AI: measure output quality](../evaluate/overview.md)**: move from "it looks fine" to a number. An **evaluation** runs your AI over a set of test cases and scores the output. A **scorer** is the rule that produces a **score**: one saved rating from a human, your own code, or an LLM acting as judge.

5. **[Change a prompt without shipping code](../reference/advanced/prompt-management/index.md)**: version your prompts outside your codebase so you can test a new wording, promote it to production, and roll it back, all without a redeploy.

## Try the full journey

- **[Instrument and evaluate an agent](../cookbook/evaluate-an-agent.md)**: a start-to-finish walkthrough: build a small agent, see its traces, then score its answers with an evaluation.
- **[Debug a slow tool call](../cookbook/debug-a-slow-tool-call.md)**: when your agent is slow, prove in one trace whether it's the model or a tool, and find the query behind it.
- **[Roll out a prompt safely](../cookbook/roll-out-a-prompt-safely.md)**: change a live prompt, watch the effect, and roll back if it gets worse.
- **[Track LLM cost](../cookbook/track-llm-cost.md)**: turn token usage into a dashboard and an alert so a runaway bill can't surprise you.
