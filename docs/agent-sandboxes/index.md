---
title: "Run untrusted agent code in Logfire Agent Sandboxes"
description: "What Logfire Agent Sandboxes are, when to use them, and how they fit with tracing."
---

# Agent Sandboxes

Let your AI agents write and run Python without running that code on your own servers.
Logfire Agent Sandboxes run each piece of code in an isolated, remote Python environment hosted by Logfire, and send the
result back to your application.

## Why run agent code in a sandbox

Many agents work better when they can write code instead of calling tools one at a time.
For example, an agent can write a short loop that calls a search tool ten times and combines the results.
But the code comes from a model, so you can't trust it.
Running it in your application process would give it access to your files, network, and secrets.

A **sandbox** is an isolated environment that runs code with no access to the machine around it.
Agent Sandboxes use [Pydantic Monty](https://github.com/pydantic/monty), a Python interpreter written in Rust and
designed for sandboxing.
Code in a sandbox can only reach the outside world through functions you choose to expose to it.

With Agent Sandboxes, Logfire runs the sandboxes for you:

- **No sandbox infrastructure to run**: you don't deploy, scale, or patch anything.
- **Isolation from your application**: agent code runs on Logfire's servers, not in your process.
- **Sessions that keep state**: variables and functions defined in one run are available in the next run of the same
  session, so an agent can build up work step by step.
- **Persistent sessions, snapshots, and forks**: each session's state is saved under a session ID, so you can resume it
  from a new connection, take a snapshot as a checkpoint, or fork it into independent branches.
- **Host functions**: you pass your own Python functions to a run, and the sandbox calls back to your application to run
  them.
  Your application stays in control of what the code can touch.
- **Tracing included**: each session and code run is recorded as a **span** (one unit of work: a single operation, with
  a name, a start, and a duration) inside your application's **trace** (the full journey of one request, made of nested
  spans).

## How it works

Your application opens a connection to the Agent Sandboxes server in your Logfire [data
region](../reference/data-regions.md), using a **WebSocket** (a long-lived, two-way connection between your application
and the server).
Each time you check out a session, the server gives you a dedicated sandbox.
You send code to it, and it sends back the result, printed output, and any calls to your host functions.
When the session ends, the sandbox is released.

```
your application                         Logfire Agent Sandboxes
────────────────                         ───────────────────────
checkout()      ── WebSocket connection ──▶  dedicated sandbox
feed_run(code)  ───────── code ─────────▶    runs the code
host function   ◀──── function call ─────    calls get_weather('London')
                ───── function result ───▶
result          ◀──────── result ────────    returns the final value
```

You authenticate with a Logfire API key that has the **Execute agent sandboxes** permission
(`project:execute_agent_sandboxes`).

!!! warning "Code and data are sent to Logfire" The code you run, its inputs, host function arguments and results, and
printed output are sent to Logfire's servers to be executed.
With tracing on (the default), they are also recorded in your Logfire project, after Logfire's standard
[scrubbing](../how-to-guides/scrubbing.md) hides sensitive values such as passwords and tokens.

## When not to use Agent Sandboxes

- **The code is your own.** Code you wrote and reviewed doesn't need a sandbox.
- **The code needs Python features that Monty doesn't support.** Monty runs a subset of Python.
  Check [what Monty supports](https://github.com/pydantic/monty) before you rely on a feature.
- **You need to run code offline or entirely on your own machines.** Run Monty locally with the `pydantic-monty` package
  instead, and [trace it with Logfire](../integrations/monty.md).

## Next steps

Start with [Run code from Python](python.md) to run your first script. Then pick the guide for what you want your agent
to do:

- [Answer questions that need dozens of tool calls](many-tool-calls.md): one script instead of a tool call per item.
- [Work with large tool results](large-results.md): reduce thousands of rows to the answer before the model reads them.
- [Give an agent a whole API](typed-api.md): one typed module instead of a tool per operation, checked before it runs.
- [Pause agent code for human approval](approval.md): stop at a sensitive call and continue hours later.
- [Keep an agent's work across conversation turns](conversations.md): keep loaded data for follow-up questions.

To connect your agent, see [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md) or [Add a code tool to any
agent](any-framework.md). For what scripts can run, see [What sandbox code can do](limits.md).
