from __future__ import annotations

import gc
import json
import weakref
from collections.abc import Callable
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any, cast

import pytest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire._internal.forwarding as forwarding_module
from logfire._internal.forwarding import (
    FORWARDING_CONFIGS,
    OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
    OTLP_FORWARDING_MAX_QUEUED_ITEMS,
    ForwardingAdmissionResult,
    ForwardingContentType,
    ForwardingErrorResponse,
    ForwardingRequest,
    OTLPForwardingManager,
    OTLPForwardingPipeline,
    _normalize_forwarding_path,  # pyright: ignore[reportPrivateUsage]
    build_forwarding_request,
    build_partial_success_response,
    build_success_response,
    parse_forwarding_content_type,
)
from logfire.types import ServerResponseCallbackHelper
from logfire.version import VERSION


@pytest.mark.parametrize(
    ('content_type', 'expected'),
    [
        ('application/x-protobuf', ForwardingContentType.PROTOBUF),
        ('application/json', ForwardingContentType.JSON),
        ('Application/JSON', ForwardingContentType.JSON),
        ('text/plain; note=application/json', ForwardingContentType.JSON),
        ('', None),
        ('text/plain', None),
    ],
)
def test_parse_forwarding_content_type(content_type: str, expected: ForwardingContentType | None) -> None:
    assert parse_forwarding_content_type(content_type) is expected


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/v1/traces', '/v1/traces'),
        ('v1/traces', '/v1/traces'),
    ],
)
def test_normalize_forwarding_path_valid(path: str, expected: str) -> None:
    assert _normalize_forwarding_path(path) == expected


@pytest.mark.parametrize(
    'path',
    [
        '/invalid',
        '/v1/traces/%2e%2e/secret',
        'https://example.com/v1/traces',
        '/v1/traces?foo=bar',
    ],
)
def test_normalize_forwarding_path_rejections(path: str) -> None:
    response = _normalize_forwarding_path(path)

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400
    assert response.content == b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics'


def test_build_forwarding_request_valid_protobuf() -> None:
    headers = {
        'Content-Type': 'application/x-protobuf',
        'Content-Encoding': 'gzip',
        'User-Agent': 'browser',
        'Authorization': 'client-token',
    }
    request = build_forwarding_request(
        path='/v1/traces',
        headers=headers,
        body=b'trace-data',
    )

    assert isinstance(request, ForwardingRequest)
    assert request.path == '/v1/traces'
    assert request.body == b'trace-data'
    assert request.content_type is ForwardingContentType.PROTOBUF
    assert request.headers == {
        'Content-Type': 'application/x-protobuf',
        'Content-Encoding': 'gzip',
        'User-Agent': f'logfire-proxy/{VERSION} browser',
    }


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
    assert request.headers == {
        'Content-Type': 'application/json; charset=utf-8',
        'User-Agent': f'logfire-proxy/{VERSION}',
    }


def test_build_forwarding_request_oversized_body() -> None:
    response = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'12345',
        max_body_size=4,
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 413
    assert response.content == b'Payload too large'


@pytest.mark.parametrize(
    ('headers', 'content'),
    [
        ({}, b'Missing content type header'),
        (
            {'Content-Type': 'text/plain'},
            b'Unsupported content type, must be application/json or application/x-protobuf',
        ),
    ],
)
def test_build_forwarding_request_unsupported_content_type(headers: dict[str, str], content: bytes) -> None:
    response = build_forwarding_request(path='/v1/traces', headers=headers, body=b'')

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 415
    assert response.content == content


def test_build_forwarding_request_invalid_path() -> None:
    response = build_forwarding_request(
        path='/invalid',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400


def test_build_success_response_protobuf() -> None:
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'trace-data',
        content_type=ForwardingContentType.PROTOBUF,
        headers={'Content-Type': 'application/x-protobuf'},
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
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )

    response = build_success_response(request)

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert response.content == b'{}'


