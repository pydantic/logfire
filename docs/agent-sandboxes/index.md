---
title: "Run untrusted agent code in Logfire Agent Sandboxes"
description: "What Logfire Agent Sandboxes are, when to use them, and how they fit with tracing."
---

# Agent Sandboxes

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

Let your AI agents answer a question with one short Python script instead of dozens of tool calls.
Logfire Agent Sandboxes run each script in an isolated, remote Python environment hosted by Logfire.
The script calls your tools as functions, does the work in Python, and returns only the answer.

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

logfire.configure()


def get_temperature(city: str) -> float:  # runs in your application
    return {'London': 14.0, 'Paris': 17.5, 'Tokyo': 21.0}[city]


AGENT_CODE = """
cities = ['London', 'Paris', 'Tokyo']
temperatures = {city: get_temperature(city) for city in cities}
max(cities, key=lambda city: temperatures[city])
"""  # written by your agent, runs in the sandbox


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            print(await session.feed_run(AGENT_CODE, external_lookup={'get_temperature': get_temperature}))


asyncio.run(main())
```

This prints `Tokyo`. The script made three tool calls, and the model reads one word.
[Run code from Python](python.md) shows how to set this up.

## What this changes

We ran the same tasks with a Pydantic AI agent and `gpt-6.1-sol`, with plain tool calls and with Agent Sandboxes:

| Task | Plain tool calls | Agent Sandboxes |
| --- | --- | --- |
| [Check a week of request counts for 40 customers](many-tool-calls.md): input tokens (median) | 111,162 | 4,680 |
| The same task: correct answers | 1 of 3 | 3 of 3 |
| [Refund 37 orders after one approval](approval.md): approval requests for the person | 37 | 1 |

These are three-run results on fixed sample data, not a prediction of production accuracy or cost.
Each guide gives the full results, including the cases where a sandbox did not help.

## Why run agent code in a sandbox

Many agents work better when they can write code instead of calling tools one at a time.
With plain tool calls, every result goes into the model's context, and the model does the arithmetic by reading.
A script keeps the rows in Python variables, and Python does the arithmetic.

But model-generated code can contain mistakes or unsafe operations.
Running it in your application process would give it access to your files, network, and secrets.

A **sandbox** is an isolated environment that runs code with no access to the machine around it.
Agent Sandboxes use [Pydantic Monty](https://pydantic.dev/docs/monty/), a Python interpreter written in Rust and
designed for sandboxing.
Code in a sandbox can only reach the outside world through functions you choose to expose to it.
Monty is not a container or a virtual machine. A session has no image to build and no operating system to start.

With Agent Sandboxes, Logfire runs the sandboxes for you:

- **No sandbox infrastructure to run**: you don't deploy, scale, or patch anything.
- **Isolation from your application**: agent code runs on Logfire's servers, not in your process.
- **Host functions**: you pass your own Python functions to a run, and the sandbox calls back to your application to run
  them.
  Your application stays in control of what the code can touch.
- **Sessions that keep state**: variables and functions defined in one run are available in the next run of the same
  session, so an agent can build up work step by step.
- **Saved sessions**: unless you choose an ephemeral session, Logfire saves its state under a session ID.
  Resume it from a new connection, take a snapshot as a checkpoint, or fork it into independent branches.
  A script can [pause for a person's approval](approval.md) and continue days later, from another process.
- **A type check before the code runs**: the sandbox can check a script against your function signatures, and return
  the errors to the model before any of the script runs. See [Expose a typed module](typed-api.md).
- **Tracing included**: Logfire records each session, code run, and tool call as a span inside your application's
  trace. You can read the script an agent wrote and every value it used.

## How it works

Your application opens a connection to the Agent Sandboxes server in your Logfire [data
region](../reference/data-regions.md), using **gRPC** over one long-lived HTTP/2 connection between your application
and the server.
Each time you check out a session, the server gives you a dedicated sandbox.
You send code to it, and it sends back the result, printed output, and any calls to your host functions.
When the session ends, the sandbox is released.

```
your application                         Logfire Agent Sandboxes
────────────────                         ───────────────────────
checkout()      ─────── gRPC stream ──────▶  dedicated sandbox
feed_run(code)  ───────── code ─────────▶    runs the code
host function   ◀──── function call ─────    calls get_weather('London')
                ───── function result ───▶
result          ◀──────── result ────────    returns the final value
```

You authenticate with a [non-personal project API key](python.md#get-an-execution-key) that has permission to run code in your project's agent sandboxes
(`project:execute_agent_sandboxes`).

!!! warning "Code and data are sent to Logfire"
    The code you run, its inputs, host function arguments and results, and
    printed output are sent to Logfire's servers to be executed.
    The hosted runtime also records sandbox activity in your project.
    Client [scrubbing](../how-to-guides/scrubbing.md) does not remove values from execution requests or saved session state.
    See [tracing and storage](limits.md#understand-tracing-and-storage).

## Choose a workflow

| Your task | Start here |
| --- | --- |
| Answer a question that needs dozens of tool calls | [Call tools from one script](many-tool-calls.md) |
| Reduce thousands of rows before the model reads them | [Work with large tool results](large-results.md) |
| Give an agent a whole API, checked before it runs | [Expose a typed module](typed-api.md) |
| Stop at a sensitive action, and continue hours later | [Pause for approval](approval.md) |
| Keep loaded data for follow-up questions | [Keep a session across turns](conversations.md) |

## When not to use Agent Sandboxes

- **The code is your own.** Code you wrote and reviewed doesn't need a sandbox.
- **The code needs third-party packages, a file system of its own, or a shell.** Use a container-based sandbox for
  that work, or do it in a function that the sandbox calls.
- **The code needs Python features that Monty doesn't support.** Monty runs a subset of Python.
  See [What sandbox code can do](limits.md).
- **You need to run code offline or entirely on your own machines.** Run Monty locally with the `pydantic-monty` package
  instead, and [trace it with Logfire](../integrations/monty.md).

## Next steps

Start with [Run code from Python](python.md) to run your first script.
To connect your agent, see [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md) or [Add a code tool to any
agent](any-framework.md). Then pick a guide from [Choose a workflow](#choose-a-workflow).

## Use the web UI

Open **AI Runtime** > **Agent Sandboxes** in your project.
If you do not see it, [turn on the page](python.md#enable-agent-sandboxes) first.
For a new project, choose **Use Agent Sandboxes** during [product onboarding](python.md#enable-agent-sandboxes).
If the project shows **Enable Agent Sandboxes**, ask a project manager to enable it.
Sandboxes start on first use and shut down when idle.
The project counts toward your organization's enabled-project limit until you disable it.

- [Run code in the Workbench](workbench.md): try Python without installing a local client.
- [Manage saved snapshots](snapshots.md): find saved Python state, open it in the Workbench, and free storage.
- [Manage profiles](profiles.md): create and select a named profile for a session.
- [Share files between sessions](volumes.md): mount persistent files in a profile.
- [Inspect sandbox runs](inspect.md): read recorded source and follow related calls in Live view.

### Disable Agent Sandboxes

To disable Agent Sandboxes for a project, open **Setup** and select **Disable Agent Sandboxes** at the bottom of the page.
You need permission to manage the project.
Disabling stops running sessions, and no new sessions start.
Disabling does not delete your snapshots, profiles, volumes, or execution keys.
They work again if you enable the project again, unless they expired in the meantime.
Saved sessions and snapshots expire after [7 days](sessions.md#when-a-session-is-saved).
Keys created on the setup page expire after [30 days](python.md#get-an-execution-key).
