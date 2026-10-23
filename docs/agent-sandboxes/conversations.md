---
title: "Keep an agent's work across conversation turns"
description: "Give each conversation its own sandbox session, so data an agent loaded in one turn is still there for the next question."
---

# Keep an agent's work across conversation turns

A person asks your data agent "which customers churned last quarter?", then "which of those had open tickets?", then
"show me the three biggest". If each turn starts from nothing, the agent fetches the same customers three times, or
pastes them back into the conversation so it can read them again.

With Agent Sandboxes, each conversation gets its own sandbox session. Variables that the agent's script defines in one
turn, such as `churned`, are still defined in the next turn. The next script starts from them. The data stays in the
sandbox, not in the model's **context window** (the text the model reads on each turn).

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key
  with the **Execute agent sandboxes** permission.
- Have a `run_code` tool. See [Add a code tool to any agent](any-framework.md). This page changes it to keep one
  session for each conversation.

!!! warning "Session state is stored by Logfire for 7 days"
    The variables a session holds, including values computed from your data, are stored by Logfire so that a later turn
    can load them. Logfire deletes them 7 days after they are saved. See
    [Persist, resume, and fork sessions](sessions.md).

## Define the functions the agent can call

These sample functions stand in for your customer and support systems:

```python title="tools.py" skip-run="true" skip-reason="external-connection"
async def list_customers() -> list[dict]:
    return [  # replace with a call to your customer system
        {'id': 'c1', 'name': 'Acme', 'churned_at': '2026-08-14'},
        {'id': 'c2', 'name': 'Globex', 'churned_at': None},
        {'id': 'c3', 'name': 'Initech', 'churned_at': '2026-09-02'},
    ]


async def list_open_tickets(customer_id: str) -> list[dict]:
    return [{'id': 'T-7', 'title': 'Export is slow'}] if customer_id == 'c3' else []


TOOLS = {'list_customers': list_customers, 'list_open_tickets': list_open_tickets}

STUBS = """
async def list_customers() -> list[dict]:
    '''Every customer, with `id`, `name`, and `churned_at` (an ISO date, or None).'''
async def list_open_tickets(customer_id: str) -> list[dict]:
    '''A customer's open support tickets, with `id` and `title`.'''
"""
```

## Store a session ID for each conversation

When a session closes, Logfire saves its state under `session.session_id`. Store that ID with the conversation. On the
next turn, check out a new session and load the stored ID into it. Loading gives the new session a new ID, so store the
new one when the turn ends.

```python title="code_tool.py" skip-run="true" skip-reason="external-connection"
import logfire
from pydantic_monty import MontyError, MontyTypingError

from tools import STUBS, TOOLS

pool = logfire.agent_sandboxes()

session_ids: dict[str, bytes] = {}  # use your database: one row per conversation


async def run_code(conversation_id: str, code: str) -> str:
    async with pool.checkout(type_check=True, type_check_stubs=STUBS) as session:
        if conversation_id in session_ids:
            await session.load_session(session_ids[conversation_id])
        try:
            result = await session.feed_run(code, external_lookup=TOOLS)
        except MontyTypingError as e:
            return f'The script did not run, because it has type errors:\n{e.display()}'
        except MontyError as e:
            return f'The script failed: {e}'
        finally:
            session_ids[conversation_id] = session.session_id
    return repr(result)
```

`conversation_id` comes from your application, not from the model. Pass it to the tool yourself, for example from the
tool's context in your agent framework.

## See a conversation reuse its data

Over two turns, a model writes two scripts. The second one uses `churned` from the first, without fetching it again:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

from code_tool import pool, run_code

logfire.configure()

TURN_1 = """
customers = await list_customers()
churned = [c for c in customers if c['churned_at'] and c['churned_at'] >= '2026-07-01']
len(churned)
"""

TURN_2 = """
import asyncio

tickets = await asyncio.gather(*[list_open_tickets(c['id']) for c in churned])
[c['name'] for c, ts in zip(churned, tickets) if ts]
"""


async def main():
    async with pool:
        print(await run_code('conversation-1', TURN_1))
        print(await run_code('conversation-1', TURN_2))


asyncio.run(main())
```

Run `python main.py`. It prints the answer to each turn:

```
2
['Initech']
```

In a new session, the second script would fail with `NameError: name 'churned' is not defined`. Here it finds `churned`
from the first turn.

Turns do not need to come from the same process. A conversation can continue on another server, or days later, as long
as the stored session ID is less than 7 days old.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see one `run code` span for each turn. The second turn's
span has `list_open_tickets` calls, but no `list_customers` call.

## Troubleshooting

- **`MontyRuntimeError: unknown session`** right after a turn: Logfire saves the session as it closes, which takes a
  moment. A turn that starts immediately after the previous one can try to load it too early. Retry the load after a
  short wait.
- **`NameError` for a variable from an earlier turn**: the stored ID is from an older turn. Check that you store
  `session.session_id` after every turn, including turns that failed.
- **A conversation is older than 7 days**: its saved state is gone. Start a new session, and let the agent fetch the
  data again.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): what a saved session holds, snapshots, and forks.
- [Work with large tool results](large-results.md): load large data once and keep it out of the context window.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): Pydantic AI can keep the session for each conversation for you.
