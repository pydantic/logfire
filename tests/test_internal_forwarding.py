from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any, cast

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire._internal.forwarding as forwarding_module
from logfire._internal.forwarding import (
    OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
    OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
    ForwardingAdmissionResult,
    ForwardingContentType,
    ForwardingErrorResponse,
    ForwardingRequest,
    OTLPForwardingManager,
    OTLPForwardingPipeline,
    QueuedForwardingRequest,
    _extract_forwarding_representation_headers,  # pyright: ignore[reportPrivateUsage]
    _forwarding_user_agent,  # pyright: ignore[reportPrivateUsage]
    _normalize_forwarding_path,  # pyright: ignore[reportPrivateUsage]
    build_forwarding_headers,
    build_forwarding_request,
    build_partial_success_response,
    build_success_response,
    forwarding_timeout_for_path,
    parse_forwarding_content_type,
    response_content_type,
    response_message_for_path,
)
from logfire.version import VERSION


def test_forwarding_byte_limit_constants() -> None:
    assert OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES == 64 * 1024 * 1024
    assert OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES == 50 * 1024 * 1024


def test_forwarding_content_type_values() -> None:
    assert ForwardingContentType.PROTOBUF.value == 'application/x-protobuf'
    assert ForwardingContentType.JSON.value == 'application/json'


def test_forwarding_request_record() -> None:
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'trace-data',
        content_type=ForwardingContentType.PROTOBUF,
        content_type_header='application/x-protobuf',
        content_encoding='gzip',
        user_agent='browser-agent',
    )

    assert request.path == '/v1/traces'
    assert request.body == b'trace-data'
    assert request.content_type is ForwardingContentType.PROTOBUF
    assert request.content_type_header == 'application/x-protobuf'
    assert request.content_encoding == 'gzip'
    assert request.user_agent == 'browser-agent'
    with pytest.raises(FrozenInstanceError):
        setattr(request, 'body', b'other')


def test_forwarding_error_response_record() -> None:
    response = ForwardingErrorResponse(
        status_code=415,
        content_type='text/plain',
        content=b'Unsupported content type',
    )

    assert response.status_code == 415
    assert response.content_type == 'text/plain'
    assert response.content == b'Unsupported content type'
    with pytest.raises(FrozenInstanceError):
        setattr(response, 'status_code', 400)


def test_forwarding_admission_result_record() -> None:
    success = ForwardingAdmissionResult(response='success', message=None)
    partial_success = ForwardingAdmissionResult(response='partial_success', message='queue full')

    assert success.response == 'success'
    assert success.message is None
    assert partial_success.response == 'partial_success'
    assert partial_success.message == 'queue full'
    with pytest.raises(FrozenInstanceError):
        setattr(partial_success, 'message', 'closed')


def test_queued_forwarding_request_record() -> None:
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'log-data',
        content_type=ForwardingContentType.JSON,
        content_type_header='application/json',
        content_encoding=None,
        user_agent=None,
    )
    queued_request = QueuedForwardingRequest(request=request, tokens=('token-1', 'token-2'))

    assert queued_request.request is request
    assert queued_request.tokens == ('token-1', 'token-2')
    with pytest.raises(FrozenInstanceError):
        setattr(queued_request, 'tokens', ('token-3',))


@pytest.mark.parametrize(
    ('headers', 'expected'),
    [
        ({'Content-Type': 'application/x-protobuf'}, ForwardingContentType.PROTOBUF),
        ({'Content-Type': 'application/json'}, ForwardingContentType.JSON),
        ({'Content-Type': 'application/json; charset=utf-8'}, ForwardingContentType.JSON),
        ({'content-type': 'Application/JSON'}, ForwardingContentType.JSON),
        ({}, None),
        ({'Content-Type': ''}, None),
        ({'Content-Type': 'not a media type'}, None),
        ({'Content-Type': 'application/json; charset'}, None),
        ({'Content-Type': 'text/plain'}, None),
    ],
)
def test_parse_forwarding_content_type(headers: dict[str, str], expected: ForwardingContentType | None) -> None:
    assert parse_forwarding_content_type(headers) is expected


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/v1/traces', '/v1/traces'),
        ('/v1/logs', '/v1/logs'),
        ('/v1/metrics', '/v1/metrics'),
        ('v1/traces', '/v1/traces'),
    ],
)
def test_normalize_forwarding_path_valid(path: str, expected: str) -> None:
    assert _normalize_forwarding_path(path) == expected


