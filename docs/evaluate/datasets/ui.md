---
title: "Web UI Guide"
description: "Create and manage evaluation datasets through the Logfire web interface."
---

# Web UI Guide

This guide covers creating, editing, and managing datasets through the Logfire web interface. It's task-oriented: each section below is a specific lifecycle action (create, edit, add cases, export).

For a reference of the **Evals: Datasets & Experiments** page itself (list layout, experiment viewing, comparison workflow, trace integration), see [Evals: Datasets & Experiments](../../guides/web-ui/evals.md). For programmatic dataset access, see the [SDK Guide](sdk.md).

All tasks below start from the **Evals: Datasets & Experiments** page in the sidebar.

## Creating a New Dataset

Click **+ New dataset** in the top right and enter a name for your dataset. If you don't have any datasets yet, you can also type a name directly into the empty state and click **Create**.

Once created, you can edit the dataset to add a description and define schemas.

!!! tip "Schema generation from code"
    If you are using Python types (dataclasses, Pydantic models, etc.) for your schemas, it is easier to publish the dataset via the SDK, which generates hosted JSON schemas automatically from your type definitions. See [Publishing a Local Dataset to Hosted](sdk.md#publishing-a-local-dataset-to-hosted) in the SDK Guide.

??? example "SDK equivalent"

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


    local_dataset = Dataset[QuestionInput, AnswerOutput, None](
        name='qa-golden-set',
        cases=[
            Case(
                name='capital-question',
                inputs=QuestionInput(question='What is the capital of France?'),
                expected_output=AnswerOutput(answer='Paris', confidence=0.99),
            ),
        ],
    )


    with LogfireAPIClient(api_key='your-api-key') as client:
        dataset = client.push_dataset(
            local_dataset,
            description='Golden test cases for the Q&A system',
        )
    ```

    See the [SDK Guide](sdk.md) for full details on creating and managing datasets programmatically.

## Editing a Dataset

From the dataset detail page, click **Edit** to modify the dataset's configuration. The edit form has two sections:

- **General**: Name and description.
- **Schemas**: Define JSON schemas for inputs, expected outputs, and metadata. Use the **Generate schema** toggle to have Pydantic AI create schemas from a natural language description of your data shape.

## Managing Cases

From the dataset detail page, click the **Cases** tab to see all hosted cases for the dataset.

- **Add a case**: Click **+ Add case** to open the case editor. Fill in name, inputs, expected output, and metadata. When the dataset has schemas defined, fields render as labeled inputs with type information; otherwise you edit raw JSON.
- **Edit a case**: Click the pencil icon on any case row to open the editor pre-populated with that case's data. Make your changes and save.
- **Delete a case**: Click the trash icon on any case row and confirm deletion.

??? example "SDK equivalent"

    ```python skip="true" skip-reason="external-connection"
    from pydantic_evals import Case

    client.add_cases(
        'qa-golden-set',
        cases=[
            Case(
                name='capital-question',
                inputs=QuestionInput(question='What is the capital of France?'),
                expected_output=AnswerOutput(answer='Paris', confidence=0.99),
            ),
        ],
    )
    ```

    See [Manual Dataset Management](sdk.md#manual-dataset-management) in the SDK Guide for more options.

## Adding Cases from Traces

You can create test cases directly from production data:

1. Open **Live View** and find a trace or span that represents a good test case.
2. Click the **database icon** (+) on the span details panel.
3. Select an existing dataset or create a new one.
4. The AI can automatically extract inputs and outputs from the span data --- review and edit the extracted values before saving.

This preserves a link back to the source trace, so you always know where a test case came from.

??? example "SDK equivalent"

    You can use `add_cases` with plain dicts to programmatically create the same trace linkage:

    ```python skip="true" skip-reason="external-connection"
    client.add_cases(
        'qa-golden-set',
        cases=[
            {
                'inputs': {'question': 'What color is the sky?'},
                'name': 'sky-color',
                'expected_output': {'answer': 'Blue'},
                'source_trace_id': 'trace-uuid-from-live-view',
                'source_span_id': 'span-uuid-from-live-view',
            },
        ],
    )
    ```

    See [Manual Dataset Management](sdk.md#manual-dataset-management) in the SDK Guide for more details.

## Exporting a Dataset

From the dataset detail page, click **Export** to download the dataset in one of two formats:

- **JSON**: Raw JSON representation of all cases.
- **pydantic-evals**: A YAML format compatible with `pydantic_evals.Dataset.from_file()`.

## What's Next?

Once you have cases in a dataset, you can:

- Run evaluations against it — see [Running Evaluations](evaluations.md).
- View and compare experiment results — see [Evals: Datasets & Experiments](../../guides/web-ui/evals.md#viewing-experiments).
