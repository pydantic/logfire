---
title: "What sandbox code can and cannot do"
description: "The Python features, standard library modules, and resource limits available to code in Agent Sandboxes."
---

# What sandbox code can and cannot do

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

Check here before you give an agent a task, so you know whether its script can do it. Agent Sandboxes run
[Pydantic Monty](https://github.com/pydantic/monty), a Python interpreter that supports the parts of Python agents use
to call functions and work with data. It does not support everything that Python does.

Sandbox code is good at calling your functions, looping, branching, and filtering, grouping, and reshaping data. For
work that needs third-party packages, files, or a shell, use a container-based sandbox, or run that work in a function
that the sandbox calls.

## Python features

Supported: functions (including `async def`, closures, and default arguments), `await` and `asyncio.gather`, list, dict,
and set comprehensions, f-strings, `try`/`except`, `match`, dataclasses, and type hints.

Not supported, among others:

- Classes that inherit from other classes, `@property`, `@classmethod`, and `@staticmethod`
- Generators (`yield`) and user-defined exception classes
- `async with`, `async for`, and `del`
- Keyword arguments to `asyncio.gather`, such as `return_exceptions=True`. The type check does not catch this.

See [Monty's limitations](https://pydantic.dev/docs/monty/limitations/) for the full list. A model usually rewrites a script that
uses an unsupported feature after it sees the error.

## Standard library

Available: `asyncio`, `base64`, `bisect`, `collections`, `copy`, `csv`, `dataclasses`, `datetime`, `functools`,
`hashlib`, `itertools`, `json`, `math`, `random`, `re`, `time`, `typing`, and some others.

Not available, among others: `enum`, `logging`, `statistics`, `decimal`, `uuid`, `io`, `sqlite3`, `subprocess`,
`socket`, and `urllib`.

No third-party packages can be installed. To give a script something a package does, such as parsing a PDF, write a
function in your application that uses the package, and pass that function to the sandbox.

## Files, network, and the environment

Sandbox code cannot open network connections, read environment variables, or read files on Logfire's servers. It can
reach the outside world only through the functions, modules, and directories that you pass in. Each of those runs or
lives in your application.

## Resource limits

The hosted service limits processing time for each run and memory for the session.
Variables retained from earlier runs still count toward the memory limit.

| Limit | Value | What happens when code goes over it |
| ----- | ----- | ----------------------------------- |
| Processing time per run | 50 milliseconds | `MontyRuntimeError: TimeoutError: feed time limit exceeded` |
| Session memory | 20 MiB | `MontyRuntimeError: MemoryError: memory limit exceeded`, or `MemoryError: the worker exceeded its memory limit and was terminated` for one large allocation. The session is lost in the second case. |

Time that the script spends waiting for your functions does not count toward the processing time. The calls can take longer than 50 milliseconds in total. But the Python work before, between, and after them still
counts toward the processing limit. Do heavy computation in your own functions, or in your database query.

In practice, a script can hold a few thousand rows of tool results at a time. A test with 5,000 rows of four short
fields stayed inside the limit. 20,000 rows did not.

Saved sessions and snapshots are kept for 7 days. They count toward your organization's snapshot storage limit.
Open [Snapshots](snapshots.md) to see the plan allowance, the enforced limit if it differs, and the stored object count.
Pending uploads and objects awaiting cleanup also count until cleanup finishes.
Use `checkout(ephemeral=True)` for sessions that nothing will load again. See [Persist, resume, and fork sessions](sessions.md).

Hosted [volumes](volumes.md) keep files between sessions when volume access is enabled for your organization.
They are separate from Python snapshots. Restoring a snapshot does not roll back volume files.

## Understand tracing and storage

The hosted runtime records sandbox sessions, code runs, and related activity in your project.
`logfire.agent_sandboxes()` sends the current trace context so hosted spans join your application's trace.
It does not enable the separate, process-wide `instrument_monty()` integration for local Monty pools.

Client [scrubbing](../how-to-guides/scrubbing.md) does not redact the code and values sent to the hosted runtime.
Check the source, inputs, and exposed host functions before you run untrusted code with sensitive data.

Session storage is separate from telemetry.
Use [ephemeral sessions](sessions.md#opt-out-of-storage-with-ephemeral-sessions) to avoid saved interpreter state.
Ephemeral sessions do not turn off hosted telemetry.
Do not send data that your application must keep entirely on its own machines.

## Coming soon

These are not documented yet:

- Pricing and plan limits
- Which data regions run sandboxes
- Running sandboxes in a self-hosted Logfire deployment
- Connecting sandboxes to Model Context Protocol (MCP) servers

## Next steps

- [Run code from Python](python.md): run your first script.
- [Add a code tool to any agent](any-framework.md): tell the model these limits in the tool description.