@pytest.mark.parametrize(
    'path',
    [
        '/invalid',
        '/v1/traces/../secret',
        '/v1/traces/%2e%2e/secret',
        'https://example.com/v1/traces',
        '/v1/traces?foo=bar',
        '/v1/traces#fragment',
    ],
)
def test_normalize_forwarding_path_rejections(path: str) -> None:
    response = _normalize_forwarding_path(path)

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400
    assert response.content_type == 'text/plain'
    assert response.content == b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics'


def test_extract_forwarding_representation_headers() -> None:
    headers = {
        'content-type': 'application/json; charset=utf-8',
        'CONTENT-ENCODING': 'gzip',
        'User-Agent': 'browser-agent',
        'Authorization': 'client-token',
        'Cookie': 'session=secret',
        'Host': 'example.com',
        'X-Api-Key': 'secret',
    }

    content_type, content_encoding, user_agent = _extract_forwarding_representation_headers(headers)

    assert content_type == 'application/json; charset=utf-8'
    assert content_encoding == 'gzip'
    assert user_agent == 'browser-agent'


def test_extract_forwarding_representation_headers_missing_optional_values() -> None:
    content_type, content_encoding, user_agent = _extract_forwarding_representation_headers(
        {'Content-Type': 'application/x-protobuf'}
    )

    assert content_type == 'application/x-protobuf'
    assert content_encoding is None
    assert user_agent is None


def test_build_forwarding_request_valid_protobuf() -> None:
    request = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf', 'Content-Encoding': 'gzip', 'User-Agent': 'browser'},
        body=b'trace-data',
    )

    assert isinstance(request, ForwardingRequest)
    assert request.path == '/v1/traces'
    assert request.body == b'trace-data'
    assert request.content_type is ForwardingContentType.PROTOBUF
    assert request.content_type_header == 'application/x-protobuf'
    assert request.content_encoding == 'gzip'
    assert request.user_agent == 'browser'


def test_build_forwarding_request_valid_json_with_parameters() -> None:
    request = build_forwarding_request(
        path='/v1/logs',
        headers={'Content-Type': 'application/json; charset=utf-8'},
        body=b'{"resourceLogs":[]}',
    )

    assert isinstance(request, ForwardingRequest)
    assert request.path == '/v1/logs'
    assert request.body == b'{"resourceLogs":[]}'
    assert request.content_type is ForwardingContentType.JSON
    assert request.content_type_header == 'application/json; charset=utf-8'
    assert request.content_encoding is None
    assert request.user_agent is None


def test_build_forwarding_request_none_body_normalizes_to_empty_bytes() -> None:
    request = build_forwarding_request(
        path='/v1/metrics',
        headers={'Content-Type': 'application/x-protobuf'},
        body=None,
    )

    assert isinstance(request, ForwardingRequest)
    assert request.body == b''


@pytest.mark.parametrize(
    ('body', 'max_body_size'),
    [
        (b'12345', 4),
        (b'12345', 3),
    ],
)
def test_build_forwarding_request_oversized_body(body: bytes, max_body_size: int) -> None:
    response = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=body,
        max_body_size=max_body_size,
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 413
    assert response.content_type == 'text/plain'
    assert response.content == b'Payload too large'


def test_build_forwarding_request_custom_max_body_size_allows_body_at_limit() -> None:
    request = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'12345',
        max_body_size=5,
    )

    assert isinstance(request, ForwardingRequest)
    assert request.body == b'12345'


