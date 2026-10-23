---
title: "Add a code tool to any agent"
description: "Give an agent built with any framework, or none, one run_code tool that runs its Python in Agent Sandboxes."
---

# Add a code tool to any agent

Give your agent one tool, `run_code`, that takes a Python script, runs it in an [Agent Sandbox](index.md), and returns
the result. The script can call the functions you choose. This works with any agent framework that supports tool
calls, and with a model API that you call directly.

If you use Pydantic AI, use [its built-in support](pydantic-ai.md) instead. It builds this tool from your existing
tools.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
permission to run code in agent sandboxes.

## Write the tool

The tool needs three things:

- **The functions the script may call**, in `external_lookup`.
- **A description that lists those functions**, as Python signatures. This is all the model knows about them. The same
  text is the type stub that the sandbox checks the script against.
- **Error handling that returns errors as text.** A model that sees why its script failed usually fixes it on the next
  try.

```python title="code_tool.py" skip-run="true" skip-reason="external-connection"
import logfire
from pydantic_monty import MontyError, MontyTypingError


async def get_order(order_id: str) -> dict:
    return {'id': order_id, 'status': 'shipped', 'items': 3}  # replace with a call to your order system


TOOLS = {'get_order': get_order}

STUBS = """
async def get_order(order_id: str) -> dict:
    '''Return one order, with its `status` and number of `items`.'''
"""

RUN_CODE_DESCRIPTION = f"""Run a Python script and return the value of its last expression.
The script can `await` these functions, and run several at once with `asyncio.gather`:
{STUBS}
Only a subset of Python is available. There is no network or file access, and no third-party packages."""

logfire.configure()
pool = logfire.agent_sandboxes()


async def run_code(code: str) -> str:
    async with pool.checkout(type_check=True, type_check_stubs=STUBS, ephemeral=True) as session:
        try:
            result = await session.feed_run(code, external_lookup=TOOLS)
        except MontyTypingError as e:
            return f'The script did not run, because it has type errors:\n{e.display()}'
        except MontyError as e:
            return f'The script failed: {e}'
    return repr(result)
```

`logfire.agent_sandboxes()` does not connect until the first `checkout()`. Enter the pool once when your application
starts (`await pool.__aenter__()`, or `async with pool:` around your server), and leave it open. Each `run_code` call
checks out a fresh session, so one agent run cannot see another's variables. `ephemeral=True` tells Logfire not to
store the session when it closes, because nothing will load it again. Stored sessions count toward your organization's
storage limit. To keep variables between calls, see [Keep an agent's work across conversation
turns](conversations.md).

## Register it with your agent

Register `run_code` as a tool with one string parameter, `code`, and use `RUN_CODE_DESCRIPTION` as its description. For
example, as a JSON Schema tool definition, the format most model APIs accept:

```json
{
  "name": "run_code",
  "description": "<RUN_CODE_DESCRIPTION>",
  "input_schema": {
    "type": "object",
    "properties": {"code": {"type": "string", "description": "The Python script to run."}},
    "required": ["code"]
  }
}
```

When the model calls the tool, pass its `code` argument to `run_code` and return the string as the tool result.

Remove the tools that the script can call from the agent's own tool list. If the model can call `get_order` both ways,
it often calls it directly, one order per turn.

## Test it without a model

Call the tool with the kind of script a model writes, and with one that has a mistake:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

from code_tool import pool, run_code


async def main():
    async with pool:
        print(await run_code("import asyncio\norders = await asyncio.gather(get_order('o1'), get_order('o2'))\n[o['status'] for o in orders]"))
        print(await run_code("await get_order(42)"))


asyncio.run(main())
```

Run `python main.py`. The first script returns its result. The second script does not run, and the tool returns the
error that the model will see:

```
['shipped', 'shipped']
The script did not run, because it has type errors:
error[invalid-argument-type]: Argument to function `get_order` is incorrect
 --> main.py:1:17
  |
1 | await get_order(42)
  |                 ^^ Expected `str`, found `Literal[42]`
info: Function defined here
 --> repl_type_stubs.pyi:2:11
  |
2 | async def get_order(order_id: str) -> dict:
  |           ^^^^^^^^^ ------------- Parameter declared here
3 |     '''Return one order, with its `status` and number of `items`.'''
  |
```

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see a `run code` span for each script, and a span for each
`get_order` call inside the first one. If your agent framework sends traces to Logfire, the sandbox spans appear inside
the agent's trace, under the tool call that ran them.

## Troubleshooting

- **The model calls your functions directly instead of writing a script**: the functions are still registered as
  separate tools. Remove them, so `run_code` is the only way to reach them.
- **The model writes code that the sandbox does not support**, such as `import pandas`: add the limits to the
  description in plain words. See [What sandbox code can do](limits.md) for the list.
- **The model forgets to `await`**: the type check reports it. Keep `type_check=True` so the model gets the error
  before the script runs.

## Next steps

- [Answer questions that need dozens of tool calls](many-tool-calls.md): the kind of question this tool is for.
- [Pause agent code for human approval](approval.md): stop a script at a sensitive call.
- [Keep an agent's work across conversation turns](conversations.md): keep the script's variables between turns.
