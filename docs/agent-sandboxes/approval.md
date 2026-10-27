---
title: "Pause agent code for human approval, and resume it later"
description: "Let an agent plan a batch of sensitive actions in one script, ask a person once, and finish the plan hours later from any process without calling the model again."
---

# Pause agent code for human approval, and resume it later

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

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
| Model requests after the approval   | 2, with about 26,400 input tokens | None                      |
| Refunds correct                     | 3 of 3                            | 3 of 3                    |

The model was `gpt-6.1-sol`. With approval for each tool call, the person approves 37 separate refunds, and the model must
run again afterwards to send the emails. With a sandbox, the steps after the approval are already written. The host functions must check that each action matches the approved plan. A model instruction alone cannot enforce approval.

These are three-run results on a fixed scenario, not a prediction of production accuracy or token use.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
permission to run code in agent sandboxes. This page uses [Pydantic AI](https://pydantic.dev/docs/ai/overview/) for the
agent. Install it with `pip install pydantic-ai`. Set `OPENAI_API_KEY` to a key from the
[OpenAI API keys page](https://platform.openai.com/api-keys). The same `run_code` function works in other agent frameworks.

!!! warning "Logfire stores the paused script for 7 days"
    A paused script's state, including the values it computed from your data, is stored by Logfire so that any process
    can resume it. Logfire deletes it 7 days after it is saved. Resume each paused script before then. See
    [Persist, resume, and fork sessions](sessions.md).

## Define the functions, including the one that needs approval

`request_approval` never runs on its own. Your application pauses the script when it calls that function.
The type stub asks the model for one structured plan with the refunds and emails.
The host functions reject any action that is not in the approved plan.

These functions use two synthetic orders and simulate the actions. Replace them with your own services.
Keep the approval checks and pass each idempotency key to the service. An idempotency key lets the service recognize
and return the result of an action it already completed, instead of doing it again.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
async def list_orders_during(start: str, end: str) -> list[dict]:
    return [
        {'order_id': 'o1', 'customer_id': 'c1', 'total_cents': 1200, 'status': 'failed_capture'},
        {'order_id': 'o2', 'customer_id': 'c2', 'total_cents': 1700, 'status': 'failed_capture'},
    ]


async def request_approval(plan: dict) -> bool:
    raise RuntimeError('A person answers this call. It never runs on its own.')


def make_tools(approved_plan: dict | None = None) -> dict:
    allowed = approved_plan or {}

    async def issue_refund(order_id: str, amount_cents: int, idempotency_key: str) -> dict:
        action = {'order_id': order_id, 'amount_cents': amount_cents, 'idempotency_key': idempotency_key}
        if action not in allowed.get('refunds', []):
            raise PermissionError('This refund is not in the approved plan.')
        return {**action, 'status': 'refunded'}  # replace with an idempotent payment-system call

    async def send_email(customer_id: str, subject: str, body: str, idempotency_key: str) -> None:
        action = {'customer_id': customer_id, 'subject': subject, 'body': body, 'idempotency_key': idempotency_key}
        if action not in allowed.get('emails', []):
            raise PermissionError('This email is not in the approved plan.')
        # Send through an email service that deduplicates the idempotency key.

    return {
        'list_orders_during': list_orders_during,
        'issue_refund': issue_refund,
        'send_email': send_email,
        'request_approval': request_approval,
    }


TOOLS = make_tools()
NEEDS_APPROVAL = {'request_approval'}

STUBS = '''
async def list_orders_during(start: str, end: str) -> list[dict]:
    """Return orders in the incident, with order_id, customer_id, total_cents, and status.
    Orders that charged the customer but failed have status 'failed_capture'."""
async def issue_refund(order_id: str, amount_cents: int, idempotency_key: str) -> dict:
    """Refund an approved order. Use the exact amount and key from the approved plan."""
async def send_email(customer_id: str, subject: str, body: str, idempotency_key: str) -> None:
    """Send an approved email. Use the exact fields and key from the approved plan."""
async def request_approval(plan: dict) -> bool:
    """Ask a person to approve the complete plan before any refund or email.
    plan['refunds'] contains order_id, amount_cents, and idempotency_key for each refund.
    plan['emails'] contains customer_id, subject, body, and idempotency_key for each email.
    Use a stable, unique key for each action. Return True only after a person approves.
    The script waits here for the decision. Continue with the approved actions only."""
'''
```

!!! warning "This example handles one approval at a time"
    The JSON files below demonstrate one workflow on one machine. A lock serializes tool calls within this process. Do not share them across users or
    concurrent jobs. In production, store each request under its own ID. Authenticate the approver and claim the
    decision atomically before running it. Keep the approved plan separate from model-editable state.

## Give the agent a code tool that can pause

`run_code` runs the agent's script until it finishes, or until it calls a function in `NEEDS_APPROVAL`. Then it stores
the paused script and tells the model that the script is waiting.

```python title="code_tool.py" skip-run="true" skip-reason="external-connection"
import asyncio
import inspect
import json
from pathlib import Path

from pydantic_monty import (
    AsyncFunctionSnapshot,
    MontyComplete,
    MontyError,
    MontyTypingError,
)
from tools import NEEDS_APPROVAL, STUBS, TOOLS

import logfire

logfire.configure()
pool = logfire.agent_sandboxes()
PENDING = Path('pending-approval.json')
IN_PROGRESS = Path('in-progress-approval.json')
RUN_LOCK = asyncio.Lock()


def save_pending(snapshot):
    plan = snapshot.args[0] if snapshot.args else snapshot.kwargs['plan']
    request = {'saved': snapshot.dump().hex(), 'plan': plan}
    PENDING.write_text(json.dumps(request), encoding='utf-8')


async def run_until_approval(snapshot):
    """Run the script until it finishes, or until it calls a function that needs approval."""
    while not isinstance(snapshot, MontyComplete):
        if isinstance(snapshot, AsyncFunctionSnapshot) and snapshot.function_name in NEEDS_APPROVAL:
            return snapshot
        snapshot = await snapshot.resume_auto()
    return snapshot


async def run_code(code: str) -> str:
    async with RUN_LOCK:
        if PENDING.exists() or IN_PROGRESS.exists():
            return 'An approval is already pending. Wait for the person to decide.'
        async with pool.checkout(type_check=True, type_check_stubs=STUBS) as session:
            try:
                snapshot = await run_until_approval(await session.feed_start(code, external_lookup=TOOLS))
            except MontyTypingError as e:
                return f'The script did not run, because it has type errors:\n{e.display()}'
            except MontyError as e:
                return f'The script failed: {e}'
            if isinstance(snapshot, MontyComplete):
                return repr(snapshot.output)
            save_pending(snapshot)
        return 'The script is paused until a person reviews the saved plan. Tell the user.'


async def answer(snapshot, outcome: dict):
    """Answer the call the script is waiting on, with a return value or an exception."""
    if inspect.iscoroutinefunction(TOOLS[snapshot.function_name]):
        # The script awaited an async function, so settle that pending call.
        pending = await snapshot.resume({'future': ...})
        return await pending.resume({snapshot.call_id: outcome})
    return await snapshot.resume(outcome)


RUN_CODE_DESCRIPTION = f"""Run a Python script and return the value of its last expression.
The script can `await` these functions, and run several at once with `asyncio.gather`:
{STUBS}
In this sandbox, `asyncio.gather` takes no keyword arguments, so do not pass `return_exceptions`.
If the task needs approval, write the whole task as one script. After `request_approval` returns True, the same
script must continue and do the rest of the task. You will not be called again after the approval."""
```

`snapshot.dump()` returns a short ID. Logfire stores the paused script under it. Store the ID with the approval
request, for example in the row your approval UI reads.

Two details matter:

- **The last sentence of `RUN_CODE_DESCRIPTION`.** Without it, models often stop the script at the approval and plan
  to do the rest in a later turn. Nothing calls the model after the approval, so the rest never runs.
- **`type_check=True`.** The sandbox checks the whole script before any of it runs. A mistake after the approval, such
  as a missing `import asyncio`, fails now, while the model can still fix it, and not after a person has approved.

## Run the agent

```python title="agent.py" skip-run="true" skip-reason="external-connection"
import asyncio

from code_tool import RUN_CODE_DESCRIPTION, pool, run_code
from pydantic_ai import Agent, Tool

agent = Agent('openai:gpt-6.1-sol', tools=[Tool(run_code, description=RUN_CODE_DESCRIPTION)])


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
plan that the script passed to `request_approval`. Show its exact refund amounts and email contents to the person
who approves. Do not substitute the model's summary for that plan.

## Resume the script after the decision

Later, from any process, load the paused script and answer the call. To approve, pass `True`. To deny, pass an
exception: the script sees it raised by `request_approval`.

```python title="approve.py" skip-run="true" skip-reason="external-connection"
import argparse
import asyncio
import json

from code_tool import (
    IN_PROGRESS,
    PENDING,
    answer,
    pool,
    run_until_approval,
    save_pending,
)
from pydantic_monty import MontyComplete
from tools import make_tools


async def main(approved: bool):
    if IN_PROGRESS.exists():
        raise RuntimeError('A previous attempt is unfinished. Review its effects before you retry.')
    PENDING.rename(IN_PROGRESS)
    request = json.loads(IN_PROGRESS.read_text(encoding='utf-8'))
    tools = make_tools(request['plan'] if approved else None)
    if approved:
        outcome = {'return_value': True}
    else:
        outcome = {'exception': PermissionError('A person declined the plan.')}
    async with pool:
        async with pool.checkout() as session:
            snapshot = await session.load_snapshot(bytes.fromhex(request['saved']), external_lookup=tools)
            result = await run_until_approval(await answer(snapshot, outcome))
            if not isinstance(result, MontyComplete):
                save_pending(result)
    IN_PROGRESS.unlink()
    if isinstance(result, MontyComplete):
        print('Finished:', result.output)
    else:
        print('Paused again. Review the new plan in pending-approval.json.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('decision', choices=['approve', 'deny'])
    args = parser.parse_args()
    asyncio.run(main(approved=args.decision == 'approve'))
```

Review `pending-approval.json`, then run `python approve.py approve`. The script refunds the orders, emails the customers, and prints what it returned. The model is
not called. Run `python approve.py deny` instead to decline, and `request_approval` raises `PermissionError` inside the
script. If the script does not catch it, `approve.py` raises `MontyRuntimeError`.

If the script asks for approval again, `save_pending()` writes the new checkpoint and its plan. Review that new plan
before you repeat the decision. A completed run removes the request. Running the command again cannot silently
reload the original checkpoint.

If a resume fails, the in-progress file remains. Review which actions completed before you recover it. A checkpoint
can replay host calls when you load it again. Idempotency checks in the host services must prevent duplicate actions.

## Why this works in a sandbox

Your application does not keep a process, a connection, or a container open while it waits. The paused script is a
stored value, so it can wait for days, survive a deploy of your application, and resume on a different machine.

Give the result to the model only if it needs to react, for example to tell the customer what happened. A denial can
also go back to the model, so that it can write a different plan.

## Verify it worked

Open **AI Optimization → Agent Sandboxes → Overview** in Logfire. You should see two sessions: one that ends at the `request_approval`
call, and one that starts there and contains the `issue_refund` and `send_email` calls.

## Troubleshooting

- **A call runs twice after a resume.** If your application stops while it answers a call, the resumed script asks for
  the same call again. Make functions that change things safe to repeat. Here, `issue_refund` takes an idempotency key.
- **`TypeError: 'bool' object can't be awaited`** after a resume: the script awaited an async function, and you
  answered with `snapshot.resume({'return_value': ...})` directly. Use `answer()`, which settles the awaited call.
- **The script stops after the approval and does nothing more**: the model planned to finish in a later turn. Keep
  the last sentence of `RUN_CODE_DESCRIPTION`, which tells the model that it is not called again.
- **The script fails after the approval, and `approve.py` then refuses to run**: some approved actions may already have
  run. `in-progress-approval.json` holds the plan. Check which refunds and emails happened before you retry. One cause
  is `NotImplementedError: gather() does not yet support keyword arguments`, which the type check does not catch.
  `RUN_CODE_DESCRIPTION` tells the model to avoid it.
- **A refund or email fails with `PermissionError`**: it does not exactly match the approved plan. The host rejects
  it before the action. Review a new plan instead of bypassing the check.
- **`load_snapshot()` raises `MontyRuntimeError`**: the paused script has expired. Logfire keeps it for 7 days.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): how Logfire stores sessions, and for how long.
- [Give an agent a whole API](typed-api.md): check the agent's script against your types before it can reach a
  sensitive call.
- [Add a code tool to any agent](any-framework.md): use `run_code` with another agent framework.