@pytest.mark.parametrize(
    'headers',
    [
        {},
        {'Content-Type': 'text/plain'},
    ],
)
def test_build_forwarding_request_unsupported_content_type(headers: dict[str, str]) -> None:
    response = build_forwarding_request(path='/v1/traces', headers=headers, body=b'')

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 415
    assert response.content_type == 'text/plain'
    assert response.content == b'Unsupported content type'


def test_build_forwarding_request_invalid_path() -> None:
    response = build_forwarding_request(
        path='/invalid',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ('content_type', 'expected'),
    [
        (ForwardingContentType.PROTOBUF, 'application/x-protobuf'),
        (ForwardingContentType.JSON, 'application/json'),
    ],
)
def test_response_content_type(content_type: ForwardingContentType, expected: str) -> None:
    assert response_content_type(content_type) == expected


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/v1/traces', ExportTraceServiceResponse),
        ('/v1/logs', ExportLogsServiceResponse),
        ('/v1/metrics', ExportMetricsServiceResponse),
    ],
)
def test_response_message_for_path(path: str, expected: type[object]) -> None:
    assert response_message_for_path(path) is expected  # type: ignore[arg-type]


def test_build_success_response_protobuf() -> None:
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'trace-data',
        content_type=ForwardingContentType.PROTOBUF,
        content_type_header='application/x-protobuf',
        content_encoding=None,
        user_agent=None,
    )

    response = build_success_response(request)

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/x-protobuf'}
    assert response.content == ExportTraceServiceResponse().SerializeToString()


def test_build_success_response_json() -> None:
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'{}',
        content_type=ForwardingContentType.JSON,
        content_type_header='application/json; charset=utf-8',
        content_encoding=None,
        user_agent=None,
    )

    response = build_success_response(request)

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert response.content == b'{}'


@pytest.mark.parametrize(
    ('path', 'rejected_field'),
    [
        ('/v1/traces', 'rejectedSpans'),
        ('/v1/logs', 'rejectedLogRecords'),
        ('/v1/metrics', 'rejectedDataPoints'),
    ],
)
def test_build_partial_success_response_json(path: str, rejected_field: str) -> None:
    request = ForwardingRequest(
        path=path,  # type: ignore[arg-type]
        body=b'{}',
        content_type=ForwardingContentType.JSON,
        content_type_header='application/json',
        content_encoding=None,
        user_agent=None,
    )

    response = build_partial_success_response(request, message='queue full')

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert json.loads(response.content) == {
        'partialSuccess': {
            'errorMessage': 'queue full',
            rejected_field: '0',
        }
    }


@pytest.mark.parametrize(
    ('path', 'message_cls', 'rejected_attr'),
    [
        ('/v1/traces', ExportTraceServiceResponse, 'rejected_spans'),
        ('/v1/logs', ExportLogsServiceResponse, 'rejected_log_records'),
        ('/v1/metrics', ExportMetricsServiceResponse, 'rejected_data_points'),
    ],
)
def test_build_partial_success_response_protobuf(path: str, message_cls: type[object], rejected_attr: str) -> None:
    request = ForwardingRequest(
        path=path,  # type: ignore[arg-type]
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        content_type_header='application/x-protobuf',
        content_encoding=None,
        user_agent=None,
    )

    response = build_partial_success_response(request, message='closed')
    message = message_cls()
    message.ParseFromString(response.content)  # type: ignore[attr-defined]

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/x-protobuf'}
    assert message.partial_success.error_message == 'closed'  # type: ignore[attr-defined]
    assert getattr(message.partial_success, rejected_attr) == 0  # type: ignore[attr-defined]


def test_forwarding_user_agent_without_inbound_user_agent() -> None:
    assert _forwarding_user_agent(None) == f'logfire-proxy/{VERSION}'


def test_forwarding_user_agent_with_inbound_user_agent() -> None:
    assert _forwarding_user_agent('browser-agent') == f'logfire-proxy/{VERSION} browser-agent'