def test_build_partial_success_response_json() -> None:
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'{}',
        content_type=ForwardingContentType.JSON,
        headers={'Content-Type': 'application/json'},
    )

    response = build_partial_success_response(request, message='queue full')

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert json.loads(response.content) == {
        'partialSuccess': {
            'errorMessage': 'queue full',
            'rejectedLogRecords': '0',
        }
    }


def test_build_partial_success_response_protobuf() -> None:
    request = ForwardingRequest(
        path='/v1/metrics',
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        headers={'Content-Type': 'application/x-protobuf'},
    )

    response = build_partial_success_response(request, message='closed')
    message = ExportMetricsServiceResponse()
    message.ParseFromString(response.content)

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/x-protobuf'}
    assert message.partial_success.error_message == 'closed'
    assert message.partial_success.rejected_data_points == 0


def test_forwarding_path_config_timeout_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FORWARDING_CONFIGS['/v1/traces']
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TIMEOUT', raising=False)
    monkeypatch.delenv(config.timeout_env, raising=False)

    assert config.timeout() == 10.0


def test_forwarding_path_config_timeout_generic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FORWARDING_CONFIGS['/v1/traces']
    monkeypatch.delenv(config.timeout_env, raising=False)
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TIMEOUT', '12.5')

    assert config.timeout() == 12.5


def test_forwarding_path_config_timeout_signal_specific_override(monkeypatch: pytest.MonkeyPatch) -> None:
    config = FORWARDING_CONFIGS['/v1/traces']
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TIMEOUT', '12.5')
    monkeypatch.setenv(config.timeout_env, '3.25')

    assert config.timeout() == 3.25


def _make_forwarding_request(body: bytes) -> ForwardingRequest:
    return ForwardingRequest(
        path='/v1/traces',
        body=body,
        content_type=ForwardingContentType.PROTOBUF,
        headers={
            'Content-Type': 'application/x-protobuf',
            'User-Agent': f'logfire-proxy/{VERSION}',
        },
    )


def test_forwarding_pipeline_enqueue_accepts_and_accounts_bytes() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=10)
    request = _make_forwarding_request(b'12345')

    assert pipeline.enqueue(request) is True
    assert pipeline.started.wait(timeout=5) is True
    worker = pipeline.worker
    assert list(pipeline.queue) == [request]
    assert pipeline.queued_body_bytes == 5
    assert worker is not None
    assert worker.daemon is True
    assert pipeline.enqueue(_make_forwarding_request(b'two')) is True
    assert pipeline.worker is worker
    assert pipeline.enqueue(_make_forwarding_request(b'three')) is False
    assert list(pipeline.queue) == [request, _make_forwarding_request(b'two')]
    assert pipeline.queued_body_bytes == 8
    assert pipeline.worker is worker
    pipeline.stop()


class BlockingRunForwardingPipeline(OTLPForwardingPipeline):
    def __init__(
        self,
        *,
        max_queued_body_bytes: int = 100,
        max_queued_items: int = OTLP_FORWARDING_MAX_QUEUED_ITEMS,
    ) -> None:
        super().__init__(
            base_url='https://example.com',
            session=object(),  # type: ignore[arg-type]
            max_queued_body_bytes=max_queued_body_bytes,
            max_queued_items=max_queued_items,
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


def test_forwarding_pipeline_enqueue_rejects_at_item_limit() -> None:
    pipeline = BlockingRunForwardingPipeline(max_queued_body_bytes=1, max_queued_items=2)
    request = _make_forwarding_request(b'')

    try:
        assert pipeline.enqueue(request) is True
        assert pipeline.enqueue(request) is True
        assert pipeline.enqueue(request) is False
        assert list(pipeline.queue) == [request, request]
        assert pipeline.queued_body_bytes == 0
    finally:
        pipeline.stop()


def test_forwarding_pipeline_at_fork_reinit_clears_inherited_queue_and_worker() -> None:
    pipeline = BlockingRunForwardingPipeline()
    request = _make_forwarding_request(b'one')
    worker: Thread | None = None

    try:
        assert pipeline.enqueue(request) is True
        assert pipeline.started.wait(timeout=5) is True
        worker = pipeline.worker
        condition = pipeline.condition
        session = SimpleNamespace(close=lambda: None)

        pipeline._at_fork_reinit(session=session)  # pyright: ignore[reportPrivateUsage, reportArgumentType]

        assert list(pipeline.queue) == []
        assert pipeline.worker is None
        assert pipeline.condition is not condition
        assert pipeline.session is session
        assert worker is not None
    finally:
        pipeline.release.set()
        if worker is not None:
            worker.join(timeout=5)


class BlockingSendForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self, session: Any | None = None) -> None:
        super().__init__(
            base_url='https://example.com',
            session=session or SimpleNamespace(close=lambda: None),  # type: ignore[arg-type]
            max_queued_body_bytes=100,
        )
        self.started = Event()
        self.release = Event()

    def _send(self, request: ForwardingRequest) -> None:
        self.started.set()
        self.release.wait(timeout=5)


