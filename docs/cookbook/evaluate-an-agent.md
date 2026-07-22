---
title: "Instrument and evaluate an agent, end to end"
description: "Build a small Pydantic AI support agent, see its trace in Logfire, score its answers with an eval, catch a regression by comparing runs, and send the uncertain cases to a human."
---

# Instrument and evaluate an agent, end to end

This is the full loop an AI engineer runs on a real agent: build it, watch what it actually does, measure whether it's any good, prove a change made it better or worse, and route the answers you're unsure about to a person. You'll do all five here, on one small agent, in one sitting.

**Who this is for:** you're building an LLM-powered agent (an app where a language model reasons, calls your functions, and returns an answer) and you want to stop shipping on vibes. You've got a working feature; you want to know if it's *good*, and to be told when it stops being good.

**What you'll build:** a tiny [Pydantic AI](https://pydantic.dev/docs/ai/overview/) support-question agent, instrumented so every run (the model call, the tokens it used, the cost, and any tool calls) shows up in Logfire. Then a small evaluation (a repeatable quality test, like a test suite for output that has no single right answer) that scores its answers, and a second run that catches a regression.

**Time:** about 20–25 minutes.

Along the way you'll touch three Logfire features, each covered in depth on its own page: [AI observability](../ai-observability.md) (seeing what the agent did), [evaluations](../evaluate/overview.md) (measuring whether it's good), and [human review](../evaluate/human-review.md) (adding a person's judgment). This page stitches them into one journey; follow the links when you want the full API.

A few terms, defined once:

- A **span** is one unit of work: a single operation, with a name, a start, and a duration.
- A **trace** is the full journey of one request, made of nested spans (the agent run, its model call, each tool call).
- A **token** is the unit language models read and bill by: a few characters of text.
- A **scorer** (also called an **evaluator**) is the thing that judges an output. Each scorer produces a **score**: one saved quality rating for an output.

## Prerequisites

- **Python 3.10 or newer.**
- **A Logfire project and its write token.** The write token is the credential your app uses to send data to a Logfire project. Create a project and copy the token from **Project → Settings → Write tokens** in the Logfire web app. For local development you can instead run `logfire auth` in your terminal (this opens your browser to link the machine, no token to copy). See [Getting Started](../index.md) if you don't have a project yet.
- **A Google Gemini API key**, from [Google AI Studio](https://aistudio.google.com/apikey), set as the `GEMINI_API_KEY` environment variable. The agent below uses `google:gemini-flash-lite-latest`; any [model Pydantic AI supports](https://pydantic.dev/docs/ai/models/) works the same way: swap the model string and set that provider's key instead.

!!! note "Consequence: this sends data, and some of it costs money"
    Running the agent and the eval sends traces, inputs, outputs, and scores to your Logfire project, where they're stored and visible to your team. Every model call (the agent's own answers *and* the LLM-as-a-judge scorer you'll add in step 3) is a real, billed API call to your provider. A dozen cases with one judge is a few dozen calls; keep that in mind before you point this at a 500-case dataset.

Install the packages you need:

```bash
pip install "logfire[pydantic-ai]" pydantic-evals "pydantic-ai-slim[google]"
```

`logfire[pydantic-ai]` pulls in Logfire and Pydantic AI together; `pydantic-evals` is the evaluation library; the `[google]` extra adds the Gemini client. (Using `uv`? `uv add "logfire[pydantic-ai]" pydantic-evals "pydantic-ai-slim[google]"`.)

## Step 1: Build the agent

Here's the whole agent. It answers support questions and has one tool that looks up order status, so you'll see a real tool call in the trace, not just a bare model reply.

```python title="agent.py" skip-run="true" skip-reason="external-connection"
from __future__ import annotations

from pydantic_ai import Agent, RunContext

support_agent = Agent(
    'google:gemini-flash-lite-latest',
    system_prompt=(
        'You are a support agent for an online store. Answer the customer concisely. '
        'If they ask about an order, use the `order_status` tool to look it up.'
    ),
)


@support_agent.tool
async def order_status(ctx: RunContext[None], order_id: str) -> str:
    """Look up the current status of an order by its ID."""
    # A real app would query your database here; this is a stand-in.
    fake_orders = {'A100': 'shipped, arriving Friday', 'A200': 'processing'}
    return fake_orders.get(order_id, 'no order found with that ID')


if __name__ == '__main__':
    result = support_agent.run_sync('Where is my order A100?')
    print(result.output)
```

Run it (`python agent.py`) and you'll get a plain-English answer in your terminal. But you can't yet see *how* it got there, which is the whole problem this page solves.

## Step 2: Instrument it and see the trace

Add three lines. `logfire.configure()` connects the SDK to your project; `logfire.instrument_pydantic_ai()` records every agent run (the model call, the tokens, the cost, and each tool call) with no other code changes.

```python title="agent.py" hl_lines="5 7 8" skip-run="true" skip-reason="external-connection"
from __future__ import annotations

from pydantic_ai import Agent, RunContext

import logfire

logfire.configure()  # uses your write token or `logfire auth` credentials
logfire.instrument_pydantic_ai()  # records every Pydantic AI agent run

support_agent = Agent(
    'google:gemini-flash-lite-latest',
    system_prompt=(
        'You are a support agent for an online store. Answer the customer concisely. '
        'If they ask about an order, use the `order_status` tool to look it up.'
    ),
)


@support_agent.tool
async def order_status(ctx: RunContext[None], order_id: str) -> str:
    """Look up the current status of an order by its ID."""
    fake_orders = {'A100': 'shipped, arriving Friday', 'A200': 'processing'}
    return fake_orders.get(order_id, 'no order found with that ID')


if __name__ == '__main__':
    result = support_agent.run_sync('Where is my order A100?')
    print(result.output)
```

Run it again, then open the [Live view](../guides/web-ui/live.md), the project's home page, where traces stream in as they arrive. Within a second or two you'll see the agent run appear. Click it to expand the trace.

**What you'll see in Logfire:**

- The **agent run** as the top span, with the total time it took.
- Nested under it, the **model call** to `gemini-flash-lite-latest`, with the **input and output tokens** and the **cost** of that call.
- The **`order_status` tool call**: the `order_id` the model passed in, and the string your function returned.
- Opening the model call shows the exchange laid out like a chat transcript (system prompt, user message, the model's reply) in an [LLM panel](../guides/web-ui/llm-panels.md), not a wall of JSON.

This is the point of [AI observability](../ai-observability.md): when an answer is wrong later, you open its trace and see whether the *model* reasoned badly or a *tool* returned bad data. The two look identical from the outside, and the trace is how you tell them apart. For a per-provider, per-model rollup of calls, tokens, and cost, see the [LLMs and providers view](../guides/web-ui/llms.md).

## Step 3: Is it any good? Score it with an eval

Seeing one run tells you whether *that* answer was good. To know whether the agent is good *in general*, and to notice when a change makes it worse, you need an **evaluation**: run the agent over a fixed set of test cases and score every answer.

The pieces (all from [`pydantic_evals`](https://pydantic.dev/docs/ai/evals/evals/), covered fully in the [evals overview](../evaluate/overview.md)):

- A **Dataset** of **Cases**: each an input (a question) and, optionally, the expected answer.
- A **task**: the thing under test. Here it's a thin wrapper around the agent.
- **Scorers**: the judges. You'll attach two: a **code scorer** (fast, free, deterministic) that checks the answer mentions the right fact, and an **`LLMJudge`** (a language model grading another model's output) that rates tone and helpfulness, something code can't check.

```python title="eval.py" skip-run="true" skip-reason="external-connection"
from __future__ import annotations

from dataclasses import dataclass

from agent import support_agent
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, LLMJudge

import logfire

# Send the eval run to Logfire so it appears on the
# Evals: Datasets & Experiments page. Omit this to keep results local.
logfire.configure()
logfire.instrument_pydantic_ai()  # so each case's agent run is traced too


@dataclass
class Question:
    question: str


# A code scorer: passes if the answer contains an expected substring.
# Returns a bool, which pydantic-evals treats as a pass/fail assertion.
@dataclass
class MentionsFact(Evaluator[Question, str]):
    def evaluate(self, ctx: EvaluatorContext[Question, str]) -> bool:
        if not ctx.expected_output:  # no fact to check (the refund case), leave it to the judge
            return True
        return ctx.expected_output.lower() in ctx.output.lower()


dataset = Dataset[Question, str, None](
    name='support-agent',  # the dataset's identity; required in pydantic-evals
    cases=[
        Case(
            name='order_shipped',
            inputs=Question(question='Where is my order A100?'),
            expected_output='Friday',  # the answer should mention it arrives Friday
        ),
        Case(
            name='order_processing',
            inputs=Question(question='Has order A200 shipped yet?'),
            expected_output='processing',
        ),
        Case(
            name='refund_policy',
            inputs=Question(question='What is your refund policy?'),
            expected_output='',  # no fact to match; the judge alone scores tone
        ),
    ],
    evaluators=[
        MentionsFact(),
        # An LLM-as-a-judge scorer. One extra model call per case, so it costs
        # money. It grades tone and helpfulness, things code can't check.
        LLMJudge(
            rubric='The reply is polite, concise, and genuinely helpful to a customer.',
            model='google:gemini-flash-lite-latest',
        ),
    ],
)


async def task(inputs: Question) -> str:
    """The agent under test: run it and return the plain-text answer."""
    result = await support_agent.run(inputs.question)
    return result.output


async def main():
    report = await dataset.evaluate(task, name='support-agent-baseline')
    report.print(include_input=True, include_output=True)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
```

Run it (`python eval.py`). `report.print(...)` prints a table to your terminal, one row per case, an averages row, and a few columns: the output, per-case **Metrics** (requests, tokens, cost), a **Duration**, and an **Assertions** column. Each scorer that returns a pass/fail contributes one mark to the Assertions column, in the order you listed the evaluators (here `MentionsFact` then `LLMJudge`), so `✔✔` means both passed.

On the good agent, every case passes both scorers (output columns trimmed here for width; your exact wording, tokens, and cost vary by model and run):

| Case ID          | Output                                                       | Assertions | Cost      |
| ---------------- | ------------------------------------------------------------ | ---------- | --------- |
| order_shipped    | Your order A100 has been shipped and is scheduled to arrive this Friday. | ✔✔ | $0.000117 |
| order_processing | Your order A200 is currently processing.                     | ✔✔         | $0.000105 |
| refund_policy    | You may return most items within 30 days of delivery for a full refund… | ✔✔ | $0.000080 |
| **Averages**     |                                                              | **100.0%** |           |

**How to read it, and where a judge can fool you.** The two marks are your two scorers. `MentionsFact` is deterministic: it either found the expected substring or it didn't. The `LLMJudge` is graded by a model, so it measures only what its rubric asks: "polite, concise, helpful." That's exactly where it can pass an answer a human wouldn't: if the agent replied *"Your order A100 shipped and arrives Monday"* when the real answer is Friday, the judge would likely still pass it. The reply *reads* polite and helpful, and the rubric never mentioned the delivery date. The `MentionsFact` scorer, checking for `'Friday'`, would catch it. This is the reason to pair a cheap code scorer with a judge, and to [benchmark your judge against hand-labeled cases](../evaluate/overview.md#best-practices-with-the-reason-attached) before you trust its pass rate.

Because you called `logfire.configure()`, this run also lands on the [Evals: Datasets & Experiments](../guides/web-ui/evals.md) page as one **experiment** (one full pass of your agent over the dataset), where the next step compares it against a second run. See [Run an evaluation](../evaluate/datasets/evaluations.md) for the full offline path, and the [evals overview](../evaluate/overview.md) for the concepts.

## Step 4: Catch a regression

Now the payoff. Change something and prove whether it helped or hurt: the thing you can't do by re-reading a few answers.

Make one change that *degrades* quality. Cut the agent off from its tool, so it can no longer look up a real order. Change the system prompt to forbid tool use:

```python skip="true"
# in agent.py, replace the system prompt so the agent stops using tools:
system_prompt=(
    'You are a support agent for an online store. Answer from your own '
    'general knowledge only; do not use any tools.'
)
```

Then re-run the eval under a different name so it's a separate experiment:

```python skip="true"
# in eval.py, change the run name:
report = await dataset.evaluate(task, name='support-agent-no-tools')
```

Run `python eval.py` again. Now that the agent can't call `order_status`, it answers the order questions from general knowledge (*"I don't have access to your order information"*), so those replies no longer contain the expected fact, and `MentionsFact` fails on both order cases. The averages row drops (in one run, to **66.7%**; the exact number varies by model and run, but the *shape*, both order cases failing, is the point):

| Case ID          | Assertions |
| ---------------- | ---------- |
| order_shipped    | ✗✔         |
| order_processing | ✗✔         |
| refund_policy    | ✔✔         |
| **Averages**     | **66.7%**  |

Look at the order rows: `✗✔`. `MentionsFact` failed, but the `LLMJudge` still **passed**. "I don't have access to your order information" reads polite and helpful, so the judge waves it through; only the deterministic scorer catches that the answer is useless. That's the judge-fooling failure mode from step 3, caught live.

**What you'll see in Logfire:** open the [Evals: Datasets & Experiments](../guides/web-ui/evals.md) page, select both experiments (`support-agent-baseline` and `support-agent-no-tools`) with the checkboxes, and click **Compare**. Logfire lines the two runs up case by case and highlights the differences. You'll see the pass rate fall and can click straight into a failing case's trace to confirm the agent never called the tool.

That comparison is the whole reason evals exist: "it feels worse" becomes "the pass rate went from 100% to 66.7% on these cases, and here's the trace showing why." Wire this eval into your continuous integration (the automated checks that run on every change), asserting on the pass rate the report gives you, so a regression like this fails the build before it reaches a user.

Now change the prompt back so you're on the good version again.

## Step 5: Send the uncertain cases to a human

Some answers can't be settled by code or by a model: *was this reply actually the right call?* When the judge is unsure, or a real user reacts, route that answer to a person. Their judgment lands as the **same kind of score** as your automated ones, so it sits next to the code and LLM scores on the same output and rolls up into the same numbers.

The most direct path in your own product: capture a signal (a thumbs-up/down on the answer) and attach it to the span with `record_feedback`. Save the span's **traceparent** (a short string that identifies the span) when you answer, then reference it when the user reacts:

```python skip-run="true" skip-reason="external-connection"
import logfire
from logfire.experimental.annotations import get_traceparent, record_feedback

logfire.configure()

with logfire.span('answer support question') as span:
    traceparent = get_traceparent(span)  # save this alongside the reply you return
    ...  # run the agent, return the answer

# later, when the user clicks thumbs-up in your product:
record_feedback(
    traceparent,
    'helpful',  # the feedback's name
    True,  # bool = pass/fail, number = score, string = label
    comment='User clicked thumbs up',
)
```

The interactions a human flags as bad are exactly the cases you want to fold back into your dataset, so every future eval re-tests them. See [Human review](../evaluate/human-review.md) for annotating traces by hand, working an annotation queue, and the full `record_feedback` API.

!!! note "Experimental API"
    `record_feedback` and `get_traceparent` live in `logfire.experimental.annotations`; the interface may change in a future release.

## What you've got now

Starting from a handful of lines of agent code, you now have:

- **Every agent run traced**: model calls, tokens, cost, and tool calls, readable as a transcript, so a wrong answer is something you can *see* rather than guess at.
- **A repeatable quality measure**: a dataset and two scorers that turn "seems fine" into a pass rate you can defend.
- **A regression caught on purpose**: proof that comparing experiments tells you which direction a change moved quality, before a user finds out.
- **A path to human judgment**: user feedback and hand review landing as the same scores as your automated ones.

The insight the journey produces: observability and evaluation aren't separate tools. The trace tells you *what happened*; the eval tells you *whether it was good*; the human tells you *when the machine wasn't sure*. All three attach to the same run, so you can move from a bad score straight to the trace that explains it.

## Troubleshooting

- **Nothing appears on the Evals page?** Make sure `logfire.configure()` ran and `LOGFIRE_TOKEN` is set. Without it the eval still runs and prints to your terminal, but the results aren't sent to Logfire.
- **Model auth or rate-limit errors?** Confirm `GEMINI_API_KEY` is set. Free-tier limits are low, so the example uses a lighter model (`gemini-flash-lite-latest`) to stay under them.

## What's next

- [AI observability](../ai-observability.md): the full picture of what Logfire captures from your agent, and why seeing the whole stack (not just the model) matters.
- [Evaluate your AI](../evaluate/overview.md): the concepts behind datasets, scorers, scores, and experiments, plus best practices for LLM judges.
- [Run an evaluation](../evaluate/datasets/evaluations.md): the offline eval path in full, including hosted datasets shared with your team.
- [Human review](../evaluate/human-review.md): annotate traces, work an annotation queue, and capture user feedback as scores.
- [Live Evaluations](../guides/web-ui/live-evals.md): score real production traffic automatically, then send the uncertain cases here to human review.