def test_build_forwarding_headers_preserves_representation_and_injects_token() -> None:
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'data',
        content_type=ForwardingContentType.JSON,
        content_type_header='application/json; charset=utf-8',
        content_encoding='gzip',
        user_agent='browser-agent',
    )

    headers = build_forwarding_headers(request, token='server-token')

    assert headers == {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Encoding': 'gzip',
        'User-Agent': f'logfire-proxy/{VERSION} browser-agent',
        'Authorization': 'server-token',
    }


def test_build_forwarding_headers_without_optional_content_encoding_or_user_agent() -> None:
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        content_type_header='application/x-protobuf',
        content_encoding=None,
        user_agent=None,
    )

    headers = build_forwarding_headers(request, token='other-token')

    assert headers == {
        'Content-Type': 'application/x-protobuf',
        'User-Agent': f'logfire-proxy/{VERSION}',
        'Authorization': 'other-token',
    }
    assert 'Cookie' not in headers
    assert 'Host' not in headers


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/v1/traces', 10.0),
        ('/v1/logs', 10.0),
        ('/v1/metrics', 10.0),
    ],
)
def test_forwarding_timeout_for_path_defaults(monkeypatch: pytest.MonkeyPatch, path: str, expected: float) -> None:
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TIMEOUT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TRACES_TIMEOUT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_LOGS_TIMEOUT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_METRICS_TIMEOUT', raising=False)

    assert forwarding_timeout_for_path(path) == expected  # type: ignore[arg-type]


def test_forwarding_timeout_for_path_generic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TRACES_TIMEOUT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_LOGS_TIMEOUT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_METRICS_TIMEOUT', raising=False)
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TIMEOUT', '12.5')

    assert forwarding_timeout_for_path('/v1/traces') == 12.5
    assert forwarding_timeout_for_path('/v1/logs') == 12.5
    assert forwarding_timeout_for_path('/v1/metrics') == 12.5


@pytest.mark.parametrize(
    ('path', 'env_var'),
    [
        ('/v1/traces', 'OTEL_EXPORTER_OTLP_TRACES_TIMEOUT'),
        ('/v1/logs', 'OTEL_EXPORTER_OTLP_LOGS_TIMEOUT'),
        ('/v1/metrics', 'OTEL_EXPORTER_OTLP_METRICS_TIMEOUT'),
    ],
)
def test_forwarding_timeout_for_path_signal_specific_override(
    monkeypatch: pytest.MonkeyPatch, path: str, env_var: str
) -> None:
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TIMEOUT', '12.5')
    monkeypatch.setenv(env_var, '3.25')

    assert forwarding_timeout_for_path(path) == 3.25  # type: ignore[arg-type]


def test_forwarding_pipeline_initial_state() -> None:
    session = object()
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=123,
    )

    assert pipeline.base_url == 'https://example.com'
    assert pipeline.session is session
    assert pipeline.max_queued_body_bytes == 123
    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.active_send_count == 0
    assert pipeline.worker is None
    assert pipeline.closed is False
    assert pipeline.condition is not None


def _make_queued_forwarding_request(body: bytes, tokens: tuple[str, ...] = ('token',)) -> QueuedForwardingRequest:
    return QueuedForwardingRequest(
        request=ForwardingRequest(
            path='/v1/traces',
            body=body,
            content_type=ForwardingContentType.PROTOBUF,
            content_type_header='application/x-protobuf',
            content_encoding=None,
            user_agent=None,
        ),
        tokens=tokens,
    )


def test_forwarding_pipeline_enqueue_accepts_and_accounts_bytes() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=10)
    queued_request = _make_queued_forwarding_request(b'12345')

    assert pipeline.enqueue(queued_request) is True
    pipeline.started.wait(timeout=5)
    assert list(pipeline.queue) == [queued_request]
    assert pipeline.queued_body_bytes == 5
    assert pipeline.worker is not None
    pipeline.stop()


