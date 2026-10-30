---
title: "Answer questions that need dozens of tool calls"
description: "Let your agent write one short script that calls your tools and does the math in Python, so the model reads only the answer."
---

# Answer questions that need dozens of tool calls

!!! info "Experimental"
    Agent Sandboxes is available to selected Logfire organizations. See [access and availability](index.md).

"Which enterprise customers missed their availability target this week, and do they have an open support ticket?" To
answer, an agent fetches 40 customers, then a week of request counts for each one, then tickets. With plain tool calls,
every row of every result goes into the model's **context window** (the text the model reads on each turn, which you
pay for in **tokens**, the units models read and bill by). Then the model must add up thousands of numbers by reading
them.

With Agent Sandboxes, the model writes a short Python script instead.
The script calls your tools as functions and computes the answer in Python.
Your tools run in your application. The script runs in a [sandbox](index.md). The model reads only what the script returns.

## What this changes

We asked this question of a Pydantic AI agent three times with plain tool calls, and three times with Agent Sandboxes
through [Code Mode](pydantic-ai.md) (a Pydantic AI feature that turns an agent's tools into functions its scripts can
call). Each customer's request counts were 42 rows: 7 days for 6 API
endpoints, which is the shape a real metrics API returns.

|                             | Plain tool calls          | Agent Sandboxes            |
| --------------------------- | ------------------------- | -------------------------- |
| Correct answers             | 1 of 3                    | 3 of 3                     |
| Input tokens (median)       | 111,162                   | 4,680                      |

These are three-run results on fixed sample data, not a prediction of production accuracy, latency, or cost.
Measure your own tools and questions before choosing an approach.

The model was `gpt-6.1-sol`. With plain tool calls, it named the wrong customers in two of three runs. It was not
adding up 1,680 rows reliably by reading them. In the sandbox, Python did the adding.

A smaller model, `gpt-6-luna`, was correct in 0 of 3 runs with plain tool calls and in 3 of 3 runs with Agent
Sandboxes. But its scripts often returned every row to the model instead of a summary, so it did not save tokens. The
savings depend on the model writing a script that reduces the data. Say so in your agent's instructions if your model
does not do it unprompted.

The gain is largest when tools return more data than the model needs to read. But even with a tool that returns one
availability number for each customer, `gpt-6-luna` matched numbers to the wrong customers in 3 of 3 runs with plain
tool calls, and was correct in 3 of 3 runs with Agent Sandboxes. `gpt-6.1-sol` was correct every time with both.

## Before you start

Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key with
the permission to run code in agent sandboxes.

## Write your tools as normal Python functions

Use the same functions you would give an agent as tools. Here they return sample data, so you can run the example.
Replace their bodies with calls to your own services.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import asyncio
import random
from datetime import datetime, timedelta, timezone

CUSTOMERS = [
    {'id': f'c{i:03}', 'name': f'Customer {i}', 'plan': 'enterprise' if i % 3 == 0 else 'team', 'target': 0.999}
    for i in range(120)
]
ENDPOINTS = ['/v1/orders', '/v1/search', '/v1/auth', '/v1/payments', '/v1/users', '/v1/export']


async def list_customers(plan: str) -> list[dict]:
    """List customers on a plan ('enterprise' or 'team'). Each has `id`, `name`, `plan`, and availability `target`."""
    return [c for c in CUSTOMERS if c['plan'] == plan]


async def get_request_stats(customer_id: str, days: int) -> list[dict]:
    """Return request counts for a customer for each day and endpoint over the last `days` days.

    Each row has `date`, `endpoint`, `requests`, `errors` (5xx responses), and `p95_ms`.
    """
    await asyncio.sleep(0.05)  # stands in for a real API call
    rnd = random.Random(customer_id)
    rows = []
    for day in range(days):
        date = (datetime(2026, 10, 23, tzinfo=timezone.utc) - timedelta(days=day)).date().isoformat()
        for endpoint in ENDPOINTS:
            requests = rnd.randint(2000, 9000)
            errors = rnd.randint(0, 3)
            if customer_id in ('c009', 'c042', 'c087', 'c111') and endpoint == '/v1/search':
                errors = int(requests * 0.02)
            rows.append(
                {
                    'date': date,
                    'endpoint': endpoint,
                    'requests': requests,
                    'errors': errors,
                    'p95_ms': rnd.randint(80, 400),
                }
            )
    return rows


