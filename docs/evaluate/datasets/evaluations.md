---
title: "Running Evaluations"
description: "Run evaluations against local or hosted datasets with pydantic-evals."
---

# Running Evaluations

Evaluations in Logfire are powered by [pydantic-evals](https://pydantic.dev/docs/ai/evals/evals/). You have two equally supported options for where your test cases live:

- **Local datasets** --- defined in code (or loaded from a YAML file) as a [`pydantic_evals.Dataset`][pydantic_evals.Dataset]. No server round-trip required. This is the simplest way to get started and is all you need for many projects.
- **Hosted datasets** --- stored on Logfire, editable in the [Web UI](ui.md), and fetchable as a typed `Dataset`. Useful when you want to curate cases from production traces or collaborate with teammates.

Either way, once you have a `Dataset` in hand the evaluation step is identical, and results show up on the [Evals: Datasets & Experiments](../../guides/web-ui/evals.md) page as long as Logfire tracing is configured.

!!! note "Experimental SDK"

    The hosted dataset management SDK is under `logfire.experimental.api_client`. The API may change in future releases. Local datasets use the stable `pydantic-evals` API.

## Evaluating a Local Dataset

If your test cases live in code, you can run an evaluation without ever talking to the Logfire datasets API. Just build a `Dataset` and call `evaluate`:

```python skip-run="true" skip-reason="example-ai-task"
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

import logfire

# Configure Logfire so the evaluation shows up on the Evals: Datasets & Experiments page in the Logfire UI.
# Without this, the evaluation still runs but its results will not be sent to Logfire.
logfire.configure()
logfire.instrument_pydantic_ai()  # optional, traces the AI task under test


@dataclass
class QuestionInput:
    question: str
    context: str | None = None


@dataclass
class AnswerOutput:
    answer: str
    confidence: float


dataset = Dataset[QuestionInput, AnswerOutput, None](
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
    """The AI system under test."""
    ...


async def run_evaluation():
    report = await dataset.evaluate(my_qa_task)
    report.print()
```

!!! note "Pulling data from Logfire without pushing results back"

    Whether you *store* the dataset on Logfire and whether you *send* the evaluation results to Logfire are two independent choices. You can fetch a hosted dataset (see below) and then run a purely local evaluation that only prints to the console — just omit the `logfire.configure()` call. That said, we recommend configuring Logfire during evaluation so that runs show up alongside your dataset in the UI for comparison over time.

You can also load local datasets from YAML files --- see the [pydantic-evals documentation](https://pydantic.dev/docs/ai/evals/evals/) for details. With Logfire tracing enabled, runs against local datasets still appear on the [Evals: Datasets & Experiments](../../guides/web-ui/evals.md) page (as **Local** datasets --- see [Hosted vs Local Datasets](index.md#hosted-vs-local-datasets)).

## Evaluating a Hosted Dataset

If you'd rather manage cases on the server --- for example so teammates can edit them in the UI or so you can seed cases from production traces --- fetch a hosted dataset and use it the same way.

Hosted datasets are typically created in the [Web UI](ui.md) or published from code via [`push_dataset(...)`](../../python-sdk/evaluate/datasets.md#publishing-a-local-dataset-to-hosted).

### Getting a typed pydantic-evals Dataset

The `get_dataset` method fetches all hosted cases and returns a typed
[`pydantic_evals.Dataset`][pydantic_evals.Dataset] that you can use directly for evaluation:

```python skip-run="true" skip-reason="external-connection"
from dataclasses import dataclass

from pydantic_evals import Dataset

from logfire.experimental.api_client import LogfireAPIClient


@dataclass
class QuestionInput:
    question: str
    context: str | None = None


@dataclass
class AnswerOutput:
    answer: str
    confidence: float


@dataclass
class CaseMetadata:
    category: str
    difficulty: str
    reviewed: bool = False


with LogfireAPIClient(api_key='your-api-key') as client:
    dataset: Dataset[QuestionInput, AnswerOutput, CaseMetadata] = client.get_dataset(
        'qa-golden-set',
        input_type=QuestionInput,
        output_type=AnswerOutput,
        metadata_type=CaseMetadata,
    )

print(f'Fetched {len(dataset.cases)} cases')
print(f'First case input type: {type(dataset.cases[0].inputs).__name__}')
```

If you have custom evaluator types stored with your cases, pass them via `custom_evaluator_types` so they can be deserialized:

```python skip="true" skip-reason="external-connection"
dataset = client.get_dataset(
    'qa-golden-set',
    input_type=QuestionInput,
    output_type=AnswerOutput,
    custom_evaluator_types=[MyCustomEvaluator],
)
```

Without type arguments, `get_dataset` returns the raw dict in pydantic-evals-compatible format:

```python skip="true" skip-reason="external-connection"
raw_data = client.get_dataset('qa-golden-set')
# raw_data is a dict with 'name', 'cases', etc.
```

### Running the Evaluation

Once fetched, a hosted dataset is just a `pydantic_evals.Dataset` --- use it exactly like the local example above:

```python skip="true" skip-reason="external-connection"
from pydantic_evals import Dataset

import logfire
from logfire.experimental.api_client import LogfireAPIClient

# Send evaluation results to the Evals: Datasets & Experiments page in Logfire.
logfire.configure()
# You can instrument libraries here for richer information in the evaluation traces
# e.g., via `logfire.instrument_pydantic_ai()`


async def my_qa_task(inputs: QuestionInput) -> AnswerOutput:
    """The AI system under test."""
    # Your AI logic here --- call an LLM, run an agent, etc.
    ...


async def run_evaluation():
    with LogfireAPIClient(api_key='your-api-key') as client:
        # Get the dataset
        dataset: Dataset[QuestionInput, AnswerOutput, CaseMetadata] = client.get_dataset(
            'qa-golden-set',
            input_type=QuestionInput,
            output_type=AnswerOutput,
            metadata_type=CaseMetadata,
        )

    # Run the evaluation
    report = await dataset.evaluate(my_qa_task)
    report.print()
```

## Viewing Results on the Evals Page

With Logfire tracing enabled, the evaluation results appear automatically on the [Evals: Datasets & Experiments](../../guides/web-ui/evals.md) page, where you can compare experiments and analyze performance over time.

## The Evaluation Workflow

This creates a continuous improvement loop:

1. **Observe** production behavior in Live View.
2. **Curate** test cases by adding interesting traces to a dataset.
3. **Evaluate** your system against the dataset using pydantic-evals.
4. **Analyze** the results on the Logfire **Evals: Datasets & Experiments** page.
5. **Improve** your system and repeat.
