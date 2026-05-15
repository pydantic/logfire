from __future__ import annotations

import gzip
import inspect
from typing import Any

import pytest
import requests
from opentelemetry.exporter.otlp.proto.common.trace_encoder import encode_spans
from opentelemetry.exporter.otlp.proto.http import Compression
from opentelemetry.sdk.trace.export import SpanExportResult
from requests import Response

from logfire._internal.exporters.otlp_proto_http import trace_exporter
from logfire._internal.exporters.otlp_proto_http.trace_exporter import (
    INTENTIONAL_OTEL_DEVIATIONS,
    OWNED_OTEL_ENCODING_DEPENDENCIES,
    UPSTREAM_OTEL_MODULE,
    UPSTREAM_OTEL_VERSION,
    LogfireOTLPSpanExporter,
)
from tests.exporters.test_retry_fewer_spans import TEST_SPANS


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
    def __init__(self) -> None:
        super().__init__()

    def post(self, **kwargs: Any) -> Response:  # pyright: ignore[reportIncompatibleMethodOverride]
        raise requests.exceptions.ConnectionError('no connection')


def test_trace_exporter_serializes_spans_with_owned_encoder_dependency() -> None:
    session = RecordingSession()
    exporter = LogfireOTLPSpanExporter(
        endpoint='https://logfire.example/v1/traces',
        session=session,
        headers={'Authorization': 'pylf_v1_test'},
        compression=Compression.NoCompression,
    )

    assert exporter.export(TEST_SPANS) is SpanExportResult.SUCCESS

    assert session.requests[0]['data'] == encode_spans(TEST_SPANS).SerializePartialToString()


def test_trace_exporter_posts_expected_request_metadata() -> None:
    session = RecordingSession()
    exporter = LogfireOTLPSpanExporter(
        endpoint='https://logfire.example/v1/traces',
        session=session,
        headers={'User-Agent': 'logfire/test', 'Authorization': 'pylf_v1_test'},
        compression=Compression.Gzip,
        certificate_file='server.pem',
        client_certificate_file='client.pem',
        client_key_file='client-key.pem',
        timeout=12.5,
    )

    assert exporter.export(TEST_SPANS) is SpanExportResult.SUCCESS

    request = session.requests[0]
    assert request['url'] == 'https://logfire.example/v1/traces'
    assert gzip.decompress(request['data']) == encode_spans(TEST_SPANS).SerializePartialToString()
    assert request['verify'] == 'server.pem'
    assert request['timeout'] == 12.5
    assert request['cert'] == ('client.pem', 'client-key.pem')
    assert session.headers['User-Agent'] == 'logfire/test'
    assert session.headers['Authorization'] == 'pylf_v1_test'
    assert session.headers['Content-Type'] == 'application/x-protobuf'
    assert session.headers['Content-Encoding'] == 'gzip'


def test_trace_exporter_maps_non_ok_response_to_failure() -> None:
    response = Response()
    response.status_code = 400
    exporter = LogfireOTLPSpanExporter(session=RecordingSession(response), compression=Compression.NoCompression)

    assert exporter.export(TEST_SPANS) is SpanExportResult.FAILURE


def test_trace_exporter_leaves_request_exceptions_to_quiet_wrapper() -> None:
    exporter = LogfireOTLPSpanExporter(session=FailingSession(), compression=Compression.NoCompression)

    with pytest.raises(requests.exceptions.ConnectionError, match='no connection'):
        exporter.export(TEST_SPANS)


def test_trace_exporter_shutdown_is_state_only_and_force_flush_is_noop() -> None:
    session = RecordingSession()
    exporter = LogfireOTLPSpanExporter(session=session)

    exporter.shutdown()

    assert session.closed is False
    assert exporter.export(TEST_SPANS) is SpanExportResult.FAILURE
    assert session.requests == []
    assert exporter.force_flush() is True


def test_trace_exporter_declares_owned_compatibility_surface() -> None:
    assert UPSTREAM_OTEL_MODULE == 'opentelemetry.exporter.otlp.proto.http.trace_exporter'
    assert UPSTREAM_OTEL_VERSION == '1.41.1'
    assert OWNED_OTEL_ENCODING_DEPENDENCIES == ('opentelemetry.exporter.otlp.proto.common.trace_encoder.encode_spans',)
    assert 'No OpenTelemetry HTTP retry loop' in INTENTIONAL_OTEL_DEVIATIONS[0]


def test_trace_exporter_does_not_copy_opentelemetry_retry_logic() -> None:
    source = inspect.getsource(LogfireOTLPSpanExporter)

    assert '_MAX_RETRYS' not in source
    assert '_is_retryable' not in source
    assert 'ConnectionError' not in source


def test_trace_exporter_encoder_incompatibility_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    def incompatible_encode_spans(spans: object) -> object:
        return object()

    monkeypatch.setattr(trace_exporter, 'encode_spans', incompatible_encode_spans)
    exporter = LogfireOTLPSpanExporter(session=RecordingSession())

    with pytest.raises(RuntimeError, match='trace encoder API is incompatible'):
        exporter.export(TEST_SPANS)
