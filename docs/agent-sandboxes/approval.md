---
title: "Pause agent code for human approval, and resume it later"
description: "Stop an agent's script at a sensitive call, save it, ask a person, and continue the same script hours later from any process."
---

# Pause agent code for human approval, and resume it later

A support agent decides that a customer should get a refund for two damaged orders. The refund needs a person's
approval, and the person may answer in five minutes or tomorrow. After the approval, the agent must still issue the
refund, email the customer, and report the total.

With Agent Sandboxes, the agent writes all of that as one script. When the script reaches `issue_refund(...)`, your
application stops it and saves it. Logfire stores the paused script and gives you a short ID. When the person approves, any process loads it
and the script continues from that exact line, with every variable it had. The model is not called again, so the steps
after the approval run exactly as the agent wrote them.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
permission to run code in agent sandboxes.

!!! warning "The saved state is stored by Logfire for 7 days"
    A paused script's state, including the values it computed from your data, is stored by Logfire so that any process
    can resume it. Logfire deletes it after 7 days. Resume or discard each paused script before then. See
    [Persist, resume, and fork sessions](sessions.md).

## Run the script until it reaches a sensitive call

`feed_run()` runs a script to the end. To stop at a call, use `feed_start()` instead. It returns a **snapshot** (the
paused script) at each call to one of your functions. `resume_auto()` runs that call and continues to the next one.
Stop when the snapshot is a call that needs approval, and save it with `dump()`.

```python title="refunds.py" skip-run="true" skip-reason="external-connection"
from pydantic_monty import AsyncFunctionSnapshot, MontyComplete

NEEDS_APPROVAL = {'issue_refund'}


def get_orders(customer_id: str) -> list[dict]:
    return [  # replace with a call to your order system
        {'id': 'o1', 'total': 120.0, 'status': 'damaged'},
        {'id': 'o2', 'total': 40.0, 'status': 'delivered'},
        {'id': 'o3', 'total': 75.5, 'status': 'damaged'},
    ]


def issue_refund(customer_id: str, amount: float, reason: str) -> bool:
    print(f'Refunding {amount} to {customer_id}: {reason}')  # replace with a call to your payment system
    return True


def send_email(customer_id: str, body: str) -> None:
    print(f'Email to {customer_id}: {body}')  # replace with a call to your email system


TOOLS = {'get_orders': get_orders, 'issue_refund': issue_refund, 'send_email': send_email}


async def run_until_approval(snapshot):
    """Run the script until it finishes or reaches a call that needs approval."""
    while not isinstance(snapshot, MontyComplete):
        if isinstance(snapshot, AsyncFunctionSnapshot) and snapshot.function_name in NEEDS_APPROVAL:
            return snapshot
        snapshot = await snapshot.resume_auto()
    return snapshot
```

The agent wrote this script. The model does not know that `issue_refund` needs approval, and does not need to:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

from refunds import TOOLS, run_until_approval

logfire.configure()

AGENT_CODE = """
orders = get_orders('cus_123')
damaged = [o for o in orders if o['status'] == 'damaged']
total = sum(o['total'] for o in damaged)
approved = issue_refund('cus_123', total, reason=f'{len(damaged)} damaged orders')
if approved:
    send_email('cus_123', f'We refunded ${total:.2f} for your damaged orders.')
{'refunded': total if approved else 0}
"""


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            snapshot = await run_until_approval(await session.feed_start(AGENT_CODE, external_lookup=TOOLS))
            print(snapshot.function_name, snapshot.args, snapshot.kwargs)
            saved = snapshot.dump()  # a short ID: store it with the approval request
    with open('pending-refund.bin', 'wb') as f:
        f.write(saved)


asyncio.run(main())
```

Run `python main.py`. It prints the call that is waiting for approval:

```
issue_refund ('cus_123', 195.5) {'reason': '2 damaged orders'}
```

`get_orders` ran. `issue_refund` and `send_email` did not. Show the person the function name and arguments: they are
exactly what will run if they approve. In a real application, store `saved` in your database next to the approval
request, not in a file.

## Resume the script after the decision

Later, in any process, load the saved script into a new session and answer the waiting call. To approve, run the real
function and pass its result. To deny, pass an exception: the script sees it raised by `issue_refund`.

```python title="resume.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire
from pydantic_monty import MontyRuntimeError

from refunds import TOOLS, issue_refund, run_until_approval

logfire.configure()


async def main(approved: bool):
    with open('pending-refund.bin', 'rb') as f:
        saved = f.read()
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            snapshot = await session.load_snapshot(saved, external_lookup=TOOLS)
            if approved:
                answer = {'return_value': issue_refund(*snapshot.args, **snapshot.kwargs)}
            else:
                answer = {'exception': PermissionError('A person declined this refund.')}
            try:
                result = await run_until_approval(await snapshot.resume(answer))
            except MontyRuntimeError as e:
                print(e)  # the script did not catch the denial: send this back to the model
                return
    print(result.output)


asyncio.run(main(approved=True))
```

Run `python resume.py`. The script continues from the refund, sends the email, and returns its result:

```
Refunding 195.5 to cus_123: 2 damaged orders
Email to cus_123: We refunded $195.50 for your damaged orders.
{'refunded': 195.5}
```

The model wrote the follow-up steps before the pause, and they ran unchanged after it.

Call `main(approved=False)` instead, and `issue_refund` raises the `PermissionError` inside the script. This script does
not catch it, so the script stops and `resume.py` prints:

```
PermissionError: A person declined this refund.
```

`send_email` never runs. If the script makes a second
call that needs approval, `run_until_approval` stops there too, and you repeat the same steps.

## Why this works in a sandbox

Your application does not keep a process, a connection, or a container open while it waits. The paused script is a
short ID, so it can wait for days, survive a deploy of your application, and resume on a different machine.

Give the result back to the model only if it needs to react, for example to tell the customer. A denial can also go
back to the model, so that it can write a different plan.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see two traces: one for `main.py` that ends at the
`issue_refund` call, and one for `resume.py` that starts there and includes the `send_email` call.

## Troubleshooting

- **A call runs twice after a resume.** If your application stops while it is answering a call, a resumed script asks
  for the same call again. Make functions that change things safe to repeat, for example by passing an idempotency key
  to your payment system.
- **Resuming fails with `TypeError: An asyncio.Future, a coroutine or an awaitable is required`**: the script called the
  function that needs approval inside `asyncio.gather(...)`. Tell the agent, in its instructions, to call functions that
  need approval on their own line, not inside `asyncio.gather`.
- **`load_snapshot()` raises `MontyRuntimeError`**: the saved state has expired. Logfire keeps it for 7 days. Start a
  new run.

## Next steps

- [Persist, resume, and fork sessions](sessions.md): how saved state is stored, and how long it is kept.
- [Give an agent a whole API](typed-api.md): check the agent's script against your types before it can reach a
  sensitive call.
- [Add a code tool to any agent](any-framework.md): connect this flow to your agent's tool calls.