def _wait_for_no_live_worker(pipeline: OTLPForwardingPipeline) -> None:
    with pipeline.condition:
        assert pipeline.condition.wait_for(
            lambda: pipeline.worker is None or not pipeline.worker.is_alive(),
            timeout=5,
        )


def test_forwarding_pipeline_force_flush_success_waits_for_active_send() -> None:
    pipeline = BlockingSendForwardingPipeline()
    assert pipeline.enqueue(_make_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    worker = pipeline.worker

    assert pipeline.force_flush(1) is False
    pipeline.release.set()
    assert pipeline.force_flush(5000) is True
    _wait_for_no_live_worker(pipeline)

    pipeline.started.clear()
    assert pipeline.enqueue(_make_forwarding_request(b'two')) is True
    assert pipeline.started.wait(timeout=5) is True
    assert pipeline.worker is not worker
    assert pipeline.force_flush(5000) is True
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_closes_admission_and_idle_session() -> None:
    session = FakeForwardingSession()
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=100,
    )

    assert pipeline.shutdown(1000) is True
    assert pipeline.shutdown(1000) is True

    assert pipeline.closed is True
    assert pipeline.worker is None
    assert session.closed is True
    assert pipeline.enqueue(_make_forwarding_request(b'one')) is False


class FakeForwardingSession:
    def __init__(self, *, fail_tokens: set[str] | None = None) -> None:
        self.fail_tokens = fail_tokens or set()
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, data: bytes, **kwargs: Any) -> object:
        self.calls.append({'url': url, 'data': data, **kwargs})
        headers = kwargs.get('headers')
        authorization = cast(dict[str, str], headers).get('Authorization') if isinstance(headers, dict) else None
        if authorization in self.fail_tokens:
            raise RuntimeError('send failed')
        return object()

    def close(self) -> None:
        self.closed = True


def test_forwarding_pipeline_shutdown_drains_queued_work() -> None:
    session = FakeForwardingSession()
    pipeline = BlockingSendForwardingPipeline(session)
    assert pipeline.enqueue(_make_forwarding_request(b'one')) is True
    assert pipeline.started.wait(timeout=5) is True
    shutdown_result: list[bool] = []

    shutdown_thread = Thread(target=lambda: shutdown_result.append(pipeline.shutdown(5000)))
    shutdown_thread.start()
    with pipeline.condition:
        assert pipeline.condition.wait_for(lambda: pipeline.closed, timeout=5)
    assert pipeline.enqueue(_make_forwarding_request(b'two')) is False
    pipeline.release.set()
    shutdown_thread.join(timeout=5)

    assert shutdown_result == [True]
    assert pipeline.closed is True
    assert pipeline.queued_body_bytes == 0
    assert list(pipeline.queue) == []
    assert session.closed is True
    _wait_for_no_live_worker(pipeline)