def test_forwarding_pipeline_enqueue_counts_multiple_tokens_once() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=10)
    queued_request = _make_queued_forwarding_request(b'12345', tokens=('token-1', 'token-2'))

    assert pipeline.enqueue(queued_request) is True
    assert pipeline.queued_body_bytes == 5
    pipeline.stop()


def test_forwarding_pipeline_enqueue_rejects_when_queue_full() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=4)
    queued_request = _make_queued_forwarding_request(b'12345')

    assert pipeline.enqueue(queued_request) is False
    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0


def test_forwarding_pipeline_enqueue_rejects_when_closed() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=10)
    pipeline.closed = True
    queued_request = _make_queued_forwarding_request(b'12345')

    assert pipeline.enqueue(queued_request) is False
    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0


class BlockingRunForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self, *, max_queued_body_bytes: int = 100) -> None:
        super().__init__(
            base_url='https://example.com',
            session=object(),  # type: ignore[arg-type]
            max_queued_body_bytes=max_queued_body_bytes,
        )
        self.started = Event()
        self.release = Event()

    def _run(self) -> None:
        self.started.set()
        self.release.wait(timeout=5)

    def stop(self) -> None:
        self.release.set()
        if self.worker is not None:
            self.worker.join(timeout=5)


def test_forwarding_pipeline_enqueue_starts_non_daemon_worker() -> None:
    pipeline = BlockingRunForwardingPipeline()

    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True

    assert pipeline.worker is not None
    assert pipeline.worker.daemon is False
    pipeline.stop()


def test_forwarding_pipeline_enqueue_does_not_start_duplicate_live_worker() -> None:
    pipeline = BlockingRunForwardingPipeline()

    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    first_worker = pipeline.worker
    assert pipeline.enqueue(_make_queued_forwarding_request(b'two')) is True

    assert pipeline.worker is first_worker
    pipeline.stop()


def test_forwarding_pipeline_rejected_enqueue_does_not_start_worker() -> None:
    full_pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=1)
    closed_pipeline = BlockingRunForwardingPipeline()
    closed_pipeline.closed = True

    assert full_pipeline.enqueue(_make_queued_forwarding_request(b'too-large')) is False
    assert closed_pipeline.enqueue(_make_queued_forwarding_request(b'one')) is False

    assert full_pipeline.worker is None
    assert closed_pipeline.worker is None


class BlockingSendForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self) -> None:
        super().__init__(
            base_url='https://example.com',
            session=object(),  # type: ignore[arg-type]
            max_queued_body_bytes=100,
        )
        self.started = Event()
        self.release = Event()

    def _send(self, queued_request: QueuedForwardingRequest) -> None:
        self.started.set()
        self.release.wait(timeout=5)


def _wait_for_no_live_worker(pipeline: OTLPForwardingPipeline) -> None:
    with pipeline.condition:
        assert pipeline.condition.wait_for(
            lambda: pipeline.worker is None or not pipeline.worker.is_alive(),
            timeout=5,
        )


def test_forwarding_pipeline_worker_state_reusable_after_drain() -> None:
    pipeline = BlockingSendForwardingPipeline()

    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    first_worker = pipeline.worker
    assert first_worker is not None
    assert first_worker.daemon is False

    pipeline.release.set()
    _wait_for_no_live_worker(pipeline)
    pipeline.started.clear()
    pipeline.release.clear()

    assert pipeline.enqueue(_make_queued_forwarding_request(b'two')) is True
    assert pipeline.started.wait(timeout=5) is True
    second_worker = pipeline.worker

    assert second_worker is not None
    assert second_worker is not first_worker
    assert second_worker.daemon is False
    pipeline.release.set()
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_worker_exit_notifies_waiters() -> None:
    pipeline = BlockingSendForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    waiter_returned = Event()

    def wait_for_worker_exit() -> None:
        with pipeline.condition:
            if pipeline.condition.wait_for(lambda: pipeline.worker is None, timeout=5):
                waiter_returned.set()

    waiter = Thread(target=wait_for_worker_exit)
    waiter.start()
    pipeline.release.set()
    waiter.join(timeout=1)

    assert waiter_returned.is_set()
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_force_flush_success_waits_for_active_send() -> None:
    pipeline = BlockingSendForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    flush_result: list[bool] = []

    flush_thread = Thread(target=lambda: flush_result.append(pipeline.force_flush(5000)))
    flush_thread.start()
    pipeline.release.set()
    flush_thread.join(timeout=5)

    assert flush_result == [True]
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_force_flush_times_out_with_queued_work() -> None:
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=object(),  # type: ignore[arg-type]
        max_queued_body_bytes=100,
    )
    queued_request = _make_queued_forwarding_request(b'queued')
    with pipeline.condition:
        pipeline.queue.append(queued_request)
        pipeline.queued_body_bytes = len(queued_request.request.body)

    assert pipeline.force_flush(1) is False


