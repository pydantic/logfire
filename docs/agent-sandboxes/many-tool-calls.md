---
title: "Answer questions that need dozens of tool calls in one step"
description: "Let your agent write one short script that calls your tools in loops and in parallel, and return only the answer to the model."
---

# Answer questions that need dozens of tool calls

Some questions need many tool calls: "Which enterprise customers missed their availability target this week, and do
they have an open support ticket?" With one tool call per model turn, your agent fetches 40 customers, then makes 40
availability calls, then a few ticket lookups. Each round trip waits for the model, and every result fills its
**context window** (the text the model reads on each turn, which you pay for in **tokens**, the units models read and
bill by).

With Agent Sandboxes, the model writes one short Python script instead. The script calls your tools as functions, in
parallel, filters the results, and returns only the rows that answer the question. Your tools run in your application.
The script runs in a [sandbox](index.md).

## What changes

|                                  | One tool call per turn                    | One script in a sandbox                         |
| -------------------------------- | ----------------------------------------- | ----------------------------------------------- |
| Model turns                      | One or more for each batch of calls       | One                                             |
| What the model reads             | Every customer, every result              | The two rows that answer the question           |
| Who does the filtering and math  | The model, by reading                     | Python, exactly                                 |
| Where your tools run             | Your application                          | Your application                                |

The last row matters: the sandbox never holds your credentials or connects to your systems. When the script calls
`get_availability(...)`, the sandbox pauses, your application runs the real function, and the sandbox continues with the
result.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
the **Execute agent sandboxes** permission.

## Write your tools as normal Python functions

Use the same functions you would give an agent as tools. Here they return sample data, so you can run the example.
Replace their bodies with calls to your own services.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import asyncio

CUSTOMERS = [
    {'id': f'c{i:03}', 'name': f'Customer {i}', 'plan': 'enterprise' if i % 3 == 0 else 'team', 'target': 0.999}
    for i in range(120)
]


async def list_customers(plan: str) -> list[dict]:
    """List customers on a plan."""
    return [c for c in CUSTOMERS if c['plan'] == plan]


async def get_availability(customer_id: str, days: int) -> float:
    """Return the fraction of successful requests for a customer over the last `days` days."""
    await asyncio.sleep(0.05)  # stands in for a real API call
    return 0.997 if customer_id in ('c009', 'c042', 'c087', 'c111') else 0.9995


async def list_open_tickets(customer_id: str) -> list[dict]:
    """List a customer's open support tickets."""
    await asyncio.sleep(0.05)
    return [{'id': 'T-1', 'title': 'API timeouts'}] if customer_id in ('c042', 'c087') else []
```

## See the script your agent writes

Asked the question above, a model writes a script like this one. It uses `asyncio.gather` to make the availability
calls at the same time, then looks up tickets only for the customers that missed their target:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

import logfire

from tools import get_availability, list_customers, list_open_tickets

logfire.configure()

AGENT_CODE = """
import asyncio

customers = await list_customers(plan='enterprise')
availability = await asyncio.gather(*[get_availability(c['id'], days=7) for c in customers])
missed = [(c, a) for c, a in zip(customers, availability) if a < c['target']]
tickets = await asyncio.gather(*[list_open_tickets(c['id']) for c, _ in missed])
[
    {'customer': c['name'], 'availability': a, 'open_tickets': [t['title'] for t in ts]}
    for (c, a), ts in zip(missed, tickets)
    if ts
]
"""


async def main():
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            result = await session.feed_run(
                AGENT_CODE,
                external_lookup={
                    'list_customers': list_customers,
                    'get_availability': get_availability,
                    'list_open_tickets': list_open_tickets,
                },
            )
    print(result)


asyncio.run(main())
```

Run `python main.py`. It prints the only two rows the model needs:

```
[{'customer': 'Customer 42', 'availability': 0.997, 'open_tickets': ['API timeouts']}, {'customer': 'Customer 87', 'availability': 0.997, 'open_tickets': ['API timeouts']}]
```

The script made 45 tool calls. The model wrote about 12 lines and read two rows.

Here you run the script yourself, so you can see what happens. In your application, the agent writes the script and
your code runs it. See [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md) or [Add a code tool to any
agent](any-framework.md) to connect the two.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see one `run code` span (one unit of work: a single
operation, with a name, a start, and a duration) with a child span for each of the 45 tool calls. The availability
calls overlap in time, because the script ran them in parallel.

!!! warning "Tool arguments and results are recorded in your project"
    With tracing on (the default), Logfire records the script, each tool call's arguments and result, and the final
    result in your project, after its standard [scrubbing](../how-to-guides/scrubbing.md). The script and the tool
    results also pass through Logfire's servers to run.

## When to use this, and when not

Use a script when the agent needs many calls whose results it does not need to read one by one: lookups for each item
in a list, the same check across many services, or several sources joined into one answer.

Keep plain tool calls when each step depends on the model's judgment about the last result, for example reading a
document and deciding what to search next. A script cannot replace that reasoning.

## Troubleshooting

- **`NameError: name 'list_customers' is not defined`**: the script called a function that is not in `external_lookup`.
  Pass every function the agent may call.
- **`MontyCrashedError` with `timed_out=True`**: the slowest tool call took longer than `request_timeout` (10 seconds
  by default). Pass a larger `request_timeout` to `logfire.agent_sandboxes()`.
- **The script fails on an unsupported feature**, such as a class that inherits from another class: sandboxes run a
  subset of Python. See [What sandbox code can do](limits.md).

## Next steps

- [Work with large results without filling the context window](large-results.md): reduce thousands of rows to a summary.
- [Give an agent a whole API](typed-api.md): check the agent's code against your types before it runs.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): let a Pydantic AI agent write and run these scripts.