def test_forwarding_pipeline_shutdown_timeout_drops_queued_work_after_active_send() -> None:
    for drain_queued in (True, False):
        session = FakeForwardingSession()
        pipeline = BlockingSendForwardingPipeline(session)
        assert pipeline.enqueue(_make_forwarding_request(b'one')) is True
        assert pipeline.started.wait(timeout=5) is True
        assert pipeline.enqueue(_make_forwarding_request(b'two')) is True

        assert pipeline.shutdown(1, drain_queued=drain_queued) is False
        assert list(pipeline.queue) == []
        assert pipeline.queued_body_bytes == 0
        assert session.closed is False

        pipeline.release.set()
        _wait_for_no_live_worker(pipeline)

        assert session.closed is True


def test_forwarding_pipeline_send_fans_out_to_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TRACES_TIMEOUT', '7.5')
    session = FakeForwardingSession(fail_tokens={'token-1'})
    pipeline = OTLPForwardingPipeline(
        base_url='https://example.com/base/',
        session=session,  # type: ignore[arg-type]
        max_queued_body_bytes=10,
    )
    pipeline.tokens = ['token-1', 'token-2']
    request = _make_forwarding_request(b'payload')

    pipeline._send(request)  # pyright: ignore[reportPrivateUsage]

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


class FailingSendForwardingPipeline(OTLPForwardingPipeline):
    def __init__(self) -> None:
        super().__init__(
            base_url='https://example.com',
            session=SimpleNamespace(close=lambda: None),  # type: ignore[arg-type]
            max_queued_body_bytes=100,
        )
        self.first_send_started = Event()
        self.release_first_send = Event()
        self.sent_bodies: list[bytes] = []

    def _send(self, request: ForwardingRequest) -> None:
        self.sent_bodies.append(request.body)
        if request.body == b'one':
            self.first_send_started.set()
            self.release_first_send.wait(timeout=5)
            raise RuntimeError('send failed')


def test_forwarding_pipeline_worker_continues_after_unexpected_send_failure() -> None:
    pipeline = FailingSendForwardingPipeline()
    assert pipeline.enqueue(_make_forwarding_request(b'one')) is True
    assert pipeline.first_send_started.wait(timeout=5) is True
    assert pipeline.enqueue(_make_forwarding_request(b'two')) is True

    pipeline.release_first_send.set()
    assert pipeline.force_flush(5000) is True
    _wait_for_no_live_worker(pipeline)

    assert list(pipeline.queue) == []
    assert pipeline.queued_body_bytes == 0
    assert pipeline.sent_bodies == [b'one', b'two']
    assert pipeline.shutdown(5000) is True


def test_forwarding_manager_destinations_create_pipeline_and_group_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_sessions: list[Any] = []

    class FakeSession(FakeForwardingSession):
        def __init__(self) -> None:
            super().__init__()
            self.hooks: dict[str, list[object]] = {}
            created_sessions.append(self)

    def hook(helper: ServerResponseCallbackHelper) -> None:
        pass

    monkeypatch.setattr(forwarding_module, 'OTLPExporterHttpSession', FakeSession)

    manager = OTLPForwardingManager(
        [
            ('https://backend-1.example.com', 'token-1'),
            ('https://backend-1.example.com', 'token-2'),
            ('https://backend-2.example.com', 'token-3'),
        ],
        server_response_hook=hook,
    )

    assert set(manager.pipelines) == {'https://backend-1.example.com', 'https://backend-2.example.com'}
    assert len(created_sessions) == 2
    assert all(session.hooks['response'] for session in created_sessions)
    assert manager.pipelines['https://backend-1.example.com'].session is created_sessions[0]
    assert manager.pipelines['https://backend-1.example.com'].tokens == ['token-1', 'token-2']
    assert manager.pipelines['https://backend-2.example.com'].tokens == ['token-3']
    assert manager.pipelines['https://backend-1.example.com'].max_queued_body_bytes == (
        OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES
    )
    assert manager.pipelines['https://backend-1.example.com'].max_queued_items == OTLP_FORWARDING_MAX_QUEUED_ITEMS
    assert all(pipeline.worker is None for pipeline in manager.pipelines.values())