def test_forwarding_pipeline_force_flush_times_out_with_active_send() -> None:
    pipeline = BlockingSendForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True

    assert pipeline.force_flush(1) is False

    pipeline.release.set()
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_closes_admission_and_idle_session() -> None:
    session = FakeForwardingSession()
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=100,
    )

    assert pipeline.shutdown(1000) is True

    assert pipeline.closed is True
    assert pipeline.worker is None
    assert session.close_count == 1
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is False


def test_forwarding_pipeline_shutdown_no_queued_work_is_idempotent() -> None:
    session = FakeForwardingSession()
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=100,
    )

    assert pipeline.shutdown(1000) is True
    assert pipeline.shutdown(1000) is True

    assert session.close_count == 1
    assert pipeline.worker is None


class FakeForwardingSession:
    def __init__(self, *, fail_tokens: set[str] | None = None) -> None:
        self.fail_tokens = fail_tokens or set()
        self.calls: list[dict[str, Any]] = []
        self.close_count = 0

    def post(self, url: str, data: bytes, **kwargs: Any) -> object:
        self.calls.append({'url': url, 'data': data, **kwargs})
        headers = kwargs.get('headers')
        authorization = cast(dict[str, str], headers).get('Authorization') if isinstance(headers, dict) else None
        if authorization in self.fail_tokens:
            raise RuntimeError('send failed')
        return object()

    def close(self) -> None:
        self.close_count += 1


class BlockingShutdownForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self) -> None:
        self.fake_session = FakeForwardingSession()
        super().__init__(
            base_url='https://example.com',
            session=self.fake_session,  # type: ignore[arg-type]
            max_queued_body_bytes=100,
        )
        self.started = Event()
        self.release = Event()

    def _send(self, queued_request: QueuedForwardingRequest) -> None:
        self.started.set()
        self.release.wait(timeout=5)


