---
title: "What sandbox code can and cannot do"
description: "The Python features, standard library modules, and resource limits available to code in Agent Sandboxes."
---

# What sandbox code can and cannot do

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

See [Monty's limitations](https://github.com/pydantic/monty) for the full list. A model usually rewrites a script that
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

Each run of a script in Agent Sandboxes (one `feed_run()` call) has these limits:

| Limit | Value | What happens when code goes over it |
| ----- | ----- | ----------------------------------- |
| Processing time | 50 milliseconds | `MontyRuntimeError: TimeoutError: feed time limit exceeded` |
| Memory | 20 MiB | `MontyRuntimeError: MemoryError: memory limit exceeded` |

Time that the script spends waiting for your functions does not count toward the processing time. A script that makes
100 calls to a slow API and then filters the results stays well inside the limit. A script that does heavy computation
does not. Do heavy computation in your own functions, or in your database query.

Saved sessions and snapshots are kept for 7 days. See [Persist, resume, and fork sessions](sessions.md).

## Turn off tracing

By default, Logfire records each script, its inputs, each function call's arguments and result, and the final result in
your project. To stop recording them, pass `instrument=False`:

```python skip-run="true" skip-reason="external-connection"
import logfire

pool = logfire.agent_sandboxes(instrument=False)
```

Code and data still pass through Logfire's servers to run.

## Coming soon

These are not documented yet:

- Pricing and plan limits
- Which data regions run sandboxes
- Running sandboxes in a self-hosted Logfire deployment
- Giving sandboxes persistent storage, and connecting them to MCP servers

## Next steps

- [Run code from Python](python.md): run your first script.
- [Add a code tool to any agent](any-framework.md): tell the model these limits in the tool description.
