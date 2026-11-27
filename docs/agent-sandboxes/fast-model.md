---
title: "Call a fast model from agent code"
description: "Give agent scripts a function that asks a small, fast model, so one script can read many documents and do exact logic on the results."
---

# Call a fast model from agent code

!!! info "Beta"
    Agent Sandboxes is in beta on Logfire Cloud. If you do not see **Agent Sandboxes** in your project, see
    [Enable Agent Sandboxes](python.md#enable-agent-sandboxes).

"Which of our 60 vendor contracts renew automatically in the next 90 days, and allow a fee increase above 5%?" No single
tool answers this. Each contract states its terms in different words, so a person or a model must read each one. Then
the dates and percentages need exact comparison, which models do poorly by reading.

With Agent Sandboxes, your agent writes one script that divides the work in three:

- **Your main model writes the script once.** It plans the work. It does not read the contracts.
- **A small, fast model reads each contract.** The script calls it as a function, `extract()`, for all 60 contracts
  at once.
- **Python does the exact logic.** The script compares the dates and percentages, and returns only the matches.

When the script reads the contracts with `extract()`, the main model reads only a few rows, and the contract text stays
out of its context window.

## What this changes

We asked the question at the top of this page of a Pydantic AI agent three times with plain tool calls, and three
times with Agent Sandboxes through [Code Mode](pydantic-ai.md), with the instructions from the [agent
example](#see-the-script-your-agent-writes). Both agents had the same three tools from this page: `list_contracts`,
`get_contract_text`, and `extract`. The 60 sample contracts are about 2,000 words each, about 150,000 tokens in total.
The fast model in `extract()` was `gpt-6-luna`.

|                                      | Plain tool calls | Agent Sandboxes |
| ------------------------------------ | ---------------- | --------------- |
| `gpt-6.1-sol`: correct answers       | 3 of 3           | 2 of 3          |
| `gpt-6.1-sol`: input tokens (median) | 313,661          | 13,824          |
| `gpt-6-luna`: correct answers        | 0 of 3           | 3 of 3          |
| `gpt-6-luna`: input tokens (median)  | 235,673          | 16,629          |

These are three-run results on fixed sample data, not a prediction of production accuracy, latency, or cost.
Measure your own documents and questions before choosing an approach.

With plain tool calls, `gpt-6-luna` read all 60 contracts and missed one matching contract in each run. With Agent
Sandboxes, the fast model read one contract at a time and Python compared the values, so the answer was correct in
every run.

`gpt-6.1-sol` was correct in every run with plain tool calls, but it read about 314,000 tokens each time. With Agent
Sandboxes, it read about 14,000. In one run, its script missed a contract whose fees follow the consumer price index,
capped at 8%.

The input tokens in the table are the main model's. The fast model reads the contracts too: `extract()` sent
`gpt-6-luna` between 165,000 and 186,000 input tokens (median, depending on the main model) for the 60 contracts.
Plain tool calls were also faster: 33 seconds against 45 (median) with `gpt-6.1-sol`, and 18 against 66 with
`gpt-6-luna`.

The savings depend on the script reading the contracts with `extract()`. Without an instruction to do so,
`gpt-6.1-sol` returned the text of every contract from its script and read all of it, which took 490,017 input tokens
(median), more than plain tool calls. `gpt-6-luna` used `extract()` without the instruction.

## Before you start

- Follow [Run code from Python](python.md) to install `logfire[agent-sandboxes]` and set `LOGFIRE_API_KEY` to a key
  with permission to run code in agent sandboxes.
- This page uses [Pydantic AI](https://pydantic.dev/docs/ai/overview/) to call the fast model. Install it with
  `pip install pydantic-ai`.
- Set `OPENAI_API_KEY` to a key from the [OpenAI API keys page](https://platform.openai.com/api-keys).

!!! warning "Documents and model answers leave your application"
    `extract()` sends each contract's full text to your model provider, OpenAI in this example. The contract text and
    the extracted values also pass through Logfire for execution, and hosted telemetry can record this content in your
    project. See [tracing and storage](limits.md#understand-tracing-and-storage).

## Give the script a function that asks a fast model

Save these sample contracts as `contracts.py`. There are 60 contracts of about 2,000 words each. The renewal and fee
terms use different wording from one contract to the next, and other clauses contain dates and percentages that do
not answer the question. Each contract also stores its correct values in `answer`, so you can check what the fast
model returns. Replace this file with your document store.

??? example "contracts.py: 60 sample contracts"

    ```python title="contracts.py" skip-run="true" skip-reason="external-connection"
    import random
    from datetime import date, timedelta

    VENDORS = ['Acme Hosting', 'Globex Data', 'Initech Support', 'Umbrella Logistics', 'Hooli Cloud', 'Stark Tooling']
    RENEWAL = [  # (clause, renews without action by the customer)
        ('This Agreement renews automatically for successive one-year terms unless either party gives notice.', True),
        ('The term extends by twelve months at each anniversary without further action by the parties.', True),
        ('Unless the Customer terminates in writing before the renewal date, the Services continue for one year.', True),
        ('The Customer may end this Agreement on the renewal date. Otherwise it rolls over for a further year.', True),
        ('This Agreement never renews automatically. Any renewal needs a new order form signed by the Customer.', False),
        ('This Agreement ends on the renewal date unless both parties sign an extension.', False),
        ('Neither party must renew. The Supplier sends a renewal quote 90 days before the renewal date.', False),
    ]
    FEES = [  # (clause, the clause allows an increase of {p}%)
        ('Fees for each renewal term increase by {p}% over the fees for the previous term.', True),
        ('The Supplier may raise its charges at renewal by no more than {p} percent.', True),
        ('At renewal, fees change with the consumer price index, capped at {p}%.', True),
        ('Fees stay fixed for any renewal term.', False),
        ('Renewal fees equal the current fees, less a loyalty discount of {p}%.', False),
    ]
    BOILERPLATE = [  # clauses with dates and percentages that do not answer the question
        'Payment. The Customer pays each invoice within 30 days. Late amounts accrue interest at {late}% per year.',
        (
            'Service levels. If monthly availability falls below 99.5%, the Customer receives a credit of {credit}% of the '
            "month's fees."
        ),
        "Liability. Each party's total liability is capped at 150% of the fees paid in the twelve months before a claim.",
        (
            'Confidentiality. Each party protects the confidential information of the other party with reasonable care, '
            'during the term and for five years after it ends.'
        ),
        (
            "Data protection. The Supplier processes personal data only on the Customer's documented instructions, and "
            'deletes it within 30 days after this Agreement ends.'
        ),
        'Insurance. The Supplier keeps professional liability insurance of at least 2,000,000 USD during the term.',
        (
            'Termination for breach. Either party may terminate on 30 days written notice if the other party does not cure '
            'a material breach in that time.'
        ),
        (
            'Assignment. Neither party may assign this Agreement without the written consent of the other party, which the '
            'other party may not unreasonably withhold.'
        ),
        'Notices. Notices are given in writing to the addresses on the order form, and take effect on receipt.',
        'Governing law. The laws of the State of New York govern this Agreement.',
    ]

    STANDARD = [  # clauses with no renewal terms, fee changes, dates, or percentages
        (
            'Definitions. In this Agreement, "Affiliate" means any entity that controls, is controlled by, or is under '
            'common control with a party. "Business Day" means a day other than a Saturday, Sunday, or public holiday in '
            'New York. "Documentation" means the user guides and technical specifications that the Supplier makes '
            'available for the Services.'
        ),
        (
            'Scope. The Supplier provides the Services described in each order form and in Schedule 1. An order form '
            'forms part of this Agreement when both parties sign it. If an order form conflicts with these terms, these '
            'terms apply unless the order form expressly names the clause that it replaces.'
        ),
        (
            'Customer obligations. The Customer gives the Supplier timely access to the information, systems, and '
            'personnel that the Supplier reasonably needs to provide the Services. The Supplier is not responsible for a '
            'delay caused by a failure to give this access, if the Supplier tells the Customer about the delay promptly.'
        ),
        (
            'Acceptable use. The Customer must not use the Services to store or send unlawful material, to interfere '
            'with the operation of the Services, or to gain unauthorized access to any system. The Supplier may suspend '
            'the affected part of the Services while it investigates a reasonable suspicion of misuse, and it tells the '
            'Customer about the suspension without delay.'
        ),
        (
            'Support. The Supplier provides support by email and telephone between 08:00 and 18:00 Eastern Time on '
            'Business Days. It responds to a critical incident within {response} hours and to any other incident within '
            'one Business Day. It keeps a record of each incident and its resolution, and shares the record on request.'
        ),
        (
            'Maintenance. The Supplier may perform scheduled maintenance outside business hours. It gives the Customer '
            'at least {notice} days notice of maintenance that it expects to interrupt the Services for more than one '
            'hour. Emergency maintenance that protects the security of the Services may happen without notice.'
        ),
        (
            'Security. The Supplier maintains a written information security program with administrative, physical, and '
            'technical safeguards that suit the nature of the Customer Data. The program includes access controls, '
            'encryption of Customer Data in transit and at rest, logging of administrative access, and staff training.'
        ),
        (
            'Security incidents. The Supplier notifies the Customer without undue delay, and in any case within '
            '{incident} hours, after it becomes aware of a security incident that affects Customer Data. The notice '
            'describes the incident, the data affected, and the steps that the Supplier takes to contain it.'
        ),
        (
            'Subcontractors. The Supplier may use subcontractors to provide parts of the Services. The Supplier remains '
            'responsible for the acts and omissions of its subcontractors as if they were its own. On request, the '
            'Supplier gives the Customer a current list of the subcontractors that process Customer Data.'
        ),
        (
            'Personnel. The Supplier assigns qualified and experienced personnel to provide the Services. The Customer '
            "may ask the Supplier to remove a person from the Customer's account for a reasonable cause, and the "
            'Supplier replaces that person within a reasonable time.'
        ),
        (
            'Intellectual property. Each party keeps all rights in the materials that it owned before this Agreement or '
            'that it develops independently of it. The Supplier grants the Customer a non-exclusive, non-transferable '
            "right to use the Services and the Documentation during the term for the Customer's internal purposes."
        ),
        (
            'Customer Data. The Customer owns all Customer Data. The Supplier uses Customer Data only to provide the '
            'Services and to meet its obligations under this Agreement. The Supplier does not sell Customer Data, and it '
            'does not use Customer Data to train models for other customers.'
        ),
        (
            'Feedback. If the Customer gives the Supplier suggestions about the Services, the Supplier may use them '
            'without restriction. The Customer does not have to give feedback, and feedback does not include Customer '
            "Data or the Customer's confidential information."
        ),
        (
            'Warranties. The Supplier warrants that it provides the Services with reasonable skill and care, and that '
            'the Services perform materially as the Documentation describes. If they do not, the Supplier corrects the '
            'defect within a reasonable time or, if it cannot, the Customer may terminate the affected order form.'
        ),
        (
            'Disclaimer. Except as this Agreement states, neither party gives any warranty, express or implied, '
            'including any implied warranty of merchantability, fitness for a particular purpose, or non-infringement.'
        ),
        (
            'Indemnity. The Supplier defends the Customer against any third-party claim that the Services infringe that '
            "party's intellectual property rights, and pays the damages that a court finally awards. The Customer tells "
            'the Supplier promptly about the claim, lets the Supplier control the defense, and gives reasonable help at '
            "the Supplier's expense."
        ),
        (
            'Exclusions. Neither party is liable for loss of profits, loss of revenue, or any indirect or consequential '
            'loss, even if the other party knew that the loss was possible. This exclusion does not apply to a breach of '
            "confidentiality, to the indemnity, or to a party's fraud."
        ),
        (
            'Force majeure. Neither party is liable for a delay or failure caused by an event outside its reasonable '
            'control, such as a natural disaster, war, or a failure of public utilities. The affected party tells the '
            'other party promptly and uses reasonable efforts to reduce the effect of the event. If the event continues '
            'for more than {force_majeure} days, either party may terminate the affected order form.'
        ),
        (
            "Audit. Once in each contract year, the Customer may audit the Supplier's compliance with the data "
            'protection and security clauses, on {audit} Business Days written notice. The audit takes place during '
            "business hours and must not unreasonably disrupt the Supplier's operations. Each party pays its own costs."
        ),
        (
            'Records. The Supplier keeps complete and accurate records of the Services that it provides and the amounts '
            'that it invoices. It keeps these records for {records} years after it provides the Services, and makes them '
            "available to the Customer's auditors on reasonable notice."
        ),
        (
            'Exit assistance. When this Agreement ends for any reason, the Supplier gives the Customer reasonable help to '
            'move the Services to the Customer or to a new supplier. The Supplier returns all Customer Data in a common '
            'machine-readable format, and then deletes its copies as the data protection clause requires.'
        ),
        (
            'Change control. Either party may propose a change to the Services in writing. Within {change} Business '
            'Days, the Supplier tells the Customer what effect the change has on the Services and the timetable. A '
            'change takes effect only when both parties sign a written change order.'
        ),
        (
            'Dispute resolution. The parties first try in good faith to settle any dispute through their account '
            'managers. If the account managers cannot settle it within {dispute} days, either party may refer it to '
            'senior executives of both parties, and then to the courts that the governing law clause names.'
        ),
        (
            'Non-solicitation. During the term and for one year after it ends, neither party solicits for employment any '
            'employee of the other party who worked on the Services, except through a general advertisement that is not '
            "aimed at that party's employees."
        ),
        (
            'Entire agreement. This Agreement, with its schedules and order forms, is the entire agreement between the '
            'parties about its subject matter. It replaces all earlier agreements, proposals, and statements about that '
            'subject matter. Each party confirms that it did not rely on any statement that this Agreement does not '
            'contain.'
        ),
        (
            'Changes to this Agreement. A change to this Agreement is valid only if it is in writing and signed by both '
            'parties. A failure or delay to exercise a right is not a waiver of that right.'
        ),
        (
            'Severability. If a court finds any part of this Agreement invalid or unenforceable, the rest of this '
            'Agreement stays in effect, and the parties replace the invalid part with a valid provision that comes as '
            'close as possible to their original intent.'
        ),
        (
            'Counterparts. The parties may sign this Agreement in counterparts, including by electronic signature. Each '
            'counterpart is an original, and together they form one agreement.'
        ),
        (
            'Publicity. Neither party uses the name or logo of the other party in any publicity, advertising, or '
            'customer list without the prior written consent of the other party.'
        ),
        (
            'Compliance. Each party complies with all anti-bribery, export control, and sanctions laws that apply to it '
            'in connection with this Agreement, and keeps policies and procedures designed to ensure this compliance.'
        ),
    ]
    SERVICES = [  # (service, unit)
        ('Managed hosting', 'server'),
        ('Object storage', 'terabyte'),
        ('Database backup', 'terabyte'),
        ('Premium support', 'seat'),
        ('Infrastructure monitoring', 'host'),
        ('Data transfer', 'terabyte'),
        ('Log retention', 'terabyte'),
        ('Load balancing', 'instance'),
        ('Disaster recovery site', 'region'),
        ('Identity management', 'user'),
        ('Web application firewall', 'domain'),
        ('Content delivery', 'terabyte'),
        ('Container hosting', 'cluster'),
        ('Penetration testing', 'assessment'),
        ('Onboarding services', 'project'),
        ('Developer training', 'session'),
        ('Dedicated account management', 'account'),
        ('Email delivery', 'million messages'),
        ('Secrets management', 'vault'),
        ('Network peering', 'connection'),
    ]
    NUMBERS = {
        'response': [1, 2, 4],
        'notice': [5, 7, 10],
        'incident': [24, 48, 72],
        'force_majeure': [30, 60, 90],
        'audit': [10, 15, 20],
        'records': [3, 5, 7],
        'change': [5, 10],
        'dispute': [20, 30, 45],
    }


    def _format_date(d: date, style: int) -> str:
        return [d.isoformat(), f'{d:%B} {d.day}, {d.year}', f'{d.day} {d:%B} {d.year}'][style]


    def _contract(i: int) -> dict:
        rnd, layout = random.Random(i), random.Random(10_000 + i)
        renewal_date = date(2026, 11, 12) + timedelta(days=rnd.randint(1, 240))
        signed = date(rnd.randint(2022, 2025), rnd.randint(1, 12), rnd.randint(1, 28))
        renewal, (fees, allows_increase) = rnd.choice(RENEWAL), rnd.choice(FEES)
        pct = rnd.choice([3, 4, 6, 8, 10])
        clauses = [
            f'Term. The current term ends on {_format_date(renewal_date, rnd.randrange(3))} (the "renewal date").',
            f'Renewal. {renewal[0]}',
            f'Fees. {fees.format(p=pct)}',
            *(c.format(late=rnd.choice([1.5, 8, 12]), credit=rnd.choice([5, 10, 25])) for c in BOILERPLATE),
        ]
        rnd.shuffle(clauses)
        signed_on = _format_date(signed, rnd.randrange(3))
        numbers = {name: layout.choice(values) for name, values in NUMBERS.items()}
        clauses += [c.format(**numbers) for c in STANDARD]
        layout.shuffle(clauses)
        services = []
        for n, (service, unit) in enumerate(SERVICES, 1):
            quantity, price = layout.randint(1, 40), layout.randint(2, 400) * 25
            services.append(
                f'S-{n}. {service}: {quantity} x {unit}, at {price:,} USD per {unit} per month, billed monthly.'
            )
        vendor = VENDORS[i % 6]
        header = f'MASTER SERVICES AGREEMENT between the Customer and {vendor} (Contract C-{i:03}), signed on {signed_on}.'
        numbered = [f'{n}. {c}' for n, c in enumerate(clauses, 1)]
        text = '\n'.join([header, *numbered, 'SCHEDULE 1. SERVICES AND CHARGES', *services])
        answer = {'auto_renews': renewal[1], 'renewal_date': renewal_date, 'increase': pct if allows_increase else 0}
        return {'id': f'C-{i:03}', 'vendor': vendor, 'text': text, 'answer': answer}


    CONTRACTS = [_contract(i) for i in range(60)]
    ```

`extract()` is a normal host function. It runs in your application, and it sends one small request to a fast model.
The script chooses the fields, so the same function serves many different questions.

```python title="tools.py" skip-run="true" skip-reason="external-connection"
import asyncio

from contracts import CONTRACTS
from pydantic_ai import Agent


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
    return {name: result.output.get(name) for name in fields}


TOOLS = {'list_contracts': list_contracts, 'get_contract_text': get_contract_text, 'extract': extract}
```

Two details matter:

- **The semaphore.** A script can start hundreds of `extract()` calls at once with `asyncio.gather`. The semaphore
  lets ten of them reach the model provider at a time. It limits this process only, so set the number to fit your
  provider's rate limit.
- **The fast model returns strings.** `extract()` returns every field that the script asked for, with `None` when
  the model leaves one out, so the script can index the result. The script asks for a format in each field
  description, such as `YYYY-MM-DD`, and converts the values in Python. A conversion error names the bad value, and
  the main model can correct the script.

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
    'increase_percent': "the largest fee increase allowed at renewal, as a number, or '0' if fees cannot increase",
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

Run `python main.py`. For the sample contracts, the correct answer is these six rows. If your rows differ, the
fast model misread a contract: compare the `extract` spans in the trace with the contract's `answer`.

```
{'id': 'C-057', 'vendor': 'Umbrella Logistics', 'renews_in_days': 11, 'increase_percent': 10.0}
{'id': 'C-039', 'vendor': 'Umbrella Logistics', 'renews_in_days': 54, 'increase_percent': 8.0}
{'id': 'C-059', 'vendor': 'Stark Tooling', 'renews_in_days': 58, 'increase_percent': 6.0}
{'id': 'C-052', 'vendor': 'Hooli Cloud', 'renews_in_days': 69, 'increase_percent': 8.0}
{'id': 'C-045', 'vendor': 'Umbrella Logistics', 'renews_in_days': 70, 'increase_percent': 6.0}
{'id': 'C-007', 'vendor': 'Globex Data', 'renews_in_days': 83, 'increase_percent': 10.0}
```

The script made 121 calls to your functions: one list, 60 contract reads, and 60 fast-model requests.
The main model reads six rows.

Three details in the script matter:

- **`request_timeout=120`.** The default is 10 seconds for one `feed_run()` call. Sixty model requests can take
  longer.
- **The script states today's date.** Sandbox code has no clock. Put the date in your agent's instructions, or give
  the script a function that returns it.
- **Time that the script spends waiting does not count toward its processing limit.** The limit of 50 milliseconds
  for each run applies to the Python work in the sandbox. See [resource limits](limits.md#resource-limits).

In your application, the agent writes the script and your code runs it. See [Use Agent Sandboxes with Pydantic
AI](pydantic-ai.md) or [Add a code tool to any agent](any-framework.md). With Pydantic AI, pass `extract` in the
agent's `tools` with your other tools. Code Mode makes it a function that scripts can call. Code Mode uses the pool
that `monty_sandbox` returns, so set the longer timeout there. The instructions tell the model to read documents with
`extract()`. Without them, `gpt-6.1-sol` read the full text of every contract itself:

```python title="agent.py" skip-run="true" skip-reason="external-connection"
from functools import partial

from pydantic_ai import Agent
from pydantic_ai_harness import CodeMode
from tools import extract, get_contract_text, list_contracts

import logfire

logfire.configure()
logfire.instrument_pydantic_ai()

agent = Agent(
    'openai:gpt-6.1-sol',
    tools=[list_contracts, get_contract_text, extract],
    instructions=(
        'Today is 2026-11-12. Read documents with extract(), and do not return their text from run_code. '
        'Do date and number comparisons in Python, and return only the rows that answer the question.'
    ),
    capabilities=[CodeMode(monty_sandbox=partial(logfire.agent_sandboxes, request_timeout=120))],
)
```

## When to use this, and when not

Use a fast model inside a script when the task has many small decisions that need language understanding, and the
results then need exact logic: classify 500 support tickets and count them by product, extract fields from invoices
and add them up, or read search results and keep the relevant ones.

If your model can read all the documents at once without mistakes, plain tool calls are simpler and faster. We
measured the same 60 contracts without their 30 standard clauses and services schedule, about 270 words each. Plain
tool calls were correct in 3 of 3 runs with both models. Agent Sandboxes cut the input tokens of `gpt-6.1-sol` from
50,619 to 11,454 (median), but its answer was correct in only 2 of 3 runs. With `gpt-6-luna`, Agent Sandboxes used
more input tokens than plain tool calls.

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
