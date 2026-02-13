---
title: "Managed Datasets: Build and Manage Evaluation Test Cases"
description: "Create, manage, and export typed evaluation datasets in Pydantic Logfire. Integrate with pydantic-evals to run evaluations against your AI systems."
---

# Managed Datasets

Managed datasets let you build and maintain collections of test cases for evaluating your AI systems. You can create datasets through the Logfire web UI or programmatically via the SDK, then export them as [pydantic-evals](https://ai.pydantic.dev/evals/) `Dataset` objects to run evaluations.

!!! note "Relationship with Pydantic Evals"

    Managed datasets are the server-side complement to [pydantic-evals](https://ai.pydantic.dev/evals/) file-based datasets. While pydantic-evals stores datasets as local YAML files, managed datasets are stored in Logfire and can be created from production traces, edited collaboratively in the UI, and exported for evaluation. The SDK is designed so you can move seamlessly between the two.

## Why Managed Datasets?

When evaluating AI systems, you need test cases that reflect real-world usage. Managed datasets solve several problems:

- **Production-driven test cases**: Create test cases directly from production traces using the "Add to Dataset" action in Live View, so your evaluations reflect real user inputs.
- **Collaborative editing**: Team members can add, review, and refine test cases through the web UI without touching code.
- **Typed schemas**: Define input, output, and metadata schemas so that every case is validated, preventing malformed test data.
- **SDK integration**: Export datasets as typed `pydantic_evals.Dataset` objects and run evaluations with a single method call.

## Creating Datasets via the UI

### Navigate to Datasets

Open the **Datasets** page from the left-hand navigation in your project. This shows all datasets in the project along with their case counts and descriptions.

### Create a New Dataset

Click **New Dataset** and fill in:

- **Name**: A unique identifier for the dataset (e.g., `qa-golden-set`, `support-agent-regression`).
- **Description**: Optional text explaining what the dataset is for.
- **Input schema**: A JSON Schema defining the structure of case inputs.
- **Output schema**: A JSON Schema defining the structure of expected outputs.
- **Metadata schema**: A JSON Schema defining the structure of case metadata.

!!! tip "Schema generation from code"
    If you are using Python types (dataclasses, Pydantic models, etc.) for your schemas, it is easier to create the dataset via the SDK, which generates JSON schemas automatically from your type definitions. See [Creating Datasets via the SDK](#creating-datasets-via-the-sdk) below.

### Adding Cases Manually

Once a dataset exists, you can add cases through the UI by clicking **Add Case** and providing:

- **Name**: An optional label for the case (e.g., `capital-question`, `edge-case-empty-input`).
- **Inputs**: The case inputs, validated against the dataset's input schema.
- **Expected output**: The expected result, validated against the output schema.
- **Metadata**: Additional information for organizing or filtering cases.

### Adding Cases from Traces

You can create test cases directly from production data:

1. Open **Live View** and find a trace or span that represents a good test case.
2. Click the **Add to Dataset** button on the span.
3. Select the target dataset and review the extracted inputs and outputs.
4. Optionally edit the values before saving.

This preserves a link back to the source trace, so you always know where a test case came from.

## Creating Datasets via the SDK

The SDK provides a typed Python client for managing datasets programmatically. This is the recommended approach when you want to define schemas using Python types and automate dataset management.

### Installation

Install the Logfire SDK with the `datasets` extra:

```bash
pip install 'logfire[datasets]'
```

This installs `httpx` and `pydantic-evals` as additional dependencies.

### Creating a Client

```python
from logfire.datasets import LogfireDatasetsClient

client = LogfireDatasetsClient(api_key='your-api-key')
```

The client can also be used as a context manager to ensure the underlying HTTP connection is properly closed:

```python
with LogfireDatasetsClient(api_key='your-api-key') as client:
    ...
```

!!! note "API key scopes"
    The API key must have the `project:read_datasets` scope to read datasets, and `project:write_datasets` to create, update, or delete datasets and cases. You can create API keys with these scopes under **Settings > API Keys** in the Logfire UI.

The `base_url` is automatically inferred from the API key. You can override it if needed (e.g., for local development):

```python
client = LogfireDatasetsClient(
    api_key='your-api-key',
    base_url='http://localhost:8000',
)
```

An async client is also available:

```python
from logfire.datasets import AsyncLogfireDatasetsClient

async with AsyncLogfireDatasetsClient(api_key='your-api-key') as client:
    datasets = await client.list_datasets()
```

### Creating a Dataset with Typed Schemas

Define your input, output, and metadata types as dataclasses or Pydantic models, then pass them to `create_dataset`. The SDK automatically generates JSON schemas from the types:

```python
from dataclasses import dataclass

from logfire.datasets import LogfireDatasetsClient


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
    )
    print(f"Created dataset: {dataset['name']} (ID: {dataset['id']})")
```

All three type parameters are optional. You can create a dataset with just `input_type`, or with no types at all (in which case inputs and outputs are unvalidated JSON).

### Adding Cases

The SDK integrates directly with pydantic-evals `Case` objects. You can add a single case or multiple cases in bulk:

```python
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
)
```

!!! tip "Referencing datasets by name or ID"
    All dataset operations accept either the dataset's UUID or its name. Using the name (e.g., `'qa-golden-set'`) is more readable, while the UUID is guaranteed to be unique across renames.

You can also create cases using the lower-level `create_case` method, which accepts raw values instead of `Case` objects:

```python
client.create_case(
    'qa-golden-set',
    inputs=QuestionInput(question='What color is the sky?'),
    name='sky-color',
    expected_output=AnswerOutput(answer='Blue', confidence=0.95),
    metadata=CaseMetadata(category='science', difficulty='easy'),
)
```

### Listing and Retrieving Data

```python
# List all datasets in the project
datasets = client.list_datasets()
for ds in datasets:
    print(f"{ds['name']}: {ds['case_count']} cases")

# Get a specific dataset by name or ID
dataset_info = client.get_dataset('qa-golden-set')

# List all cases in a dataset
cases = client.list_cases('qa-golden-set')
for case in cases:
    print(f"  {case['name']}: {case['inputs']}")

# Get a specific case
case = client.get_case('qa-golden-set', case_id='some-case-uuid')
```

### Updating and Deleting

```python
# Update a dataset's metadata
client.update_dataset('qa-golden-set', description='Updated description')

# Update a specific case
client.update_case(
    'qa-golden-set',
    case_id='some-case-uuid',
    metadata=CaseMetadata(category='geography', difficulty='easy', reviewed=True),
)

# Delete a case
client.delete_case('qa-golden-set', case_id='some-case-uuid')

# Delete an entire dataset and all its cases
client.delete_dataset('qa-golden-set')
```

### Exporting to pydantic-evals Dataset

The `export_dataset` method fetches all cases and returns a typed `pydantic_evals.Dataset` that you can use directly for evaluation:

```python
from pydantic_evals import Dataset

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

## Running Evaluations with Managed Datasets

Once you have exported a dataset, use it with pydantic-evals to evaluate your AI system:

```python
from pydantic_evals import Dataset

from logfire.datasets import LogfireDatasetsClient


async def my_qa_task(inputs: QuestionInput) -> AnswerOutput:
    """The AI system under test."""
    # Your AI logic here — call an LLM, run an agent, etc.
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

With Logfire tracing enabled, the evaluation results appear automatically in the [Evals](evals.md) tab, where you can compare experiments and analyze performance over time.

This creates a workflow loop:

1. **Observe** production behavior in Live View.
2. **Curate** test cases by adding interesting traces to a managed dataset.
3. **Evaluate** your system against the dataset using pydantic-evals.
4. **Analyze** the results in the Logfire Evals tab.
5. **Improve** your system and repeat.

## SDK Reference

### LogfireDatasetsClient

| Method | Description |
|--------|-------------|
| `list_datasets()` | List all datasets in the project. |
| `get_dataset(id_or_name)` | Get a dataset by UUID or name. |
| `create_dataset(name, *, input_type, output_type, metadata_type, description, guidance)` | Create a new dataset. Types are converted to JSON schemas automatically. |
| `update_dataset(id_or_name, *, name, input_type, output_type, metadata_type, description)` | Update a dataset's metadata or schemas. |
| `delete_dataset(id_or_name)` | Delete a dataset and all its cases. |
| `list_cases(dataset_id_or_name)` | List all cases in a dataset. |
| `get_case(dataset_id_or_name, case_id)` | Get a specific case. |
| `add_case(dataset_id_or_name, case)` | Add a single `pydantic_evals.Case` to a dataset. |
| `add_cases(dataset_id_or_name, cases)` | Add multiple `pydantic_evals.Case` objects in bulk. |
| `create_case(dataset_id_or_name, inputs, *, name, expected_output, metadata, evaluators)` | Create a case from raw values. |
| `update_case(dataset_id_or_name, case_id, *, name, inputs, expected_output, metadata)` | Update an existing case. |
| `delete_case(dataset_id_or_name, case_id)` | Delete a case. |
| `export_dataset(id_or_name, input_type, output_type, metadata_type)` | Export as a typed `pydantic_evals.Dataset`. |
| `import_cases(dataset_id_or_name, cases)` | Bulk import cases (as `Case` objects or dicts). |

An async version, `AsyncLogfireDatasetsClient`, provides the same methods as async coroutines.

### Exceptions

| Exception | Description |
|-----------|-------------|
| `DatasetNotFoundError` | Raised when a dataset lookup by ID or name finds no match. |
| `CaseNotFoundError` | Raised when a case lookup finds no match. |
| `DatasetApiError` | Raised for other API errors. Contains `status_code` and `detail`. |
