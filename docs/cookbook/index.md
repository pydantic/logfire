---
title: "Cookbook: end-to-end guides"
description: "Runnable, real-world walkthroughs that stitch Logfire's features into one journey: instrument and evaluate an agent, debug a slow endpoint or tool call, roll out a prompt safely, and track LLM cost."
---
# Cookbook

The Cookbook is a set of **end-to-end guides**: each follows a real goal from start to finish, stitching several Logfire features into one journey. Where the feature pages tell you *what each part does*, these show you *how they fit together* to get a job done. Every guide is runnable: copy the code, send the data, and see the result in Logfire.

## Guides

- **[Instrument and evaluate an agent](evaluate-an-agent.md)**: build a Pydantic AI agent, see its traces, tokens, and cost, then measure its quality with evals (repeatable tests of an AI's output quality) and catch a regression. *~25 min · for AI engineers.*
- **[Debug a slow endpoint](debug-a-slow-endpoint.md)**: trace a slow request in a FastAPI + Postgres app down to the exact SQL query behind it, and fix it. *~15 min · for backend and site reliability engineers.*
- **[Debug a slow tool call](debug-a-slow-tool-call.md)**: prove in one trace that a slow agent is stuck in a tool, not the model, and find the slow query inside it. *~15 min · for AI engineers.*
- **[Roll out a prompt safely](roll-out-a-prompt-safely.md)**: change a prompt, test it, promote it with a label, and roll it back, without a redeploy. *~15 min · for AI engineers.*
- **[Track and alert on LLM cost](track-llm-cost.md)**: capture the cost of your LLM calls, chart it on a dashboard, and get alerted when spend spikes. *~15 min · for AI engineers and engineering leads.*

## New to Logfire?

Start with the [quickstart](../index.md) to send your first trace, or pick your [path by role](../get-started/choose-your-path.md).
