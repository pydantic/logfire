from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.context import Context
from opentelemetry.instrumentation.aws_lambda import _HANDLER  # type: ignore[import]
from opentelemetry.propagate import extract

import logfire
import logfire._internal.integrations.aws_lambda
from logfire._internal.integrations.aws_lambda import LambdaEvent
from logfire.propagate import get_context
from logfire.testing import TestExporter


def lambda_handler(event: Any, context: MockLambdaContext):
    pass


HANDLER_NAME = f'{__name__}.{lambda_handler.__name__}'


# The below mock is based on the following code:
# https://github.com/open-telemetry/opentelemetry-python-contrib/blob/ecf5529f99222e7d945eddcaa83acb8a47c9ba42/instrumentation/opentelemetry-instrumentation-aws-lambda/tests/test_aws_lambda_instrumentation_manual.py#L57-L66
@dataclass
class MockLambdaContext:
    aws_request_id: str
    invoked_function_arn: str


def event_context_extractor(lambda_event: LambdaEvent) -> Context:
    return extract(lambda_event['context'])


def test_instrument_aws_lambda(exporter: TestExporter) -> None:
    with logfire.span('span'):
        current_context = get_context()

    with mock.patch.dict('os.environ', {_HANDLER: HANDLER_NAME, 'AWS_LAMBDA_FUNCTION_NAME': HANDLER_NAME}):
        logfire.instrument_aws_lambda(lambda_handler, event_context_extractor=event_context_extractor)

        context = MockLambdaContext(
            aws_request_id='mock_aws_request_id',
            invoked_function_arn='arn:aws:lambda:us-east-1:123456:function:myfunction:myalias',
        )
        lambda_handler({'key': 'value', 'context': current_context}, context)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_aws_lambda.py',
                    'code.function': 'test_instrument_aws_lambda',
                    'code.lineno': 123,
                    'logfire.msg_template': 'span',
                    'logfire.msg': 'span',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': HANDLER_NAME,
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': True},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': HANDLER_NAME,
                    'cloud.resource_id': 'arn:aws:lambda:us-east-1:123456:function:myfunction:myalias',
                    'faas.invocation_id': 'mock_aws_request_id',
                    'cloud.account.id': '123456',
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aws_lambda': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aws_lambda)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aws_lambda()` requires the `opentelemetry-instrumentation-aws-lambda` package.
You can install this with:
    pip install 'logfire[aws-lambda]'\
""")
