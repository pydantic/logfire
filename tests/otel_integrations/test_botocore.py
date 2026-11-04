from __future__ import annotations

import sys
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import opentelemetry.instrumentation as instrumentation
import pytest
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.session import get_session
from botocore.stub import Stubber
from inline_snapshot import snapshot
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.sdk._logs.export import InMemoryLogRecordExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.metrics.export import ExponentialHistogram, Histogram, InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

import logfire
from logfire.testing import TestExporter

if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
    from mypy_boto3_s3 import S3Client


def test_instrument_botocore_uses_local_provider(config_kwargs: dict[str, Any]) -> None:
    exporter = TestExporter()
    kwargs: dict[str, Any] = {
        **config_kwargs,
        'additional_span_processors': [SimpleSpanProcessor(exporter)],
    }
    local = logfire.configure(local=True, **kwargs)
    local.instrument_botocore()
    try:
        client = cast(
            'S3Client',
            get_session().create_client(
                's3',
                endpoint_url='https://s3.amazonaws.com',
                region_name='us-east-1',
                aws_access_key_id='testing',
                aws_secret_access_key='testing',
                config=Config(signature_version=UNSIGNED),
            ),
        )
        with closing(client), Stubber(client) as stubber:
            stubber.add_response('list_buckets', {'Buckets': [], 'ResponseMetadata': {'HTTPStatusCode': 200}})
            stubber.add_client_error(
                'head_bucket',
                service_error_code='NoSuchBucket',
                service_message='Missing bucket',
                http_status_code=404,
                expected_params={'Bucket': 'missing'},
            )
            with local.span('AWS work'):
                client.list_buckets()
                with pytest.raises(ClientError):
                    client.head_bucket(Bucket='missing')
    finally:
        BotocoreInstrumentor().uninstrument()

    client_spans = [
        span
        for span in exporter.exported_spans
        if span.kind == SpanKind.CLIENT and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    ]
    assert [span.status.status_code for span in client_spans] == [StatusCode.UNSET, StatusCode.ERROR]
    assert exporter.exported_spans_as_dict(include_instrumentation_scope=True) == snapshot(
        [
            {
                'name': 'S3.ListBuckets',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.botocore',
                'attributes': {
                    'rpc.system': 'aws-api',
                    'rpc.service': 'S3',
                    'rpc.method': 'ListBuckets',
                    'cloud.region': 'us-east-1',
                    'server.address': 's3.amazonaws.com',
                    'server.port': 443,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'S3.ListBuckets',
                    'http.status_code': 200,
                },
            },
            {
                'name': 'S3.HeadBucket',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.botocore',
                'attributes': {
                    'rpc.system': 'aws-api',
                    'rpc.service': 'S3',
                    'rpc.method': 'HeadBucket',
                    'cloud.region': 'us-east-1',
                    'server.address': 's3.amazonaws.com',
                    'server.port': 443,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'S3.HeadBucket',
                    'http.status_code': 404,
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 5000000000,
                        'attributes': {
                            'exception.type': 'botocore.errorfactory.NoSuchBucket',
                            'exception.message': 'An error occurred (NoSuchBucket) when calling the HeadBucket operation: Missing bucket',
                            'exception.stacktrace': 'botocore.errorfactory.NoSuchBucket: An error occurred (NoSuchBucket) when calling the HeadBucket operation: Missing bucket',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            },
            {
                'name': 'AWS work',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 7000000000,
                'instrumentation_scope': 'logfire',
                'attributes': {
                    'code.filepath': 'test_botocore.py',
                    'code.function': 'test_instrument_botocore_uses_local_provider',
                    'code.lineno': 123,
                    'logfire.msg_template': 'AWS work',
                    'logfire.msg': 'AWS work',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_instrument_botocore_uses_local_bedrock_providers(
    config_kwargs: dict[str, Any], logs_exporter: InMemoryLogRecordExporter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT', 'true')
    reader = InMemoryMetricReader()
    local_exporter = InMemoryLogRecordExporter()
    kwargs: dict[str, Any] = {
        **config_kwargs,
        'metrics': logfire.MetricsOptions(additional_readers=[reader]),
        'scrubbing': logfire.ScrubbingOptions(extra_patterns=['content']),
        'advanced': replace(
            config_kwargs['advanced'], log_record_processors=[SimpleLogRecordProcessor(local_exporter)]
        ),
    }
    local = logfire.configure(local=True, **kwargs)
    local.instrument_botocore()
    try:
        client = cast(
            'BedrockRuntimeClient',
            get_session().create_client(
                'bedrock-runtime',
                region_name='us-east-1',
                aws_access_key_id='testing',
                aws_secret_access_key='testing',
            ),
        )
        with closing(client), Stubber(client) as stubber:
            stubber.add_response(
                'converse',
                {
                    'output': {'message': {'role': 'assistant', 'content': [{'text': 'Hello'}]}},
                    'stopReason': 'end_turn',
                    'usage': {'inputTokens': 10, 'outputTokens': 5, 'totalTokens': 15},
                    'metrics': {'latencyMs': 1},
                    'ResponseMetadata': {'HTTPStatusCode': 200},
                },
            )
            client.converse(
                modelId='anthropic.claude-3-haiku-20240307-v1:0',
                messages=[{'role': 'user', 'content': [{'text': 'Local question'}]}],
            )
    finally:
        BotocoreInstrumentor().uninstrument()

    data = reader.get_metrics_data()
    assert data is not None
    token_usage = next(
        metric
        for resource in data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
        if metric.name == 'gen_ai.client.token.usage'
    )
    assert isinstance(token_usage.data, (Histogram, ExponentialHistogram))
    assert {(point.attributes or {})['gen_ai.token.type']: point.sum for point in token_usage.data.data_points} == {
        'input': 10,
        'output': 5,
    }

    assert not logs_exporter.get_finished_logs()
    local_records = local_exporter.get_finished_logs()
    assert {record.log_record.event_name for record in local_records} == {'gen_ai.user.message', 'gen_ai.choice'}
    for record in local_records:
        assert 'logfire.scrubbed' in (record.log_record.attributes or {})
        body = str(record.log_record.body)
        assert 'Local question' not in body
        assert 'Hello' not in body


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.botocore': None}):
        sys.modules.pop('logfire._internal.integrations.botocore', None)
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_botocore()
        assert isinstance(exc_info.value.__context__, ModuleNotFoundError)


@pytest.mark.parametrize(
    'statement, error_type, missing_name',
    [
        ('from math import missing_botocore_symbol', ImportError, 'math'),
        ('import missing_botocore_transport', ModuleNotFoundError, 'missing_botocore_transport'),
    ],
)
def test_broken_opentelemetry_dependency(
    tmp_path: Path, statement: str, error_type: type[ImportError], missing_name: str
) -> None:
    (tmp_path / 'botocore.py').write_text(statement + '\n')
    with mock.patch.dict(sys.modules), mock.patch.object(instrumentation, '__path__', [str(tmp_path)]):
        sys.modules.pop('opentelemetry.instrumentation.botocore', None)
        sys.modules.pop('logfire._internal.integrations.botocore', None)
        with pytest.raises(error_type) as exc_info:
            logfire.instrument_botocore()
        assert exc_info.value.name == missing_name
