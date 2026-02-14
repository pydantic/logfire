"""Logfire Datasets SDK for managing typed datasets compatible with pydantic-evals.

This module provides sync and async clients for managing datasets that integrate
with pydantic-evals for AI evaluation workflows.

Example usage:
    ```python
    from dataclasses import dataclass
    from logfire.experimental.datasets import LogfireDatasetsClient


    @dataclass
    class MyInput:
        question: str
        context: str | None = None


    @dataclass
    class MyOutput:
        answer: str
        confidence: float


    with LogfireDatasetsClient(api_key='your-api-key') as client:
        # Create a typed dataset (generates JSON schemas from types)
        dataset_info = client.create_dataset(
            name='my-evaluation-dataset',
            input_type=MyInput,
            output_type=MyOutput,
            description='Test cases for my chatbot',
        )

        # Add typed cases
        client.create_case(
            dataset_info['id'],
            inputs=MyInput(question='What is 2+2?'),
            expected_output=MyOutput(answer='4', confidence=1.0),
        )

        # Export as pydantic-evals Dataset for evaluation
        from pydantic_evals import Dataset

        dataset: Dataset[MyInput, MyOutput, None] = client.export_dataset(
            'my-evaluation-dataset',
            input_type=MyInput,
            output_type=MyOutput,
        )

        # Run evaluations
        report = await dataset.evaluate(my_task)
    ```
"""

from logfire.experimental.datasets.client import (
    AsyncLogfireDatasetsClient,
    CaseNotFoundError,
    DatasetApiError,
    DatasetNotFoundError,
    LogfireDatasetsClient,
)

__all__ = [
    # Clients
    'LogfireDatasetsClient',
    'AsyncLogfireDatasetsClient',
    # Errors
    'DatasetNotFoundError',
    'CaseNotFoundError',
    'DatasetApiError',
]
