from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.aws_lambda import _HANDLER  # type: ignore[import]

import logfire
import logfire._internal.integrations.pymongo
from logfire.testing import TestExporter


def lambda_handler(event: Any, context: MockLambdaContext):
    pass


# The below mock is based on the following code:
# https://github.com/open-telemetry/opentelemetry-python-contrib/blob/ecf5529f99222e7d945eddcaa83acb8a47c9ba42/instrumentation/opentelemetry-instrumentation-aws-lambda/tests/test_aws_lambda_instrumentation_manual.py#L57-L66
@dataclass
class MockLambdaContext:
    aws_request_id: str
    invoked_function_arn: str


# TODO real test
def test_instrument_aws_lambda(exporter: TestExporter) -> None:
    with mock.patch.dict('os.environ', {_HANDLER: 'tests.otel_integrations.test_aws_lambda.lambda_handler'}):
        logfire.instrument_aws_lambda()

        context = MockLambdaContext(
            aws_request_id='mock_aws_request_id',
            invoked_function_arn='arn:aws:lambda:us-east-1:123456:function:myfunction:myalias',
        )
        lambda_handler({'key': 'value'}, context)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'tests.otel_integrations.test_aws_lambda.lambda_handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'tests.otel_integrations.test_aws_lambda.lambda_handler',
                    'cloud.resource_id': 'arn:aws:lambda:us-east-1:123456:function:myfunction:myalias',
                    'faas.invocation_id': 'mock_aws_request_id',
                    'cloud.account.id': '123456',
                },
            }
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aws_lambda': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.pymongo)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aws_lambda()` requires the `opentelemetry-instrumentation-aws-lambda` package.
You can install this with:
    pip install 'logfire[aws-lambda]'\
""")
