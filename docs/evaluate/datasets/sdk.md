---
title: "SDK Guide"
description: "Manage evaluation datasets programmatically with the Logfire Python SDK."
---

# SDK Guide

!!! note "Experimental SDK"

    The dataset management SDK is under `logfire.experimental.api_client`. The API may change in future releases.

The SDK provides a typed Python client for managing datasets programmatically. This is the recommended approach when you want to define datasets in code, publish them to hosted storage, and later fetch them back for evaluation. You can also manage datasets through the [Web UI](ui.md).

## Installation

Install the Logfire SDK with the `datasets` extra:

```bash
pip install 'logfire[datasets]'
```

This installs `httpx` and `pydantic-evals` as additional dependencies.

!!! note "Python 3.10+ Required"

    The datasets SDK requires Python 3.10 or later due to the `pydantic-evals` dependency.

## Creating a Client

```python skip-run="true" skip-reason="external-connection"
from logfire.experimental.api_client import LogfireAPIClient

client = LogfireAPIClient(api_key='your-api-key')
```

The client can also be used as a context manager to ensure the underlying HTTP connection is properly closed:

```python skip="true" skip-reason="external-connection"
with LogfireAPIClient(api_key='your-api-key') as client:
    ...
```

!!! note "API key scopes"
    The API key must have the `project:read_datasets` scope to read datasets, and `project:write_datasets` to create, update, or delete datasets and cases. You can create API keys with these scopes under **Settings > API Keys** in the Logfire UI.

The `base_url` is automatically inferred from the API key. You can override it if needed (e.g., for self-hosters):

```python skip="true" skip-reason="external-connection"
client = LogfireAPIClient(
    api_key='your-api-key',
    base_url='http://localhost:8000',
)
```

An async client is also available:

```python skip="true" skip-reason="external-connection"
from logfire.experimental.api_client import AsyncLogfireAPIClient

async with AsyncLogfireAPIClient(api_key='your-api-key') as client:
    datasets = await client.list_datasets()
```

## Publishing a Local Dataset to Hosted

Define your input, output, and metadata types as dataclasses or Pydantic models, build a local [`pydantic_evals.Dataset`][pydantic_evals.Dataset], and publish it with `push_dataset`. The SDK infers hosted JSON schemas from the dataset's generic types:

```python skip-run="true" skip-reason="external-connection"
from dataclasses import dataclass

from pydantic_evals import Case, Dataset

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


local_dataset = Dataset[QuestionInput, AnswerOutput, CaseMetadata](
    name='qa-golden-set',
    cases=[
        Case(
            name='capital-question',
            inputs=QuestionInput(question='What is the capital of France?'),
            expected_output=AnswerOutput(answer='Paris', confidence=0.99),
            metadata=CaseMetadata(category='geography', difficulty='easy'),
        ),
        Case(
            name='math-question',
            inputs=QuestionInput(question='What is 15 * 23?'),
            expected_output=AnswerOutput(answer='345', confidence=1.0),
            metadata=CaseMetadata(category='math', difficulty='easy'),
        ),
    ],
)


with LogfireAPIClient(api_key='your-api-key') as client:
    dataset = client.push_dataset(
        local_dataset,
        description='Golden test cases for the Q&A system',
        guidance='Each case should represent a realistic user question with a verified answer.',
        tags=['golden'],
    )
    print(f"Published dataset: {dataset['name']} (ID: {dataset['id']})")
```

`push_dataset(...)` is designed to be rerunnable:

- it uses `dataset.name` by default, or `name=` if you want a hosted override
- it creates the hosted dataset if it does not exist yet
- it updates the hosted dataset if one already exists with the same name
- it uploads all cases through the existing import/upsert API
- it uses `on_case_conflict='update'` by default, so named cases are updated on repeat pushes

!!! note "Dataset-level evaluators are not uploaded yet"

    `push_dataset(...)` uploads case-level evaluators with their cases, but it currently rejects dataset-level `evaluators` and `report_evaluators` because hosted datasets do not store them yet. Case-level evaluators are also not yet surfaced in the Logfire UI, so they round-trip through `get_dataset(..., custom_evaluator_types=[...])` but won't show up when browsing cases in the web app. We're working on this!

## Manual Dataset Management

If you need lower-level control, the SDK still exposes `create_dataset(...)`, `add_cases(...)`, `update_dataset(...)`, and the other primitives directly.

Use `create_dataset(...)` when you want to create the hosted dataset record separately from uploading cases:

```python skip="true" skip-reason="external-connection"
dataset = client.create_dataset(
    name='qa-golden-set',
    description='Golden test cases for the Q&A system',
    input_type=QuestionInput,
    output_type=AnswerOutput,
    metadata_type=CaseMetadata,
    guidance='Each case should represent a realistic user question with a verified answer.',
)
```

Then use `add_cases(...)` to upload one or more cases:

```python skip="true" skip-reason="external-connection"
client.add_cases(
    'qa-golden-set',
    cases=local_dataset.cases,
    tags=['batch-import'],
)
```

You can also pass plain dicts instead of `Case` objects:

```python skip="true" skip-reason="external-connection"
client.add_cases(
    'qa-golden-set',
    cases=[
        {'inputs': {'question': 'What color is the sky?'}, 'expected_output': {'answer': 'Blue'}},
    ],
)
```

!!! tip "Referencing datasets by name or ID"
    All dataset operations accept either the dataset's UUID or its name. Names are recommended for readability. If you need the UUID, it's returned in the `create_dataset()` response as `dataset['id']`.

## Listing Cases

```python skip="true" skip-reason="external-connection"
# List all cases in a dataset
cases = client.list_cases('qa-golden-set')
for case in cases:
    print(f"  {case['name']}: {case['inputs']}")

# Filter cases by tags
cases = client.list_cases('qa-golden-set', tags=['geography'])
for case in cases:
    print(f"  {case['name']}: {case['tags']}")

# Get a specific case
case = client.get_case('qa-golden-set', case_id='some-case-uuid')
```

## Listing and Retrieving Datasets

```python skip="true" skip-reason="external-connection"
# List all datasets in the project
datasets = client.list_datasets()
for ds in datasets:
    print(f"{ds['name']}: {ds['case_count']} cases")

# Retrieve only dataset-level metadata for a specific dataset by name or ID
dataset_info = client.get_dataset('qa-golden-set', include_cases=False)
```

To fetch the full hosted dataset back as a typed [`pydantic_evals.Dataset`][pydantic_evals.Dataset], see [Running Evaluations](evaluations.md).

## Updating and Deleting

```python skip="true" skip-reason="external-connection"
# Update a dataset's metadata
client.update_dataset('qa-golden-set', description='Updated description')

# Update a specific case (including tags)
client.update_case(
    'qa-golden-set',
    case_id='some-case-uuid',
    metadata=CaseMetadata(category='geography', difficulty='easy', reviewed=True),
    tags=['verified', 'geography'],
)

# Delete a case
client.delete_case('qa-golden-set', case_id='some-case-uuid')

# Delete an entire dataset and all its cases
client.delete_dataset('qa-golden-set')
```

## What's Next?

- **[Running Evaluations](evaluations.md)** --- Fetch your dataset and run evaluations with pydantic-evals.
- **[SDK Reference](../../reference/api/datasets.md)** --- Complete method signatures and exception reference.
- **[Web UI Guide](ui.md)** --- Manage datasets through the Logfire web interface.