async def list_open_tickets(customer_id: str) -> list[dict]:
    """List a customer's open support tickets."""
    await asyncio.sleep(0.05)
    return [{'id': 'T-1', 'title': 'API timeouts'}] if customer_id in ('c042', 'c087') else []
```

## See the code the agent writes

In one comparison run, the agent called the sandbox three times. Each script continued from the previous script's
variables. The following example adapts that workflow to return compact results:

1. Load the customers and return their count.
2. Fetch each customer's request counts and return the names below their availability target.
3. Look up tickets for those customers and return the names with open tickets.

The scripts request one tool call at a time.
An agent can also use `asyncio.gather` to request several calls together.
The hosted service can serialize those calls. Do not assume that they finish in parallel or reduce latency.

You can run these scripts without a model. Save the code below as `main.py` beside `tools.py`:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

from tools import get_request_stats, list_customers, list_open_tickets

import logfire

logfire.configure()

SCRIPTS = [
    """
customers = await list_customers(plan='enterprise')
len(customers)
""",
    """
stats_lists = [await get_request_stats(customer_id=c['id'], days=7) for c in customers]
missed = []
for c, rows in zip(customers, stats_lists):
    total = sum(r['requests'] for r in rows)
    errors = sum(r['errors'] for r in rows)
    availability = (total - errors) / total if total else 1.0
    if availability < c['target']:
        missed.append(c)
[c['name'] for c in missed]
""",
    """
tickets_lists = [await list_open_tickets(customer_id=c['id']) for c in missed]
[c['name'] for c, tickets in zip(missed, tickets_lists) if tickets]
""",
]


async def main():
    tools = {
        'list_customers': list_customers,
        'get_request_stats': get_request_stats,
        'list_open_tickets': list_open_tickets,
    }
    async with logfire.agent_sandboxes() as pool:
        async with pool.checkout() as session:
            for script in SCRIPTS:
                print(await session.feed_run(script, external_lookup=tools))


asyncio.run(main())
```

Run `python main.py`. It prints what the model reads after each script:

```
40
['Customer 9', 'Customer 42', 'Customer 87', 'Customer 111']
['Customer 42', 'Customer 87']
```

The scripts made 45 tool calls and handled 1,680 rows of request counts. The model read three short lines.

In your application, the agent writes the scripts and your code runs them. See [Use Agent Sandboxes with Pydantic
AI](pydantic-ai.md) or [Add a code tool to any agent](any-framework.md) to connect the two.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see a `run code` span (one unit of work: a single operation,
with a name, a start, and a duration) for each script. The second one has a child span for each of the 40
`get_request_stats` calls.

!!! warning "Tool arguments and results are recorded in your project"
    With tracing on (the default), Logfire records each script, each tool call's arguments and result, and each final
    result in your project, after its standard [scrubbing](../how-to-guides/scrubbing.md). The scripts and the tool
    results also pass through Logfire's servers to run.

## When to use this, and when not

Use a script when tools return more data than the model needs to read, or when the answer needs arithmetic, filtering,
or joining across many results.

Keep plain tool calls when each step depends on the model's judgment about the previous result, for example reading a
document and deciding what to search next. A script cannot replace that reasoning.

## Troubleshooting

- **`NameError: name 'list_customers' is not defined`**: the script called a function that is not in `external_lookup`.
  Pass every function the agent may call.
- **`MontyRuntimeError: MemoryError`**: the script holds more data than a sandbox allows. Let your tools return fewer
  fields or rows. See [What sandbox code can do](limits.md#resource-limits).
- **The script fails on an unsupported feature**, such as a class that inherits from another class: sandboxes run a
  subset of Python. See [What sandbox code can do](limits.md).

## Next steps

- [Work with large tool results without filling the context window](large-results.md): join data from several sources.
- [Give an agent a whole API](typed-api.md): check the agent's code against your types before it runs.
- [Use Agent Sandboxes with Pydantic AI](pydantic-ai.md): let a Pydantic AI agent write and run these scripts.
