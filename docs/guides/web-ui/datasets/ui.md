---
title: "Web UI Guide"
description: "Create and manage evaluation datasets through the Logfire web interface."
---

# Web UI Guide

!!! warning "Experimental Feature"

    Managed datasets is an experimental feature currently gated behind a feature flag. Reach out to us on [Slack](https://logfire.pydantic.dev/docs/join-slack/) or [contact us](../../../help.md) to learn how to enable it for your project.

This guide covers creating and managing datasets through the Logfire web interface. For programmatic access, see the [SDK Guide](sdk.md).

## Navigate to Datasets

Open the **Datasets** page in your project. This shows all datasets in the project along with their case counts and descriptions.

## Creating a New Dataset

Click **New Dataset** and fill in:

- **Name**: A unique identifier for the dataset (e.g., `qa-golden-set`, `support-agent-regression`).
- **Description**: Optional text explaining what the dataset is for.
- **Input schema**: A JSON Schema defining the structure of case inputs.
- **Output schema**: A JSON Schema defining the structure of expected outputs.
- **Metadata schema**: A JSON Schema defining the structure of case metadata.
- **Guidance**: Optional free-text instructions that describe how cases should be structured, what makes a good test case, or any other context for contributors.
- **AI-managed guidance**: When enabled, the system can automatically refine the guidance based on the cases added to the dataset.

!!! tip "Schema generation from code"
    If you are using Python types (dataclasses, Pydantic models, etc.) for your schemas, it is easier to create the dataset via the SDK, which generates JSON schemas automatically from your type definitions. See [Creating a Dataset with Typed Schemas](sdk.md#creating-a-dataset-with-typed-schemas) in the SDK Guide.

??? example "SDK equivalent"

    ```python skip-run="true" skip-reason="external-connection"
    from dataclasses import dataclass

    from logfire.experimental.datasets import LogfireAPIClient


    @dataclass
    class QuestionInput:
        question: str
        context: str | None = None


    @dataclass
    class AnswerOutput:
        answer: str
        confidence: float


    with LogfireAPIClient(api_key='your-api-key') as client:
        dataset = client.create_dataset(
            name='qa-golden-set',
            description='Golden test cases for the Q&A system',
            input_type=QuestionInput,
            output_type=AnswerOutput,
            guidance='Each case should represent a realistic user question with a verified answer.',
        )
    ```

    See the [SDK Guide](sdk.md) for full details on creating and managing datasets programmatically.

## Adding Cases Manually

Once a dataset exists, you can add cases through the UI by clicking **Add Case** and providing:

- **Name**: An optional label for the case (e.g., `capital-question`, `edge-case-empty-input`).
- **Inputs**: The case inputs, validated against the dataset's input schema.
- **Expected output**: The expected result, validated against the output schema.
- **Metadata**: Additional information for organizing or filtering cases.
- **Tags**: Optional labels for organizing and filtering cases (e.g., `regression`, `edge-case`, `high-priority`).

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
        tags=['geography', 'easy'],
    )
    ```

    See [Adding Cases](sdk.md#adding-cases) in the SDK Guide for more options.

## Adding Cases from Traces

You can create test cases directly from production data:

1. Open **Live View** and find a trace or span that represents a good test case.
2. Click the **Add to Dataset** button on the span.
3. Select the target dataset and review the extracted inputs and outputs.
4. Optionally edit the values before saving.

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

    See [Adding Cases](sdk.md#adding-cases) in the SDK Guide for more details.

## Tags

Tags let you organize and categorize cases within a dataset. Each case can have zero or more tags --- short text labels like `regression`, `edge-case`, or `high-priority`.

### Adding Tags to Cases

You can add tags when creating a new case or by editing an existing case. Tags are free-form text, so you can use whatever labeling scheme fits your workflow.

### Filtering Cases by Tags

Use the tag filter on the dataset view to narrow the case list to only those matching specific tags. This is useful when you want to:

- Focus on a subset of cases for review (e.g., all `needs-review` cases).
- Run evaluations against a specific category (e.g., only `regression` cases).
- Track which cases have been verified (e.g., filter by `verified` vs. `unverified`).

??? example "SDK equivalent"

    You can filter cases by tags and manage tags via the SDK as well:

    ```python skip="true" skip-reason="external-connection"
    # List only cases with a specific tag
    regression_cases = client.list_cases('qa-golden-set', tags=['regression'])

    # Update tags on an existing case
    client.update_case(
        'qa-golden-set',
        case_id='some-case-uuid',
        tags=['verified', 'regression'],
    )
    ```

    See [Listing Cases](sdk.md#listing-cases) and [Updating and Deleting](sdk.md#updating-and-deleting) in the SDK Guide.

## What's Next?

Once you have cases in a dataset, you can export them and run evaluations. See [Running Evaluations](evaluations.md) to get started.