def test_forwarding_manager_after_fork_callback_is_weak(monkeypatch: pytest.MonkeyPatch) -> None:
    callbacks: list[Callable[[], None]] = []

    def register_at_fork(*, after_in_child: Callable[[], None]) -> None:
        callbacks.append(after_in_child)

    created_sessions: list[FakeForwardingSession] = []

    class FakeSession(FakeForwardingSession):
        def __init__(self) -> None:
            super().__init__()
            self.hooks: dict[str, list[object]] = {}
            created_sessions.append(self)

    monkeypatch.setattr(forwarding_module.os, 'register_at_fork', register_at_fork)
    monkeypatch.setattr(forwarding_module, 'OTLPExporterHttpSession', FakeSession)
    manager = OTLPForwardingManager([('https://backend.example.com', 'token')])
    pipeline = manager.pipelines['https://backend.example.com']
    inherited_session = pipeline.session
    pipeline.queue.append(_make_forwarding_request(b'data'))
    pipeline.worker = Thread(target=lambda: None)
    condition = pipeline.condition

    callbacks[0]()

    assert list(pipeline.queue) == []
    assert pipeline.worker is None
    assert pipeline.condition is not condition
    assert pipeline.session is not inherited_session
    assert pipeline.session is created_sessions[1]

    manager_ref = weakref.ref(manager)
    del manager
    gc.collect()

    assert manager_ref() is None
    callbacks[0]()
    assert len(created_sessions) == 2


def test_forwarding_manager_submit_reinitializes_after_pid_change(monkeypatch: pytest.MonkeyPatch) -> None:
    pid = 1000
    created_sessions: list[FakeForwardingSession] = []

    class FakeSession(FakeForwardingSession):
        def __init__(self) -> None:
            super().__init__()
            self.hooks: dict[str, list[object]] = {}
            created_sessions.append(self)

    monkeypatch.setattr(forwarding_module.os, 'getpid', lambda: pid)
    monkeypatch.setattr(forwarding_module, 'OTLPExporterHttpSession', FakeSession)
    manager = OTLPForwardingManager([('https://backend.example.com', 'token')])
    pipeline = manager.pipelines['https://backend.example.com']
    inherited_condition = pipeline.condition
    inherited_session = pipeline.session

    pid = 1001
    result = manager.submit(_make_forwarding_request(b'child'))
    assert result == ForwardingAdmissionResult(response='success', message=None)
    assert manager.force_flush(5000) is True
    _wait_for_no_live_worker(pipeline)

    assert pipeline.condition is not inherited_condition
    assert pipeline.session is not inherited_session
    assert pipeline.session is created_sessions[1]
    assert created_sessions[0].calls == []
    assert [call['data'] for call in created_sessions[1].calls] == [b'child']


class FakeForwardingPipeline:
    def __init__(self, *, accepted: bool = True) -> None:
        self.accepted = accepted
        self.enqueued: list[ForwardingRequest] = []

    def enqueue(self, request: ForwardingRequest) -> bool:
        self.enqueued.append(request)
        return self.accepted


def test_forwarding_manager_submit_success_enqueues_per_backend_url() -> None:
    manager = OTLPForwardingManager([])
    pipeline_1 = FakeForwardingPipeline()
    pipeline_2 = FakeForwardingPipeline()
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        headers={'Content-Type': 'application/x-protobuf'},
    )
    manager.pipelines = {  # type: ignore[assignment]
        'https://backend-1.example.com': pipeline_1,
        'https://backend-2.example.com': pipeline_2,
    }

    result = manager.submit(request)

    assert result == ForwardingAdmissionResult(response='success', message=None)
    assert pipeline_1.enqueued == [request]
    assert pipeline_2.enqueued == [request]


def test_forwarding_manager_submit_partial_success_for_mixed_backend_outcomes() -> None:
    manager = OTLPForwardingManager([])
    accepting_pipeline = FakeForwardingPipeline()
    rejecting_pipeline = FakeForwardingPipeline(accepted=False)
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        headers={'Content-Type': 'application/x-protobuf'},
    )
    manager.pipelines = {  # type: ignore[assignment]
        'https://backend-1.example.com': accepting_pipeline,
        'https://backend-2.example.com': rejecting_pipeline,
    }

    result = manager.submit(request)

    assert result == ForwardingAdmissionResult(
        response='partial_success',
        message='Forwarding request was locally dropped for 1 backend URL(s).',
    )
    assert accepting_pipeline.enqueued == [request]
    assert rejecting_pipeline.enqueued == [request]