def test_forwarding_pipeline_shutdown_drains_queued_work() -> None:
    pipeline = BlockingShutdownForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    shutdown_result: list[bool] = []

    shutdown_thread = Thread(target=lambda: shutdown_result.append(pipeline.shutdown(5000)))
    shutdown_thread.start()
    with pipeline.condition:
        assert pipeline.condition.wait_for(lambda: pipeline.closed, timeout=5)
    assert pipeline.enqueue(_make_queued_forwarding_request(b'two')) is False
    pipeline.release.set()
    shutdown_thread.join(timeout=5)

    assert shutdown_result == [True]
    assert pipeline.closed is True
    assert pipeline.queued_body_bytes == 0
    assert list(pipeline.queue) == []
    assert pipeline.fake_session.close_count == 1
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_timeout_drops_queued_work_after_active_send() -> None:
    pipeline = BlockingShutdownForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    assert pipeline.enqueue(_make_queued_forwarding_request(b'two')) is True
    shutdown_result: list[bool] = []

    shutdown_thread = Thread(target=lambda: shutdown_result.append(pipeline.shutdown(1)))
    shutdown_thread.start()
    with pipeline.condition:
        assert pipeline.condition.wait_for(lambda: pipeline.queued_body_bytes == 0, timeout=5)
    assert shutdown_thread.is_alive()
    pipeline.release.set()
    shutdown_thread.join(timeout=5)

    assert shutdown_result == [False]
    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.fake_session.close_count == 1
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_waits_for_active_send_after_timeout() -> None:
    pipeline = BlockingShutdownForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    shutdown_result: list[bool] = []

    shutdown_thread = Thread(target=lambda: shutdown_result.append(pipeline.shutdown(1)))
    shutdown_thread.start()
    with pipeline.condition:
        assert pipeline.condition.wait_for(lambda: pipeline.closed, timeout=5)
    shutdown_thread.join(timeout=0.05)

    assert shutdown_thread.is_alive()
    assert pipeline.fake_session.close_count == 0

    pipeline.release.set()
    shutdown_thread.join(timeout=5)

    assert shutdown_result == [True]
    assert pipeline.fake_session.close_count == 1
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_without_drain_drops_queued_work_and_waits_for_active_send() -> None:
    pipeline = BlockingShutdownForwardingPipeline()
    assert pipeline.enqueue(_make_queued_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    assert pipeline.enqueue(_make_queued_forwarding_request(b'two')) is True
    shutdown_result: list[bool] = []

    shutdown_thread = Thread(target=lambda: shutdown_result.append(pipeline.shutdown(1, drain_queued=False)))
    shutdown_thread.start()
    with pipeline.condition:
        assert pipeline.condition.wait_for(lambda: pipeline.queued_body_bytes == 0, timeout=5)

    assert shutdown_thread.is_alive()
    assert pipeline.fake_session.close_count == 0

    pipeline.release.set()
    shutdown_thread.join(timeout=5)

    assert shutdown_result == [True]
    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.fake_session.close_count == 1
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_send_fans_out_to_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TRACES_TIMEOUT', '7.5')
    session = FakeForwardingSession()
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com/base/',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=10,
    )
    queued_request = _make_queued_forwarding_request(b'payload', tokens=('token-1', 'token-2'))

    pipeline._send(queued_request)  # pyright: ignore[reportPrivateUsage]

    assert session.calls == [
        {
            'url': 'https://example.com/base/v1/traces',
            'data': b'payload',
            'headers': {
                'Content-Type': 'application/x-protobuf',
                'User-Agent': f'logfire-proxy/{VERSION}',
                'Authorization': 'token-1',
            },
            'timeout': 7.5,
        },
        {
            'url': 'https://example.com/base/v1/traces',
            'data': b'payload',
            'headers': {
                'Content-Type': 'application/x-protobuf',
                'User-Agent': f'logfire-proxy/{VERSION}',
                'Authorization': 'token-2',
            },
            'timeout': 7.5,
        },
    ]


def test_forwarding_pipeline_send_contains_token_failures() -> None:
    session = FakeForwardingSession(fail_tokens={'token-1'})
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=10,
    )
    queued_request = _make_queued_forwarding_request(b'payload', tokens=('token-1', 'token-2'))

    pipeline._send(queued_request)  # pyright: ignore[reportPrivateUsage]

    assert [call['headers']['Authorization'] for call in session.calls] == ['token-1', 'token-2']


class RecordingForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self, *, fail_bodies: set[bytes] | None = None) -> None:
        super().__init__(
            base_url='https://example.com',
            session=object(),  # type: ignore[arg-type]
            max_queued_body_bytes=100,
        )
        self.fail_bodies = fail_bodies or set()
        self.sent_bodies: list[bytes] = []
        self.active_send_counts: list[int] = []

    def _send(self, queued_request: QueuedForwardingRequest) -> None:
        self.active_send_counts.append(self.active_send_count)
        self.sent_bodies.append(queued_request.request.body)
        if queued_request.request.body in self.fail_bodies:
            raise RuntimeError('send failed')


