---
title: "Pause agent code for human approval, and resume it later"
description: "Let an agent plan a batch of sensitive actions in one script, ask a person once, and finish the plan hours later from any process without calling the model again."
---

# Pause agent code for human approval, and resume it later

An incident charged 25 customers for 37 orders that then failed. A support agent can find the orders, refund each one,
and email each customer. But a person must approve the refunds first, and that person may answer in five minutes or
tomorrow.

With Agent Sandboxes, the agent writes the whole job as one script: find the orders, ask for approval once with the
complete plan, then refund and email. When the script reaches the approval, your application stops it, and Logfire
stores it. When the person decides, any process loads the script and it continues from that line, with every variable
it had. The model is not called again.

## What this changes

We gave this task to a Pydantic AI agent three times with Pydantic AI's built-in
[approval for tool calls](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/), and three times with the
approach on this page.

|                                     | Approval for each tool call       | Agent Sandboxes           |
| ----------------------------------- | --------------------------------- | ------------------------- |
| Approval requests for the person    | 37, one for each refund           | 1, with the complete plan |
| Model requests after the approval   | 2, with about 25,700 input tokens | None                      |
| Refunds correct                     | 3 of 3                            | 3 of 3                    |

The model was `gpt-5.5`. With approval for each tool call, the person approves 37 separate refunds, and the model must
run again afterwards to send the emails. With a sandbox, the steps after the approval are already written. They run
exactly as the person saw them in the plan.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
permission to run code in agent sandboxes. This page uses [Pydantic AI](https://pydantic.dev/docs/ai/overview/) for the
agent. The same `run_code` function works as a tool in any agent framework.

!!! warning "Logfire stores the paused script for 7 days"
    A paused script's state, including the values it computed from your data, is stored by Logfire so that any process
    can resume it. Logfire deletes it 7 days after it is saved. Resume each paused script before then. See
    [Persist, resume, and fork sessions](sessions.md).

## Define the functions, including the one that needs approval

`request_approval` never runs on its own. The script pauses when it calls it. The type stub tells the model to call it
once, with the whole plan, before any refund.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
async def list_orders_during(start: str, end: str) -> list[dict]:
    return []  # replace with a query on your order system


async def issue_refund(order_id: str, amount: float, idempotency_key: str) -> dict:
    return {'order_id': order_id, 'status': 'refunded'}  # replace with a call to your payment system


async def send_email(customer_id: str, subject: str, body: str) -> None:
    pass  # replace with a call to your email system


async def request_approval(summary: str, total: float) -> bool:
    raise RuntimeError('A person answers this call. It never runs on its own.')


TOOLS = {
    'list_orders_during': list_orders_during,
    'issue_refund': issue_refund,
    'send_email': send_email,
    'request_approval': request_approval,
}
NEEDS_APPROVAL = {'request_approval'}

STUBS = '''
async def list_orders_during(start: str, end: str) -> list[dict]:
    """Orders created between start and end (ISO timestamps), with order_id, customer_id, total, status, created_at.
    Orders that charged the customer but failed have status 'failed_capture'."""
async def issue_refund(order_id: str, amount: float, idempotency_key: str) -> dict:
    """Refund an order. Pass a unique idempotency_key for each order."""
async def send_email(customer_id: str, subject: str, body: str) -> None:
    """Email a customer."""
async def request_approval(summary: str, total: float) -> bool:
    """Ask a person to approve a plan. Call it once, with the whole plan, before any issue_refund call.
    The script waits here until the person answers, which can take hours. Returns True if approved."""
'''
```

## Give the agent a code tool that can pause

`run_code` runs the agent's script until it finishes, or until it calls a function in `NEEDS_APPROVAL`. Then it stores
the paused script and tells the model that the script is waiting.

```python title="code_tool.py" skip-run="true" skip-reason="external-connection"
import inspect
import json

import logfire
from pydantic_monty import AsyncFunctionSnapshot, MontyComplete, MontyError

from tools import NEEDS_APPROVAL, STUBS, TOOLS

logfire.configure()
pool = logfire.agent_sandboxes()


async def run_until_approval(snapshot):
    """Run the script until it finishes, or until it calls a function that needs approval."""
    while not isinstance(snapshot, MontyComplete):
        if isinstance(snapshot, AsyncFunctionSnapshot) and snapshot.function_name in NEEDS_APPROVAL:
            return snapshot
        snapshot = await snapshot.resume_auto()
    return snapshot


async def run_code(code: str) -> str:
    async with pool.checkout() as session:
        try:
            snapshot = await run_until_approval(await session.feed_start(code, external_lookup=TOOLS))
        except MontyError as e:
            return f'The script failed: {e}'
        if isinstance(snapshot, MontyComplete):
            return repr(snapshot.output)
        request = {'saved': snapshot.dump().hex(), 'args': snapshot.args, 'kwargs': snapshot.kwargs}
    with open('pending-approval.json', 'w') as f:  # use your database
        json.dump(request, f)
    return f'The script is paused until a person answers: {snapshot.args} {snapshot.kwargs}. Tell the user.'


async def answer(snapshot, outcome: dict):
    """Answer the call the script is waiting on, with a return value or an exception."""
    if inspect.iscoroutinefunction(TOOLS[snapshot.function_name]):
        # The script awaited an async function, so settle that pending call.
        pending = await snapshot.resume({'future': ...})
        return await pending.resume({snapshot.call_id: outcome})
    return await snapshot.resume(outcome)


RUN_CODE_DESCRIPTION = f"""Run a Python script and return the value of its last expression.
The script can `await` these functions, and run several at once with `asyncio.gather`:
{STUBS}"""
```

`snapshot.dump()` returns a short ID. Logfire stores the paused script under it. Store the ID with the approval
request, for example in the row your approval UI reads.

## Run the agent

```python title="agent.py" skip-run="true" skip-reason="external-connection"
import asyncio

from pydantic_ai import Agent, Tool

from code_tool import RUN_CODE_DESCRIPTION, pool, run_code

agent = Agent('openai:gpt-5.5', tools=[Tool(run_code, description=RUN_CODE_DESCRIPTION)])


async def main():
    async with pool:
        result = await agent.run(
            'Incident INC-1042 (2026-10-22 10:00 to 18:00 UTC) charged customers for orders that then failed. '
            'Refund every affected order in full, then email each affected customer once to apologize and '
            'confirm the refund amount.'
        )
    print(result.output)


asyncio.run(main())
```

Run `python agent.py`. The agent writes one script and runs it. The script finds the orders and stops at
`request_approval`, so the agent replies that the refunds are waiting for approval. `pending-approval.json` holds the
plan that the script passed to `request_approval`. Show that plan to the person who approves.

## Resume the script after the decision

Later, from any process, load the paused script and answer the call. To approve, pass `True`. To deny, pass an
exception: the script sees it raised by `request_approval`.

```python title="approve.py" skip-run="true" skip-reason="external-connection"
import asyncio
import json
import sys

from pydantic_monty import MontyComplete

from code_tool import answer, pool, run_until_approval
from tools import TOOLS


async def main(approved: bool):
    with open('pending-approval.json') as f:
        request = json.load(f)
    if approved:
        outcome = {'return_value': True}
    else:
        outcome = {'exception': PermissionError('A person declined the refunds.')}
    async with pool:
        async with pool.checkout() as session:
            snapshot = await session.load_snapshot(bytes.fromhex(request['saved']), external_lookup=TOOLS)
            result = await run_until_approval(await answer(snapshot, outcome))
    if isinstance(result, MontyComplete):
        print('Finished:', result.output)
    else:
        print('Paused again at', result.function_name)


asyncio.run(main(approved=sys.argv[1:] != ['deny']))
```

Run `python approve.py`. The script refunds the orders, emails the customers, and prints what it returned. The model is
not called. Run `python approve.py deny` instead to decline, and `request_approval` raises `PermissionError` inside the
script. If the script does not catch it, `approve.py` raises `MontyRuntimeError`.

If the script calls `request_approval` a second time, it pauses again, and you repeat this step.

## Why this works in a sandbox

Your application does not keep a process, a connection, or a container open while it waits. The paused script is a
stored value, so it can wait for days, survive a deploy of your application, and resume on a different machine.

Give the result to the model only if it needs to react, for example to tell the customer what happened. A denial can
also go back to the model, so that it can write a different plan.

## Verify it worked

Open **Agent Sandboxes → Overview** in Logfire. You should see two sessions: one that ends at the `request_approval`
call, and one that starts there and contains the `issue_refund` and `send_email` calls.

## Troubleshooting

- **A call runs twice after a resume.** If your application stops while it answers a call, the resumed script asks for
  the same call again. Make functions that change things safe to repeat. Here, `issue_refund` takes an idempotency key.
- **`TypeError: 'bool' object can't be awaited`** after a resume: the script awaited an async function, and you
  answered with `snapshot.resume({'return_value': ...})` directly. Use `answer()`, which settles the awaited call.
- **The script refunds before asking for approval**: the model ignored the stub. Make `issue_refund` itself check that
  approval was given, and raise an error if not. The script then fails before the refund, and the model sees why.
- **`load_snapshot()` raises `MontyRuntimeError`**: the paused script has expired. Logfire keeps it for 7 days.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): how Logfire stores sessions, and for how long.
- [Give an agent a whole API](typed-api.md): check the agent's script against your types before it can reach a
  sensitive call.
- [Add a code tool to any agent](any-framework.md): use `run_code` with another agent framework.
