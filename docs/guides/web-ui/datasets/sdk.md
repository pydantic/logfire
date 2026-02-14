---
title: "SDK Guide"
description: "Manage evaluation datasets programmatically with the Logfire Python SDK."
---

# SDK Guide

!!! warning "Experimental Feature"

    Managed datasets is an experimental feature currently gated behind a feature flag. Reach out to us on [Slack](https://logfire.pydantic.dev/docs/join-slack/) or [contact us](../../../help.md) to learn how to enable it for your project.

The SDK provides a typed Python client for managing datasets programmatically. This is the recommended approach when you want to define schemas using Python types and automate dataset management. You can also manage datasets through the [Web UI](ui.md).

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
from logfire.experimental.datasets import LogfireDatasetsClient

client = LogfireDatasetsClient(api_key='your-api-key')
```

The client can also be used as a context manager to ensure the underlying HTTP connection is properly closed:

```python skip="true" skip-reason="external-connection"
with LogfireDatasetsClient(api_key='your-api-key') as client:
    ...
```

!!! note "API key scopes"
    The API key must have the `project:read_datasets` scope to read datasets, and `project:write_datasets` to create, update, or delete datasets and cases. You can create API keys with these scopes under **Settings > API Keys** in the Logfire UI.

The `base_url` is automatically inferred from the API key. You can override it if needed (e.g., for local development):

```python skip="true" skip-reason="external-connection"
client = LogfireDatasetsClient(
    api_key='your-api-key',
    base_url='http://localhost:8000',
)
```

An async client is also available:

```python skip="true" skip-reason="external-connection"
from logfire.experimental.datasets import AsyncLogfireDatasetsClient

async with AsyncLogfireDatasetsClient(api_key='your-api-key') as client:
    datasets = await client.list_datasets()
```

## Creating a Dataset with Typed Schemas

Define your input, output, and metadata types as dataclasses or Pydantic models, then pass them to `create_dataset`. The SDK automatically generates JSON schemas from the types:

```python skip-run="true" skip-reason="external-connection"
from dataclasses import dataclass

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
    dataset = client.create_dataset(
        name='qa-golden-set',
        description='Golden test cases for the Q&A system',
        input_type=QuestionInput,
        output_type=AnswerOutput,
        metadata_type=CaseMetadata,
        guidance='Each case should represent a realistic user question with a verified answer.',
    )
    print(f"Created dataset: {dataset['name']} (ID: {dataset['id']})")
```

All three type parameters are optional. You can create a dataset with just `input_type`, or with no types at all (in which case inputs and outputs are unvalidated JSON).

The `guidance` parameter lets you provide free-text instructions describing how cases should be structured.

## Adding Cases

The SDK integrates directly with pydantic-evals `Case` objects. You can add a single case or multiple cases in bulk:

```python skip="true" skip-reason="external-connection"
from pydantic_evals import Case


# Add a single case
client.add_case(
    'qa-golden-set',
    Case(
        name='capital-question',
        inputs=QuestionInput(question='What is the capital of France?'),
        expected_output=AnswerOutput(answer='Paris', confidence=0.99),
        metadata=CaseMetadata(category='geography', difficulty='easy'),
    ),
    tags=['geography', 'easy'],
)

# Add multiple cases in bulk
client.add_cases(
    'qa-golden-set',
    cases=[
        Case(
            name='math-question',
            inputs=QuestionInput(question='What is 15 * 23?'),
            expected_output=AnswerOutput(answer='345', confidence=1.0),
            metadata=CaseMetadata(category='math', difficulty='easy'),
        ),
        Case(
            name='science-question',
            inputs=QuestionInput(question='What is the chemical symbol for gold?'),
            expected_output=AnswerOutput(answer='Au', confidence=0.98),
            metadata=CaseMetadata(category='science', difficulty='medium'),
        ),
    ],
    tags=['batch-import'],
)
```

!!! tip "Referencing datasets by name or ID"
    All dataset operations accept either the dataset's UUID or its name. Using the name (e.g., `'qa-golden-set'`) is more readable, while the UUID is guaranteed to be unique across renames.

You can also create cases using the lower-level `create_case` method, which accepts raw values instead of `Case` objects:

```python skip="true" skip-reason="external-connection"
client.create_case(
    'qa-golden-set',
    inputs=QuestionInput(question='What color is the sky?'),
    name='sky-color',
    expected_output=AnswerOutput(answer='Blue', confidence=0.95),
    metadata=CaseMetadata(category='science', difficulty='easy'),
    tags=['science', 'easy'],
)
```

The `create_case` method also accepts `source_trace_id` and `source_span_id` parameters to link a case back to the production trace it was created from --- the same linkage that the [Add to Dataset button](ui.md#adding-cases-from-traces) creates in the UI.

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

# Get a specific dataset by name or ID
dataset_info = client.get_dataset('qa-golden-set')
```

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

- **[Running Evaluations](evaluations.md)** --- Export your dataset and run evaluations with pydantic-evals.
- **[SDK Reference](sdk-reference.md)** --- Complete method signatures and exception reference.
- **[Web UI Guide](ui.md)** --- Manage datasets through the Logfire web interface.
