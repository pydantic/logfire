from __future__ import annotations

import sys
from contextlib import closing
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import ClientError
from botocore.session import get_session
from botocore.stub import Stubber
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import SpanKind, StatusCode

import logfire
from logfire.testing import TestExporter

if TYPE_CHECKING:
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

    spans = [
        span for span in exporter.exported_spans if (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    ]
    parent = next(span for span in spans if span.name == 'AWS work')
    clients = [span for span in spans if span.kind == SpanKind.CLIENT]
    assert [span.name for span in clients] == ['S3.ListBuckets', 'S3.HeadBucket']
    assert parent.context is not None
    for span in clients:
        assert span.context is not None
        assert span.parent == parent.context
        assert span.context.trace_id == parent.context.trace_id
        assert (span.attributes or {})['rpc.service'] == 'S3'
    assert clients[0].status.status_code != StatusCode.ERROR
    assert clients[1].status.status_code == StatusCode.ERROR


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.botocore': None}):
        sys.modules.pop('logfire._internal.integrations.botocore', None)
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_botocore()
        assert isinstance(exc_info.value.__context__, ModuleNotFoundError)
