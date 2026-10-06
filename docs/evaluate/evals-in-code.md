---
title: "Evals in code"
description: "Run evaluations against local or hosted datasets with pydantic-evals, and see a real printed score table."
---

# Evals in code

Run an evaluation from Python and you get a score table you can read at a glance and compare over time. Evals in Logfire are powered by [pydantic-evals](https://pydantic.dev/docs/ai/evals/evals/); this page shows the offline path end to end. For the concepts behind it (scorers, scores, offline vs online), read the [evals overview](overview.md) first.

Your test cases can live in either of two places, and the evaluation step is identical once you have a `Dataset` in hand:

- **Code-defined datasets** are defined in code (or loaded from YAML, a human-readable configuration format) as a [`pydantic_evals.Dataset`][pydantic_evals.Dataset]. No server round-trip. This is the simplest way to start and is all many projects need.
- **Hosted datasets** are stored on Logfire, editable in the [web UI](manage-datasets.md), and fetched back as a typed `Dataset`. Useful when you curate cases from production traces or collaborate with teammates.

## A worked example

Here is a complete, runnable evaluation. The system under test is deterministic so the example is reproducible; in real use, `classify_sentiment` would call your LLM or agent. Two scorers run on every case: a custom `ExactMatch` and the built-in `IsInstance`.

```py title="sentiment_eval.py" skip-run="true" skip-reason="requires-new-pydantic-version"
from dataclasses import dataclass

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext, IsInstance


# The AI system under test. Deterministic here so the example is reproducible;
# in real use this calls your LLM or agent.
def classify_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ('love', 'great', 'excellent')):
        return 'positive'
    if any(word in lowered for word in ('hate', 'terrible', 'awful')):
        return 'negative'
    return 'neutral'


@dataclass
class ExactMatch(Evaluator[str, str]):
    def evaluate(self, ctx: EvaluatorContext[str, str]) -> bool:
        return ctx.output == ctx.expected_output


dataset = Dataset[str, str, None](
    name='sentiment-eval',
    cases=[
        Case(name='clearly_positive', inputs='I love this product', expected_output='positive'),
        Case(name='clearly_negative', inputs='This is terrible', expected_output='negative'),
        Case(name='neutral_statement', inputs='It is a chair', expected_output='neutral'),
        Case(name='subtle_negative', inputs='I would not recommend it', expected_output='negative'),
    ],
    evaluators=[ExactMatch(), IsInstance(type_name='str')],
)

report = dataset.evaluate_sync(classify_sentiment)
report.print(include_input=True, include_output=True)
```

Running it prints a table. Each cell in the **Assertions** column is one mark per scorer, in order (`ExactMatch`, then `IsInstance`):

```text
                      Evaluation Summary: classify_sentiment
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ Case ID           ┃ Inputs                   ┃ Outputs  ┃ Assertions ┃ Duration ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━┩
│ clearly_positive  │ I love this product      │ positive │ ✔✔         │    683µs │
│ clearly_negative  │ This is terrible         │ negative │ ✔✔         │    689µs │
│ neutral_statement │ It is a chair            │ neutral  │ ✔✔         │    657µs │
│ subtle_negative   │ I would not recommend it │ neutral  │ ✗✔         │    625µs │
│ Averages          │                          │          │ 87.5% ✔    │    663µs │
└───────────────────┴──────────────────────────┴──────────┴────────────┴──────────┘
```

The `subtle_negative` case is the one that matters: the classifier returned `neutral` where `negative` was expected, so `ExactMatch` failed (`✗`) while `IsInstance` still passed (`✔`), and the aggregate lands at 87.5%. That single number is what you compare when you change a prompt or swap a model. To send this run to the **Experiments** tab in Logfire for comparison over time, add `logfire.configure()` before you evaluate.

## Evaluating against your real AI task

Swap the deterministic function for your actual system, and configure Logfire so the run shows up in the UI:

```python skip-run="true" skip-reason="example-ai-task"
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

import logfire

# Configure Logfire so the run appears on the Experiments tab in Logfire.
# Without this, the evaluation still runs but its results stay local.
logfire.configure()
logfire.instrument_pydantic_ai()  # optional: traces the AI task under test


@dataclass
class QuestionInput:
    question: str
    context: str | None = None


@dataclass
class AnswerOutput:
    answer: str
    confidence: float


dataset = Dataset[QuestionInput, AnswerOutput, None](
    name='qa-golden-set',
    cases=[
        Case(
            name='capital_of_france',
            inputs=QuestionInput(question='What is the capital of France?'),
            expected_output=AnswerOutput(answer='Paris', confidence=1.0),
        ),
        # ... more cases
    ],
)


async def my_qa_task(inputs: QuestionInput) -> AnswerOutput:
    """The AI system under test: call an LLM, run an agent, hit your API."""
    ...


async def run_evaluation():
    report = await dataset.evaluate(my_qa_task)
    report.print()
```

!!! note "Storing the dataset and sending results are independent choices"
    Whether you *store* the dataset on Logfire and whether you *send* results to Logfire are two separate decisions. You can fetch a hosted dataset and run a purely local evaluation that only prints to the console by omitting `logfire.configure()`. We recommend configuring Logfire during evaluation so runs show up alongside your dataset in the UI. You can also load local datasets from YAML files, see the [pydantic-evals docs](https://pydantic.dev/docs/ai/evals/evals/).

## Evaluating a hosted dataset

To manage cases on the server (so teammates can edit them in the UI, or you can seed them from production traces), fetch a hosted dataset and use it exactly like a code-defined one. Hosted datasets are typically created in the [web UI](manage-datasets.md) or published from code, see the [Datasets SDK](datasets-sdk.md).

```python skip-run="true" skip-reason="external-connection"
from dataclasses import dataclass

from pydantic_evals import Dataset

import logfire
from logfire.experimental.api_client import LogfireAPIClient


@dataclass
class QuestionInput:
    question: str


@dataclass
class AnswerOutput:
    answer: str


logfire.configure()


async def my_qa_task(inputs: QuestionInput) -> AnswerOutput:
    """The AI system under test."""
    ...


async def run_evaluation():
    with LogfireAPIClient(api_key='your-api-key') as client:
        dataset: Dataset[QuestionInput, AnswerOutput, None] = client.get_dataset(
            'qa-golden-set',
            input_type=QuestionInput,
            output_type=AnswerOutput,
        )
    report = await dataset.evaluate(my_qa_task)
    report.print()
```

`get_dataset` returns a typed `pydantic_evals.Dataset`; pass `custom_evaluator_types=[...]` if your cases carry custom evaluators, or omit the type arguments to get the raw pydantic-evals-compatible dict. See the [Datasets SDK](datasets-sdk.md) for the full API.

## The loop

With Logfire tracing on, every run appears on the [Experiments](review-experiments.md) page, which turns evals into a continuous loop: **observe** production in the live view, **curate** interesting traces into a dataset, **evaluate** with pydantic-evals, **analyze** and compare experiments, then **improve** and repeat.
