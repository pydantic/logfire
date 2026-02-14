---
title: "Running Evaluations"
description: "Export managed datasets and run evaluations with pydantic-evals."
---

# Running Evaluations

!!! warning "Experimental Feature"

    Managed datasets is an experimental feature currently gated behind a feature flag. Reach out to us on [Slack](https://logfire.pydantic.dev/docs/join-slack/) or [contact us](../../../help.md) to learn how to enable it for your project.

Once you have a managed dataset (created via the [Web UI](ui.md) or [SDK](sdk.md)), you can export it as a typed `pydantic_evals.Dataset` and use it to evaluate your AI system.

## Exporting to pydantic-evals Dataset

The `export_dataset` method fetches all cases and returns a typed `pydantic_evals.Dataset` that you can use directly for evaluation:

```python
from dataclasses import dataclass

from pydantic_evals import Dataset

from logfire.experimental.datasets import LogfireDatasetsClient


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


with LogfireDatasetsClient(api_key='your-api-key') as client:
    dataset: Dataset[QuestionInput, AnswerOutput, CaseMetadata] = client.export_dataset(
        'qa-golden-set',
        input_type=QuestionInput,
        output_type=AnswerOutput,
        metadata_type=CaseMetadata,
    )

print(f"Exported {len(dataset.cases)} cases")
print(f"First case input type: {type(dataset.cases[0].inputs).__name__}")
```

If you have custom evaluator types stored with your cases, pass them via `custom_evaluator_types` so they can be deserialized:

```python
dataset = client.export_dataset(
    'qa-golden-set',
    input_type=QuestionInput,
    output_type=AnswerOutput,
    custom_evaluator_types=[MyCustomEvaluator],
)
```

Without type arguments, `export_dataset` returns the raw dict in pydantic-evals compatible format:

```python
raw_data = client.export_dataset('qa-golden-set')
# raw_data is a dict with 'name', 'cases', etc.
```

## Running the Evaluation

Use the exported dataset with pydantic-evals to evaluate your AI system:

```python
from pydantic_evals import Dataset

from logfire.experimental.datasets import LogfireDatasetsClient


async def my_qa_task(inputs: QuestionInput) -> AnswerOutput:
    """The AI system under test."""
    # Your AI logic here --- call an LLM, run an agent, etc.
    ...


async def run_evaluation():
    with LogfireDatasetsClient(api_key='your-api-key') as client:
        # Export the dataset
        dataset: Dataset[QuestionInput, AnswerOutput, CaseMetadata] = client.export_dataset(
            'qa-golden-set',
            input_type=QuestionInput,
            output_type=AnswerOutput,
            metadata_type=CaseMetadata,
        )

    # Run the evaluation
    report = await dataset.evaluate(my_qa_task)
    report.print()
```

## Viewing Results in the Evals Tab

With Logfire tracing enabled, the evaluation results appear automatically in the [Evals](../evals.md) tab, where you can compare experiments and analyze performance over time.

## The Evaluation Workflow

This creates a continuous improvement loop:

1. **Observe** production behavior in Live View.
2. **Curate** test cases by adding interesting traces to a managed dataset.
3. **Evaluate** your system against the dataset using pydantic-evals.
4. **Analyze** the results in the Logfire Evals tab.
5. **Improve** your system and repeat.
