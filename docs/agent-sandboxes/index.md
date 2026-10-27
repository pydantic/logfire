---
title: "Run untrusted agent code in Logfire Agent Sandboxes"
description: "What Logfire Agent Sandboxes are, when to use them, and how they fit with tracing."
---

# Agent Sandboxes

!!! info "Experimental"
    Agent Sandboxes is experimental and available to selected Logfire organizations. Email
    [engineering@pydantic.dev](mailto:engineering@pydantic.dev) if you want to try it.

Let your AI agents write and run Python without running that code on your own servers.
Logfire Agent Sandboxes run each piece of code in an isolated, remote Python environment hosted by Logfire, and send the
result back to your application.

## Why run agent code in a sandbox

Many agents work better when they can write code instead of calling tools one at a time.
For example, an agent can write a short loop that calls a search tool ten times and combines the results.
But model-generated code can contain mistakes or unsafe operations.
Running it in your application process would give it access to your files, network, and secrets.

A **sandbox** is an isolated environment that runs code with no access to the machine around it.
Agent Sandboxes use [Pydantic Monty](https://github.com/pydantic/monty), a Python interpreter written in Rust and
designed for sandboxing.
Code in a sandbox can only reach the outside world through functions you choose to expose to it.

With Agent Sandboxes, Logfire runs the sandboxes for you:

- **Managed sandboxes**: Logfire deploys, scales, and patches the sandbox service.
- **Isolation from your application**: agent code runs on Logfire's servers, not in your process.
- **Sessions that keep state**: variables and functions defined in one run are available in the next run of the same
  session, so an agent can build up work step by step.
- **Persistent sessions, snapshots, and forks**: unless you choose an ephemeral session, Logfire saves its state under a session ID. You can resume it
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

You authenticate with a Logfire API key that has permission to run code in your project's agent sandboxes
(`project:execute_agent_sandboxes`).

!!! warning "Code and data are sent to Logfire"
    The code you run, its inputs, host function arguments and results, and
    printed output are sent to Logfire's servers to be executed.
    The default client instrumentation also records this content in your project. It applies Logfire's standard
    [scrubbing](../how-to-guides/scrubbing.md) before it sends telemetry. Scrubbing does not remove values from the
    execution request or saved session state. See [tracing and storage controls](limits.md#control-client-tracing).

## Choose a workflow

| Your task | Start here |
| --- | --- |
| Fetch many tool results and calculate an answer | [Call tools from Python](many-tool-calls.md) |
| Compare large results from several sources | [Reduce results before the model reads them](large-results.md) |
| Check calls against an API's types | [Expose a typed module](typed-api.md) |
| Wait for a person before an action | [Pause for approval](approval.md) |
| Reuse data in a later conversation turn | [Keep a session across turns](conversations.md) |

## When not to use Agent Sandboxes

- **You only need to run trusted application code.** Run it directly when it does not need the sandbox's isolation or session features.
- **The code needs Python features that Monty doesn't support.** Monty runs a subset of Python.
  Check [what Monty supports](https://pydantic.dev/docs/monty/limitations/) before you rely on a feature.
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

### Use the web UI

Open **AI Optimization** > **Agent Sandboxes** in your project.
If the project shows **Enable Agent Sandboxes**, ask a project manager to enable it.
Sandboxes start on first use and shut down when idle.
The project counts toward your organization's enabled-project limit until you disable it.
The available tabs depend on the features enabled for your organization.

- [Run code in the Workbench](workbench.md): try Python without installing a local client.
- [Manage saved snapshots](snapshots.md): find saved Python state, open it in the Workbench, and free storage.
- [Manage profiles](profiles.md): create and select a named profile for a session.
- [Share files between sessions](volumes.md): mount persistent files in a profile when volume access is enabled.
- [Inspect sandbox runs](inspect.md): read recorded source and follow related calls in Live view.
