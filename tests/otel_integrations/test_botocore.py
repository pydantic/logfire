from __future__ import annotations

import importlib
from typing import Any
from unittest import mock

import botocore.session
import pytest
from botocore.stub import Stubber
from inline_snapshot import snapshot
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span

import logfire
import logfire._internal.integrations.botocore
from logfire.testing import TestExporter


@pytest.fixture(autouse=True)
def uninstrument_after_test():
    yield
    instrumentor = BotocoreInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


def create_s3_client() -> Any:
    return botocore.session.get_session().create_client(  # pyright: ignore[reportUnknownMemberType]
        's3', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test'
    )


def stub_list_buckets(client: Any) -> Stubber:
    return Stubber(client)


def test_instrument_botocore_with_stubber(exporter: TestExporter) -> None:
    request_hook = mock.Mock()
    response_hook = mock.Mock()
    logfire.instrument_botocore(request_hook=request_hook, response_hook=response_hook)

    client = create_s3_client()
    with stub_list_buckets(client) as stubber:
        stubber.add_response(  # pyright: ignore[reportUnknownMemberType]
            'list_buckets', {'Buckets': [], 'Owner': {'DisplayName': 'test', 'ID': 'test'}}
        )
        with logfire.span('parent'):
            response = client.list_buckets()
    assert response['Buckets'] == []

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'S3.ListBuckets',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'rpc.system': 'aws-api',
                    'rpc.service': 'S3',
                    'rpc.method': 'ListBuckets',
                    'cloud.region': 'us-east-1',
                    'server.address': 's3.amazonaws.com',
                    'server.port': 443,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'S3.ListBuckets',
                },
            },
            {
                'name': 'parent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_botocore.py',
                    'code.function': 'test_instrument_botocore_with_stubber',
                    'code.lineno': 123,
                    'logfire.msg_template': 'parent',
                    'logfire.msg': 'parent',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    request_args = request_hook.call_args.args
    assert len(request_args) == 4
    assert isinstance(request_args[0], Span)
    assert request_args[1:] == ('s3', 'ListBuckets', {})

    response_args = response_hook.call_args.args
    assert len(response_args) == 4
    assert response_args[0] is request_args[0]
    assert response_args[1:] == ('s3', 'ListBuckets', response)


def test_provider_defaults_and_overrides() -> None:
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    with mock.patch('logfire._internal.integrations.botocore.BotocoreInstrumentor.instrument') as instrument:
        logfire.instrument_botocore()

    assert instrument.call_args.kwargs == {
        'request_hook': None,
        'response_hook': None,
        'tracer_provider': config.get_tracer_provider(),
        'meter_provider': config.get_meter_provider(),
        'logger_provider': config.get_logger_provider(),
    }

    overrides: dict[str, Any] = {
        'tracer_provider': object(),
        'meter_provider': object(),
        'logger_provider': object(),
    }
    with mock.patch('logfire._internal.integrations.botocore.BotocoreInstrumentor.instrument') as instrument:
        logfire.instrument_botocore(**overrides)

    assert instrument.call_args.kwargs == {'request_hook': None, 'response_hook': None, **overrides}


def test_tracer_provider_override_does_not_export_botocore_span(exporter: TestExporter) -> None:
    logfire.instrument_botocore(tracer_provider=TracerProvider())

    client = create_s3_client()
    with stub_list_buckets(client) as stubber:
        stubber.add_response('list_buckets', {'Buckets': []})  # pyright: ignore[reportUnknownMemberType]
        with logfire.span('parent'):
            client.list_buckets()

    assert [span['name'] for span in exporter.exported_spans_as_dict()] == ['parent']


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.botocore': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.botocore)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_botocore()` requires the `opentelemetry-instrumentation-botocore` package.
You can install this with:
    pip install 'logfire[botocore]'\
""")
