---
title: "Give an agent a whole API without a tool for every endpoint"
description: "Expose a Python module to agent code with type stubs, and reject code that calls it wrongly before any of it runs."
---

# Give an agent a whole API without a tool for every endpoint

An internal API with dozens of operations becomes dozens of tool definitions. The model reads every definition on every turn, and the
list grows each time you add an operation. Each call is still one model turn.

With Agent Sandboxes, you expose the API as one importable Python module. The model reads a short **type stub** (a
`.pyi` file that lists function signatures and data shapes, without code) and writes a script that imports the module
and calls it. Before the script runs, the sandbox checks it against the stub. A script that calls a function with the
wrong arguments, or reads a field that does not exist, never runs. The model gets the error and fixes the script.

That check matters most for APIs that change things. A script that passes a status that does not exist, or reads a
field that does not exist, fails the check before its first call. The check cannot tell whether a valid value is the
right one, for example whether an invoice ID belongs to the right customer. Your functions must still check that.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
permission to run code in agent sandboxes.

## Describe the API with a type stub

Write the signatures and data shapes the agent may use. The stub is also what you put in the agent's instructions, so
the model knows what it can call. Keep it to the operations the agent needs.

```python title="billing.py" skip-run="true" skip-reason="external-connection"
from pydantic_monty import ExternalModule

BILLING_STUB = """
from typing import Literal, TypedDict

class Invoice(TypedDict):
    id: str
    customer_id: str
    amount_cents: int
    status: Literal['paid', 'open', 'void']

def list_invoices(customer_id: str, status: Literal['paid', 'open', 'void'] | None = None) -> list[Invoice]: ...
def void_invoice(invoice_id: str) -> Invoice: ...
"""


def list_invoices(customer_id: str, status: str | None = None) -> list[dict]:
    invoices = [  # replace with a call to your billing service
        {'id': 'in_1', 'customer_id': customer_id, 'amount_cents': 5000, 'status': 'open'},
        {'id': 'in_2', 'customer_id': customer_id, 'amount_cents': 900, 'status': 'paid'},
    ]
    return [i for i in invoices if status is None or i['status'] == status]


def void_invoice(invoice_id: str) -> dict:
    raise NotImplementedError('replace with a call to your billing service')


billing = ExternalModule({'list_invoices': list_invoices, 'void_invoice': void_invoice}, stubs=BILLING_STUB)
```

Each function in the module runs in your application when sandbox code calls it, like any other host function.

## Check the agent's code before it runs

Pass the module in `external_modules` and turn on `type_check` when you check out a session. Here the first script has
two mistakes a model can make: a status that does not exist, and a field name that does not exist.

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire
from pydantic_monty import MontyTypingError

from billing import billing

logfire.configure()

FIRST_TRY = """
from billing import list_invoices

unpaid = list_invoices('cus_1', status='unpaid')
sum(i['amount'] for i in unpaid)
"""

SECOND_TRY = """
from billing import list_invoices

unpaid = list_invoices('cus_1', status='open')
sum(i['amount_cents'] for i in unpaid) / 100
"""


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout(type_check=True, external_modules={'billing': billing}) as session:
            try:
                await session.feed_run(FIRST_TRY)
            except MontyTypingError as e:
                print(e.display())  # send this back to the model
            print(await session.feed_run(SECOND_TRY))


asyncio.run(main())
```

Run `python main.py`. The first script does not run. It prints the errors that you send back to the model:

```
error[invalid-argument-type]: Argument to function `list_invoices` is incorrect
 --> main.py:4:33
  |
2 | from billing import list_invoices
3 |
4 | unpaid = list_invoices('cus_1', status='unpaid')
  |                                 ^^^^^^^^^^^^^^^ Expected `Literal["paid", "open", "void"] | None`, found `Literal["unpaid"]`
5 | sum(i['amount'] for i in unpaid)
  |
info: Function defined here
  --> billing.pyi:10:5
   |
 8 |     status: Literal['paid', 'open', 'void']
 9 |
10 | def list_invoices(customer_id: str, status: Literal['paid', 'open', 'void'] | None = None) -> list[Invoice]: ...
   |     ^^^^^^^^^^^^^                   ----------------------------------------------------- Parameter declared here
11 | def void_invoice(invoice_id: str) -> Invoice: ...
   |

error[invalid-key]: Unknown key "amount" for TypedDict `Invoice`
 --> main.py:5:7
  |
4 | unpaid = list_invoices('cus_1', status='unpaid')
5 | sum(i['amount'] for i in unpaid)
  |     - ^^^^^^^^ Unknown key "amount"
  |     |
  |     TypedDict `Invoice`
```

The corrected script runs and prints `50.0`.

The errors name the line, the argument, and the allowed values, so a model can fix the script in one more turn. Without
the check, the first script would have called `list_invoices` with a status your service does not understand, and
failed (or worse, succeeded) at run time.

## Write a good stub

- **Use `Literal` for fixed values** such as statuses and regions. The check then rejects any other value.
- **Use `TypedDict` for the shape of results**, so the check catches misspelled field names.
- **Add a one-line comment above a function** when its name does not say what it does. The model reads the stub.
- **Leave out operations the agent must not use.** A function that is not in the module cannot be called.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see a `run code` span for the corrected script, with a child
span for the `billing.list_invoices` call. The script that failed the check has no tool call spans, because none of its
code ran.

## Troubleshooting

- **`ImportError` for your module**: pass it to `checkout()` in `external_modules`, under the name the script imports.
- **The check rejects code that is correct**: the stub is wrong or incomplete. Check that every type the stub uses is
  imported in the stub (for example `from typing import Literal`).
- **The check rejects a standard library feature**: sandboxes support a subset of Python, and the check knows which
  parts. See [What sandbox code can do](limits.md).

## Next steps

- [Pause agent code for human approval](approval.md): let a script call `void_invoice`, but only after a person agrees.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): Pydantic AI writes the stub from your tools for you.
- [Answer questions that need dozens of tool calls](many-tool-calls.md): call the API in parallel from one script.