def test_forwarding_pipeline_run_drains_queue_and_resets_state() -> None:
    pipeline = RecordingForwardingPipeline()
    pipeline.enqueue(_make_queued_forwarding_request(b'one'))
    pipeline.enqueue(_make_queued_forwarding_request(b'two'))

    pipeline._run()  # pyright: ignore[reportPrivateUsage]

    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.active_send_count == 0
    assert pipeline.sent_bodies == [b'one', b'two']
    assert pipeline.active_send_counts == [1, 1]


def test_forwarding_pipeline_run_continues_after_unexpected_send_failure() -> None:
    pipeline = RecordingForwardingPipeline(fail_bodies={b'one'})
    pipeline.enqueue(_make_queued_forwarding_request(b'one'))
    pipeline.enqueue(_make_queued_forwarding_request(b'two'))

    pipeline._run()  # pyright: ignore[reportPrivateUsage]

    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.active_send_count == 0
    assert pipeline.sent_bodies == [b'one', b'two']


def test_forwarding_pipeline_run_drains_already_queued_work_when_closed() -> None:
    pipeline = RecordingForwardingPipeline()
    pipeline.enqueue(_make_queued_forwarding_request(b'one'))
    pipeline.closed = True

    pipeline._run()  # pyright: ignore[reportPrivateUsage]

    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.active_send_count == 0
    assert pipeline.sent_bodies == [b'one']


def test_forwarding_manager_initial_state() -> None:
    config = object()
    manager = OTLPForwardingManager(config)  # type: ignore[arg-type]

    assert manager.config is config
    assert manager.tokens_by_base_url == {}
    assert manager.pipelines == {}
    assert manager.closed is False
    assert manager.lock is not None


def test_forwarding_manager_has_destinations() -> None:
    manager = OTLPForwardingManager(object())  # type: ignore[arg-type]

    assert manager.has_destinations() is False

    manager.tokens_by_base_url['https://example.com'] = ('token',)

    assert manager.has_destinations() is True


def test_forwarding_manager_add_destination_creates_pipeline_and_groups_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_sessions: list[Any] = []

    class FakeSession(FakeForwardingSession):
        def __init__(self) -> None:
            super().__init__()
            self.hooks: dict[str, list[object]] = {}
            created_sessions.append(self)

    hook = object()
    config = SimpleNamespace(advanced=SimpleNamespace(server_response_hook=hook))
    manager = OTLPForwardingManager(config)  # type: ignore[arg-type]
    monkeypatch.setattr(forwarding_module, 'OTLPExporterHttpSession', FakeSession)

    manager.add_destination(base_url='https://backend-1.example.com', token='token-1')
    manager.add_destination(base_url='https://backend-1.example.com', token='token-2')
    manager.add_destination(base_url='https://backend-2.example.com', token='token-3')

    assert manager.tokens_by_base_url == {
        'https://backend-1.example.com': ('token-1', 'token-2'),
        'https://backend-2.example.com': ('token-3',),
    }
    assert set(manager.pipelines) == {'https://backend-1.example.com', 'https://backend-2.example.com'}
    assert len(created_sessions) == 2
    assert all(session.hooks['response'] for session in created_sessions)
    assert manager.pipelines['https://backend-1.example.com'].session is created_sessions[0]
    assert manager.pipelines['https://backend-1.example.com'].max_queued_body_bytes == (
        OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES
    )


def test_forwarding_manager_add_destination_after_close_does_not_register(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_sessions: list[Any] = []

    class FakeSession(FakeForwardingSession):
        def __init__(self) -> None:
            super().__init__()
            self.hooks: dict[str, list[object]] = {}
            created_sessions.append(self)

    config = SimpleNamespace(advanced=SimpleNamespace(server_response_hook=None))
    manager = OTLPForwardingManager(config)  # type: ignore[arg-type]
    manager.closed = True
    monkeypatch.setattr(forwarding_module, 'OTLPExporterHttpSession', FakeSession)

    manager.add_destination(base_url='https://backend.example.com', token='token')

    assert manager.tokens_by_base_url == {}
    assert manager.pipelines == {}
    assert created_sessions == []
