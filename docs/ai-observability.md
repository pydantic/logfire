---
title: "AI & LLM Observability"
description: "See every agent decision, tool call, and downstream service in one trace with Pydantic Logfire."
---

# AI & LLM Observability

<div class="agent-observability-intro">

<p class="agent-observability-intro__lede">See every decision your agent makes and everything it triggers. Tell a prompt problem from a service problem before you change production.</p>

<div class="agent-observability-intro__detail">

<div class="agent-observability-intro__detail-copy">

<p>Logfire turns an agent run into one trace (the full journey of one request or agent run, made of nested spans): the model calls, tool calls, database queries, API requests, and response your user receives.</p>

</div>

<figure class="agent-trace-hero">
  <svg class="agent-trace" viewBox="0 0 760 280" role="img" aria-labelledby="agent-trace-title agent-trace-desc"><title id="agent-trace-title">An agent trace with model, tool, and database work</title><desc id="agent-trace-desc">A complete agent run: the agent calls a model, then an inventory tool, which queries a database, before the agent returns a response. The database span is visibly slow, showing why full-stack context matters.</desc><rect class="agent-trace__frame" x="0.5" y="0.5" width="759" height="279" rx="14"/><text class="agent-trace__heading" x="28" y="29">trace · inventory-agent.run</text><text class="agent-trace__sample" x="682" y="29" text-anchor="end">sample run</text><g class="agent-trace__axis" aria-hidden="true"><line x1="170" y1="52" x2="718" y2="52"/><line x1="170" y1="47" x2="170" y2="57"/><line x1="307" y1="47" x2="307" y2="57"/><line x1="444" y1="47" x2="444" y2="57"/><line x1="581" y1="47" x2="581" y2="57"/><line x1="718" y1="47" x2="718" y2="57"/><text x="164" y="70">0</text><text x="293" y="70">500 ms</text><text x="433" y="70">1 s</text><text x="566" y="70">1.5 s</text><text x="701" y="70">2 s</text></g><g class="agent-trace__lanes" aria-hidden="true"><line x1="170" y1="95" x2="718" y2="95"/><line x1="170" y1="127" x2="718" y2="127"/><line x1="170" y1="159" x2="718" y2="159"/><line x1="170" y1="191" x2="718" y2="191"/></g><g class="agent-trace__labels"><text x="28" y="99">Agent</text><text x="28" y="131">LLM</text><text x="28" y="163">Tool</text><text x="28" y="195">Database</text></g><g class="agent-trace__spans"><rect class="agent-trace__span agent-trace__span--agent" x="170" y="85" width="548" height="20" rx="5"/><text class="agent-trace__span-label" x="182" y="99">inventory-agent.run</text><rect class="agent-trace__span agent-trace__span--llm" x="202" y="117" width="174" height="20" rx="5"/><text class="agent-trace__span-label" x="214" y="131">model.generate</text><text class="agent-trace__metric" x="388" y="131">1.8k tokens</text><rect class="agent-trace__span agent-trace__span--tool" x="398" y="149" width="306" height="20" rx="5"/><text class="agent-trace__span-label" x="410" y="163">search_inventory</text><rect class="agent-trace__span agent-trace__span--database" x="432" y="181" width="259" height="20" rx="5"/><text class="agent-trace__span-label" x="444" y="195">SELECT inventory</text><text class="agent-trace__span-label" x="678" y="195" text-anchor="end">1.2 s</text></g><line class="agent-trace__annotation-divider" x1="28" y1="218" x2="732" y2="218"/><text class="agent-trace__annotation-heading" x="28" y="238">Here's what happened</text><text class="agent-trace__annotation-static" x="28" y="262">One trace gives you evidence to investigate a wrong or slow answer.</text><g class="agent-trace__annotations" aria-hidden="true"><text class="agent-trace__annotation agent-trace__annotation--agent" x="28" y="262">The agent starts working on the question.</text><text class="agent-trace__annotation agent-trace__annotation--llm" x="28" y="262">The model decides it needs inventory information.</text><text class="agent-trace__annotation agent-trace__annotation--tool" x="28" y="262">The tool asks the inventory service for that information.</text><text class="agent-trace__annotation agent-trace__annotation--database" x="28" y="262">The inventory lookup takes 1.2 seconds.</text></g></svg>
</figure>

</div>

<div class="agent-observability-intro__prerequisite" markdown>

**Before you explore:** this page explains what Logfire can show once your application is sending traces. [Send your first trace →](first-trace.md)

</div>

</div>

## Follow the complete agent loop

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--agent"></span> [__Inspect a single run__](guides/web-ui/llm-panels.md)

  Read the messages, model settings, tool arguments, results, tokens, cost, and latency that produced one answer.

- <span class="lf-icon lf-icon--trace"></span> [__See the work behind each tool__](guides/web-ui/live.md)

  Follow a tool call into the database, API, queue, or service it touched. The trace keeps the causal chain intact.

- <span class="lf-icon lf-icon--metrics"></span> [__Find expensive or unreliable paths__](guides/web-ui/llms.md)

  Compare models and agent runs by cost, error rate, latency, tokens, tool calls, and turns. Then drill into the trace.

</div>

## From a bad answer to a useful diagnosis

An agent recommends an item that cannot arrive by Friday. The trace can show two very different failures.

- The agent never passed the delivery constraint to `search_inventory`. That is a prompt, model, or tool-selection problem.
- The agent passed the constraint, but the inventory service returned stale delivery data. That is a system problem.

Both failures look like a bad answer to the user. They need different fixes. Logfire keeps the agent's decisions and the work they triggered in the same trace, so you can change the right part of the system.

## Improve the next run with evidence

<div class="grid cards" markdown>

- <span class="lf-icon lf-icon--evals"></span> [__Turn failures into evals__](evaluate/overview.md)

  Build datasets from the cases that matter, compare changes before release, and score live traffic after it ships.

- <span class="lf-icon lf-icon--path"></span> [__Iterate on prompts safely__](reference/advanced/prompt-management/index.md)

  Version prompts, test them against representative inputs, and promote the version that performs better.

- <span class="lf-icon lf-icon--sql"></span> [__Ask production data better questions__](how-to-guides/mcp-server.md)

  Query traces with SQL yourself, or connect the Logfire MCP server so your coding agent can investigate with you.

</div>

## Instrument the stack you have

Start with a one-line integration for [Pydantic AI](integrations/llms/pydanticai.md), [OpenAI](integrations/llms/openai.md), [Anthropic](integrations/llms/anthropic.md), [LangChain](integrations/llms/langchain.md), or another supported framework. Logfire also accepts [OpenTelemetry (OTel), the open industry standard for collecting traces, metrics, and logs](how-to-guides/alternative-clients.md), so a TypeScript frontend, Python agent service, and Go backend can all appear in the same trace.

[See all integrations →](integrations/index.md)

## Control cost and routing (optional)

To cap what your app can spend on models, fail over between providers, or keep one API key for many models, route your calls through the [AI Gateway](reference/advanced/gateway/index.md). This is optional: the instrumentation above is all you need to trace and debug your agents.
