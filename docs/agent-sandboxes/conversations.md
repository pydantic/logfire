---
title: "Keep an agent's work across conversation turns"
description: "Give each conversation its own sandbox session, so data an agent loaded in one turn is still there for the next question."
---

# Keep an agent's work across conversation turns

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

A person asks your data agent "which customers churned last quarter?", then "which of those had open tickets?", then
"show me the three biggest". If each turn starts from nothing, the agent fetches the same customers three times, or
pastes them back into the conversation so it can read them again.

With Agent Sandboxes, each conversation gets its own sandbox session. Variables that the agent's script defines in one
turn, such as `churned`, are still defined in the next turn. The next script starts from them. The data stays in the
sandbox, not in the model's **context window** (the text the model reads on each turn).

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key
  with permission to run code in agent sandboxes.
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

Store a saved session or checkpoint ID with the conversation.
On the next turn, check out a new session and load that ID into it.
Save a new checkpoint after each turn, then replace the stored ID.
The example uses `dump()` so the next turn does not race with connection cleanup.
The IDs are opaque bytes. The dictionary stores bytes directly.
For a text database field, encode with `.hex()` and decode with `bytes.fromhex()` before `load_session()`.
See [session ID storage](sessions.md#resume-a-session-from-a-new-connection).

This example relies on Logfire's enforced 7-day retention for saved state.
Each turn creates a checkpoint. Replacing its ID in the dictionary does not delete the previous checkpoint.
The closed session also consumes snapshot storage. Check the project's [snapshot quota](snapshots.md#delete-snapshots-and-check-storage) for high-volume conversations.
Delete superseded snapshots when you need to reclaim space sooner. Keep every checkpoint that a conversation still needs.

Process only one tool call at a time for each conversation. Concurrent calls can load the same old state and overwrite
each other's saved ID. If several servers handle the conversation, serialize those calls in your application and
store the mapping in a shared database. The dictionary below is a single-process example.

```python title="code_tool.py" skip-run="true" skip-reason="external-connection"
from pydantic_monty import MontyError, MontyTypingError
from tools import STUBS, TOOLS

import logfire

logfire.configure()
pool = logfire.agent_sandboxes()

session_ids: dict[str, bytes] = {}  # use your database: one row per conversation


async def run_code(conversation_id: str, code: str) -> str:
    async with pool.checkout(type_check=True, type_check_stubs=STUBS) as session:
        try:
            if conversation_id in session_ids:
                await session.load_session(session_ids[conversation_id])
        except MontyError as e:
            return (
                f'The previous session could not be loaded: {e}. Retry the load or explicitly reset the conversation.'
            )
        try:
            result = await session.feed_run(code, external_lookup=TOOLS)
        except MontyTypingError as e:
            response = f'The script did not run, because it has type errors:\n{e.display()}'
        except MontyError as e:
            response = f'The script failed: {e}'
        else:
            response = repr(result)
        session_id = await session.dump()
    session_ids[conversation_id] = session_id
    return response
```

`conversation_id` comes from your application, not from the model. Pass it to the tool yourself, for example from the
tool's context in your agent framework.

## See a conversation reuse its data

Over two turns, a model writes two scripts. The second one uses `churned` from the first, without fetching it again:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

from code_tool import pool, run_code

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

With a shared, persistent session-ID mapping, turns do not need to come from the same process. A conversation can continue on another server, or days later, as long
as the stored session ID is less than 7 days old.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see one `run code` span for each turn. The second turn's
span has `list_open_tickets` calls, but no `list_customers` call.

## Troubleshooting

- **`MontyRuntimeError: unknown session`**: the checkpoint may have expired, been deleted, or belong to another project.
  Check the stored ID and the API key's project. This example waits for `dump()` before it stores the ID.
  If you store `session.session_id` instead, wait for the connection to close and its save to finish before loading it.
- **`NameError` for a variable from an earlier turn**: the stored ID is from an older turn. Check that you store
  the checkpoint ID returned by `dump()`, including turns where the script failed. A failed load preserves the
  previous ID so a transient error does not silently discard the conversation state.
- **An unexpected host-function or connection error escapes `run_code`**: this example propagates errors outside `MontyError` and `MontyTypingError`.
  Its stored ID does not advance. Stop further turns for this conversation and inspect the failed run before recovery.
  Do not retry against the old ID as if it included the failed turn's changes.
- **The saved state is older than 7 days**: it has expired. Explicitly remove its ID from your application's mapping,
  then start a new session and let the agent fetch the data again. Do not reset the ID for every load failure.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): what a saved session holds, snapshots, and forks.
- [Work with large tool results](large-results.md): load large data once and keep it out of the context window.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): Pydantic AI can keep the session for each conversation for you.
