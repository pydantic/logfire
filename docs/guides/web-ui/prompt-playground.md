---
title: "Prompt Playground: Experiment with agent prompts"
description: "Prompt Playground: Experiment with agent prompts"
---
# Prompt Playground

The prompt playground gives you the ability to experiment with an agent run and its different parts. It is mostly useful when you want to iterate
on the system prompt, and see if you can get better results by tweaking it. Taking the following agent run as an example:

/// public-trace | https://logfire-eu.pydantic.dev/public-trace/bae009a7-e2cf-4c50-b623-bf255ebabe7c?spanId=26d6114284366b18
    title: 'Logfire instrumentation of an agent run'
///

Clicking **Open in Playground** will redirect you to the Agent Playground, prefilled with the agent run data:

![Prompt playground](../../images/guide/prompt-playground/prompt_playground.png)

You can then modify parts of the captured run, such as the system prompt, user requests, tool calls, available tools, or model settings, and trigger another run to see the results.

You can also configure which tools are available as well as the [model settings](https://ai.pydantic.dev/api/settings/) (for example, temperature).

## Compared with Prompt Management

The Prompt Playground is for exploratory iteration on a captured run. You tweak the system prompt, user messages, tool calls, or settings on that specific run and immediately re-execute it.

If you want a persistent prompt that your application imports from Logfire, use [Prompt Management](../../reference/advanced/prompt-management/index.md) instead. Prompt Management stores prompt templates and versions, plus testing artifacts such as saved scenarios and run history.
