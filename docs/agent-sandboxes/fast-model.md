---
title: "Call a fast model from agent code"
description: "Give agent scripts a function that asks a small, fast model, so one script can read many documents and do exact logic on the results."
---

# Call a fast model from agent code

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

"Which of our 60 vendor contracts renew automatically in the next 90 days, with a fee increase above 5%?" No single
tool answers this. Each contract states its terms in different words, so a person or a model must read each one. Then
the dates and percentages need exact comparison, which models do poorly by reading.

With Agent Sandboxes, your agent writes one script that divides the work in three:

- **Your main model writes the script once.** It plans the work. It does not read the contracts.
- **A small, fast model reads each contract.** The script calls it as a function, `extract()`, for all 60 contracts
  at once.
- **Python does the exact logic.** The script compares the dates and percentages, and returns only the matches.

The main model reads a few rows. The contract text never enters its context window.

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key
  with permission to run code in agent sandboxes.
- This page uses [Pydantic AI](https://pydantic.dev/docs/ai/overview/) to call the fast model. Install it with
  `pip install pydantic-ai`.
- Set `OPENAI_API_KEY` to a key from the [OpenAI API keys page](https://platform.openai.com/api-keys).

!!! warning "Documents and model answers leave your application"
    The contract text and the extracted values pass through Logfire for execution. Hosted telemetry can record this
    content in your project. See [tracing and storage](limits.md#understand-tracing-and-storage).

## Give the script a function that asks a fast model

`extract()` is a normal host function. It runs in your application, and it sends one small request to a fast model.
The script chooses the fields, so the same function serves many different questions.

The first two functions return sample contracts, so you can run the example. Replace them with calls to your
document store.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import asyncio
import random

from pydantic_ai import Agent

VENDORS = ['Acme Hosting', 'Globex Data', 'Initech Support', 'Umbrella Logistics', 'Hooli Cloud', 'Stark Tooling']
RENEWAL = [
    'This Agreement renews automatically for successive one-year terms unless either party gives notice.',
    'The term extends by twelve months at each anniversary without further action by the parties.',
    'This Agreement ends on the renewal date unless both parties sign an extension.',
    'Renewal requires a new order form signed by the Customer.',
]
INCREASE = [
    'Fees for each renewal term increase by {pct}% over the fees for the previous term.',
    'The Supplier may raise its charges at renewal by no more than {pct} percent.',
    'Fees stay fixed for any renewal term.',
]


def _contract(i: int) -> dict:
    rnd = random.Random(i)
    renewal, increase = rnd.randrange(4), rnd.randrange(3)
    month, day, pct = rnd.randint(1, 12), rnd.randint(1, 28), rnd.choice([3, 4, 6, 8, 10])
    year = 2027 if month < 11 else 2026
    text = (
        f'MASTER SERVICES AGREEMENT between the Customer and {VENDORS[i % 6]} (Contract C-{i:03}).\n'
        f'1. Term. The current term ends on {year}-{month:02}-{day:02} (the "renewal date").\n'
        f'2. Renewal. {RENEWAL[renewal]}\n'
        f'3. Fees. {INCREASE[increase].format(pct=pct)}\n'
        '4. Confidentiality. Each party protects the confidential information of the other party.\n'
    )
    return {'id': f'C-{i:03}', 'vendor': VENDORS[i % 6], 'text': text}


CONTRACTS = [_contract(i) for i in range(60)]


async def list_contracts() -> list[dict]:
    """List vendor contracts. Each has `id` and `vendor`."""
    return [{'id': c['id'], 'vendor': c['vendor']} for c in CONTRACTS]


async def get_contract_text(contract_id: str) -> str:
    """Return the full text of one contract."""
    await asyncio.sleep(0.05)  # stands in for a document store
    return next(c['text'] for c in CONTRACTS if c['id'] == contract_id)


fast_model = Agent(
    'openai:gpt-6-luna',
    output_type=dict[str, str | None],
    instructions=(
        'Extract the requested fields from the text. Return one value for each field, in the format that the '
        'field asks for. Use null when the text does not state a value.'
    ),
)
limit = asyncio.Semaphore(10)


async def extract(text: str, fields: dict[str, str]) -> dict[str, str | None]:
    """Read `text` with a fast model and return one value for each field.

    `fields` maps each field name to a description of the value and its format.
    A value is None when the text does not state it.
    """
    async with limit:
        result = await fast_model.run(f'Fields: {fields}\n\nText:\n{text}')
    return result.output


TOOLS = {'list_contracts': list_contracts, 'get_contract_text': get_contract_text, 'extract': extract}
```

Two details matter:

- **The semaphore.** A script can start hundreds of `extract()` calls at once with `asyncio.gather`. The semaphore
  lets ten of them reach the model provider at a time, so the script does not exceed your rate limit.
- **The fast model returns strings.** The script asks for a format in each field description, such as `YYYY-MM-DD`,
  and converts the values in Python. A conversion error names the bad value, and the main model can correct the
  script.

## See the script your agent writes

A model asked the question at the top of this page can write a script like this one:

```python title="main.py" skip-run="true" skip-reason="external-connection"
import asyncio

from tools import TOOLS

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

AGENT_CODE = """
import asyncio
from datetime import date, timedelta

contracts = await list_contracts()
texts = await asyncio.gather(*[get_contract_text(c['id']) for c in contracts])
fields = {
    'auto_renews': "'yes' if the contract renews without action by the customer, else 'no'",
    'renewal_date': 'the renewal date as YYYY-MM-DD',
    'increase_percent': "the largest fee increase allowed at renewal, as a number, or '0' if fees stay fixed",
}
terms = await asyncio.gather(*[extract(text, fields) for text in texts])

today = date(2026, 11, 12)
found = []
for c, t in zip(contracts, terms):
    if t['auto_renews'] != 'yes' or not t['renewal_date']:
        continue
    days = (date.fromisoformat(t['renewal_date']) - today).days
    increase = float(t['increase_percent'] or 0)
    if 0 <= days <= 90 and increase > 5:
        found.append({**c, 'renews_in_days': days, 'increase_percent': increase})
sorted(found, key=lambda f: f['renews_in_days'])
"""


async def main():
    async with logfire.agent_sandboxes(request_timeout=120) as pool:
        async with pool.checkout() as session:
            for row in await session.feed_run(AGENT_CODE, external_lookup=TOOLS):
                print(row)


asyncio.run(main())
```

Run `python main.py`. For the sample contracts, the correct answer is these five rows:

```
{'id': 'C-018', 'vendor': 'Acme Hosting', 'renews_in_days': 3, 'increase_percent': 6.0}
{'id': 'C-056', 'vendor': 'Initech Support', 'renews_in_days': 5, 'increase_percent': 6.0}
{'id': 'C-021', 'vendor': 'Umbrella Logistics', 'renews_in_days': 32, 'increase_percent': 6.0}
{'id': 'C-046', 'vendor': 'Hooli Cloud', 'renews_in_days': 68, 'increase_percent': 10.0}
{'id': 'C-022', 'vendor': 'Hooli Cloud', 'renews_in_days': 69, 'increase_percent': 8.0}
```

The script made 121 calls to your functions: one list, 60 contract reads, and 60 fast-model requests.
The main model reads five rows.

Three details in the script matter:

- **`request_timeout=120`.** The default is 10 seconds for one `feed_run()` call. Sixty model requests can take
  longer.
- **The script states today's date.** Sandbox code has no clock. Put the date in your agent's instructions, or give
  the script a function that returns it.
- **Time that the script spends waiting does not count toward its processing limit.** The limit of 50 milliseconds
  for each run applies to the Python work in the sandbox. See [resource limits](limits.md#resource-limits).

In your application, the agent writes the script and your code runs it. See [Use Agent Sandboxes with Pydantic
AI](pydantic-ai.md) or [Add a code tool to any agent](any-framework.md). With Pydantic AI, pass `extract` in the
agent's `tools` with your other tools. Code Mode makes it a function that scripts can call.

## When to use this, and when not

Use a fast model inside a script when the task has many small decisions that need language understanding, and the
results then need exact logic: classify 500 support tickets and count them by product, extract fields from invoices
and add them up, or read search results and keep the relevant ones.

Give the fast model small, independent questions. A question that needs several documents at once, or a judgment
that depends on the whole task, belongs to your main model.

A fast model makes mistakes. Check a sample of its answers before you rely on a result. Each `extract()` call is a
span in the trace, so you can read every text and every answer.

## Verify it worked

Open the [Live view](../guides/web-ui/live.md). You should see one `run code` span with a child span for each of the
121 calls. Each `extract` call contains the fast model's request, with its input, output, token count, and cost.

## Troubleshooting

- **`MontyCrashedError` with `timed_out=True`**: the script took longer than `request_timeout`. Pass a larger value
  to `logfire.agent_sandboxes()`, or raise the semaphore limit if your rate limit allows it.
- **`ValueError: Invalid isoformat string`**: the fast model returned a date in another format. Make the field
  description more exact, or let the script skip values that it cannot convert.
- **`429` errors from the model provider**: lower the semaphore limit in `tools.py`.
- **`MontyRuntimeError: MemoryError`**: the script holds too much text. Let a host function read each document and
  call the fast model, so the text stays in your application. See [resource limits](limits.md#resource-limits).

## Next steps

- [Answer questions that need dozens of tool calls](many-tool-calls.md): the same pattern without a fast model.
- [Give an agent a whole API](typed-api.md): check the script against your function signatures before it runs.
- [Pause agent code for human approval](approval.md): let a person approve what the script found before it acts.