def test_forwarding_manager_submit_after_close_returns_partial_success_without_enqueue() -> None:
    manager = OTLPForwardingManager([])
    pipeline = FakeForwardingPipeline()
    request = ForwardingRequest(
        path='/v1/metrics',
        body=b'data',
        content_type=ForwardingContentType.PROTOBUF,
        headers={'Content-Type': 'application/x-protobuf'},
    )
    manager.pipelines = {'https://backend.example.com': pipeline}  # type: ignore[assignment]
    manager.closed = True

    result = manager.submit(request)

    assert result == ForwardingAdmissionResult(
        response='partial_success',
        message='Forwarding manager is closed; request was locally dropped.',
    )
    assert pipeline.enqueued == []
    assert manager.pipelines == {'https://backend.example.com': pipeline}


class FakeFlushPipeline:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.flush_timeouts: list[int] = []

    def force_flush(self, timeout_millis: int) -> bool:
        self.flush_timeouts.append(timeout_millis)
        return self.result


def test_forwarding_manager_force_flush_uses_remaining_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    times = iter([0.0, 0.0, 0.025])
    monkeypatch.setattr(forwarding_module, 'monotonic', lambda: next(times))
    pipeline_1 = FakeFlushPipeline()
    pipeline_2 = FakeFlushPipeline()
    manager = OTLPForwardingManager([])
    manager.pipelines = {'one': pipeline_1, 'two': pipeline_2}  # type: ignore[assignment]

    assert manager.force_flush(100) is True

    assert pipeline_1.flush_timeouts == [100]
    assert pipeline_2.flush_timeouts == [75]


def test_forwarding_manager_force_flush_returns_false_for_pipeline_timeout() -> None:
    pipeline_1 = FakeFlushPipeline()
    pipeline_2 = FakeFlushPipeline(result=False)
    manager = OTLPForwardingManager([])
    manager.pipelines = {'one': pipeline_1, 'two': pipeline_2}  # type: ignore[assignment]

    assert manager.force_flush(100) is False

    assert len(pipeline_1.flush_timeouts) == 1
    assert len(pipeline_2.flush_timeouts) == 1


class FakeShutdownPipeline:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.shutdown_calls: list[tuple[int, bool]] = []

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        self.shutdown_calls.append((timeout_millis, drain_queued))
        return self.result


@pytest.mark.parametrize('drain_queued', [True, False])
def test_forwarding_manager_shutdown_uses_remaining_budget(
    monkeypatch: pytest.MonkeyPatch,
    drain_queued: bool,
) -> None:
    times = iter([0.0, 0.0, 0.04])
    monkeypatch.setattr(forwarding_module, 'monotonic', lambda: next(times))
    pipeline_1 = FakeShutdownPipeline()
    pipeline_2 = FakeShutdownPipeline()
    manager = OTLPForwardingManager([])
    manager.pipelines = {'one': pipeline_1, 'two': pipeline_2}  # type: ignore[assignment]

    assert manager.shutdown(100, drain_queued=drain_queued) is True

    assert manager.closed is True
    assert pipeline_1.shutdown_calls == [(100, drain_queued)]
    assert pipeline_2.shutdown_calls == [(60, drain_queued)]


def test_forwarding_manager_shutdown_returns_false_for_pipeline_timeout() -> None:
    pipeline_1 = FakeShutdownPipeline()
    pipeline_2 = FakeShutdownPipeline(result=False)
    manager = OTLPForwardingManager([])
    manager.pipelines = {'one': pipeline_1, 'two': pipeline_2}  # type: ignore[assignment]

    assert manager.shutdown(100) is False

    assert len(pipeline_1.shutdown_calls) == 1
    assert len(pipeline_2.shutdown_calls) == 1
