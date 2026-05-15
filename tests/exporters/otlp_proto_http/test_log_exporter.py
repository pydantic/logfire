from __future__ import annotations

import gzip
import importlib
import inspect
from collections.abc import Sequence
from typing import Any

import pytest
import requests
from opentelemetry._logs import LogRecord, SeverityNumber
from opentelemetry.exporter.otlp.proto.common._log_encoder import encode_logs
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk._logs import ReadableLogRecord
from opentelemetry.sdk._logs.export import LogRecordExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.util.instrumentation import InstrumentationScope
from requests import Response

from logfire._internal.exporters.otlp_proto_http import (
    LogfireOTLPLogExporter,
    LogfireOTLPMetricExporter,
    LogfireOTLPSpanExporter,
)
from logfire._internal.exporters.otlp_proto_http._log_exporter import (
    INTENTIONAL_OTEL_DEVIATIONS,
    OWNED_OTEL_ENCODING_DEPENDENCIES,
    UPSTREAM_OTEL_MODULE,
    UPSTREAM_OTEL_VERSION,
)


class RecordingSession(requests.Session):
    def __init__(self, response: Response | None = None) -> None:
        super().__init__()
        self.requests: list[dict[str, Any]] = []
        self.closed = False
        self.response = response if response is not None else Response()
        if response is None:
            self.response.status_code = 200

    def post(self, **kwargs: Any) -> Response:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.requests.append(kwargs)
        return self.response

    def close(self) -> None:
        self.closed = True
        super().close()


class FailingSession(requests.Session):
    def post(self, **kwargs: Any) -> Response:  # pyright: ignore[reportIncompatibleMethodOverride]
        raise requests.exceptions.ConnectionError('no connection')


@pytest.fixture
def log_batch() -> list[ReadableLogRecord]:
    return [
        ReadableLogRecord(
            LogRecord(
                body='hello from owned log exporter',
                severity_number=SeverityNumber.INFO,
                severity_text='INFO',
                attributes={'route': '/export'},
            ),
            Resource.create({'service.name': 'test-service'}),
            InstrumentationScope(__name__, '1.0.0'),
        )
    ]


def test_log_exporter_serializes_logs_with_owned_encoder_dependency(log_batch: Sequence[ReadableLogRecord]) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPLogExporter(
        endpoint='https://logfire.example/v1/logs',
        session=session,
        headers={'Authorization': 'pylf_v1_test'},
        compression=Compression.NoCompression,
    )

    assert exporter.export(log_batch) is LogRecordExportResult.SUCCESS

    assert session.requests[0]['data'] == encode_logs(log_batch).SerializeToString()


def test_log_exporter_posts_expected_request_metadata(log_batch: Sequence[ReadableLogRecord]) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPLogExporter(
        endpoint='https://logfire.example/v1/logs',
        session=session,
        headers={'User-Agent': 'logfire/test', 'Authorization': 'pylf_v1_test'},
        compression=Compression.Gzip,
        certificate_file='server.pem',
        client_certificate_file='client.pem',
        client_key_file='client-key.pem',
        timeout=12.5,
    )

    assert exporter.export(log_batch) is LogRecordExportResult.SUCCESS

    request = session.requests[0]
    assert request['url'] == 'https://logfire.example/v1/logs'
    assert gzip.decompress(request['data']) == encode_logs(log_batch).SerializeToString()
    assert request['verify'] == 'server.pem'
    assert request['timeout'] == 12.5
    assert request['cert'] == ('client.pem', 'client-key.pem')
    assert session.headers['User-Agent'] == 'logfire/test'
    assert session.headers['Authorization'] == 'pylf_v1_test'
    assert session.headers['Content-Type'] == 'application/x-protobuf'
    assert session.headers['Content-Encoding'] == 'gzip'


def test_log_exporter_maps_non_ok_response_to_failure(log_batch: Sequence[ReadableLogRecord]) -> None:
    response = Response()
    response.status_code = 400
    exporter = LogfireOTLPLogExporter(session=RecordingSession(response), compression=Compression.NoCompression)

    assert exporter.export(log_batch) is LogRecordExportResult.FAILURE


def test_log_exporter_leaves_request_exceptions_to_quiet_wrapper(log_batch: Sequence[ReadableLogRecord]) -> None:
    exporter = LogfireOTLPLogExporter(session=FailingSession(), compression=Compression.NoCompression)

    with pytest.raises(requests.exceptions.ConnectionError, match='no connection'):
        exporter.export(log_batch)


def test_log_exporter_shutdown_is_state_only_and_force_flush_is_noop(log_batch: Sequence[ReadableLogRecord]) -> None:
    session = RecordingSession()
    exporter = LogfireOTLPLogExporter(session=session)

    exporter.shutdown()

    assert session.closed is False
    assert exporter.export(log_batch) is LogRecordExportResult.FAILURE
    assert session.requests == []
    assert exporter.force_flush() is True


def test_log_exporter_declares_owned_compatibility_surface() -> None:
    assert UPSTREAM_OTEL_MODULE == 'opentelemetry.exporter.otlp.proto.http._log_exporter'
    assert UPSTREAM_OTEL_VERSION == '1.41.1'
    assert OWNED_OTEL_ENCODING_DEPENDENCIES == ('opentelemetry.exporter.otlp.proto.common._log_encoder.encode_logs',)
    assert 'No OpenTelemetry HTTP retry loop' in INTENTIONAL_OTEL_DEVIATIONS[0]


def test_log_exporter_does_not_copy_opentelemetry_retry_logic() -> None:
    source = inspect.getsource(LogfireOTLPLogExporter)

    assert '_MAX_RETRYS' not in source
    assert '_is_retryable' not in source
    assert 'ConnectionError' not in source


def test_log_exporter_encoder_incompatibility_fails_loudly(
    log_batch: Sequence[ReadableLogRecord], monkeypatch: pytest.MonkeyPatch
) -> None:
    def incompatible_encode_logs(batch: object) -> object:
        return object()

    log_exporter_module = importlib.import_module('logfire._internal.exporters.otlp_proto_http._log_exporter')
    monkeypatch.setattr(log_exporter_module, 'encode_logs', incompatible_encode_logs)
    exporter = LogfireOTLPLogExporter(session=RecordingSession())

    with pytest.raises(RuntimeError, match='log encoder API is incompatible'):
        exporter.export(log_batch)


def test_package_reexports_owned_exporters() -> None:
    assert LogfireOTLPSpanExporter.__name__ == 'LogfireOTLPSpanExporter'
    assert LogfireOTLPMetricExporter.__name__ == 'LogfireOTLPMetricExporter'
    assert LogfireOTLPLogExporter.__name__ == 'LogfireOTLPLogExporter'
