from __future__ import annotations

import functools
import json
from typing import TYPE_CHECKING, Any, cast
from unittest import mock

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire
from logfire._internal.config import LogfireConfig
from logfire._internal.forwarding import ForwardingAdmissionResult, ForwardingRequest
from logfire.experimental import forwarding
from logfire.experimental.forwarding import ForwardExportRequestResponse

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.testclient import TestClient


class FakeForwardingManager:
    def __init__(self, result: ForwardingAdmissionResult | None = None) -> None:
        self.result = result or ForwardingAdmissionResult(response='success', message=None)
        self.submissions: list[ForwardingRequest] = []

    def has_destinations(self) -> bool:
        return True

    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult:
        self.submissions.append(request)
        return self.result

    def force_flush(self, timeout_millis: int) -> bool:
        return True

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        return True


class RecordingForwardingSession:
    def __init__(self, *, fail_posts: bool = False) -> None:
        self.hooks: dict[str, list[Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.fail_posts = fail_posts
        self.closed = False

    def post(self, url: str, data: bytes, **kwargs: Any) -> None:
        self.calls.append({'url': url, 'data': data, **kwargs})
        if self.fail_posts:
            raise RuntimeError('backend unavailable')

    def close(self) -> None:
        self.closed = True


def _set_successful_forwarding_manager(
    result: ForwardingAdmissionResult | None = None,
) -> FakeForwardingManager:
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    manager = FakeForwardingManager(result)
    cast(Any, config)._otlp_forwarding = manager
    return manager


@pytest.fixture
def fastapi_app() -> FastAPI:
    fastapi = pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)
    return cast('FastAPI', fastapi.FastAPI())


@pytest.fixture
def fastapi_client(fastapi_app: FastAPI) -> TestClient:
    test_client_cls = pytest.importorskip('starlette.testclient').TestClient
    return cast('TestClient', test_client_cls(fastapi_app))


def test_forward_export_request_logic() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    manager = _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = logfire.forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf', 'Host': 'example.com'},
            body=b'data',
        )

        assert isinstance(response, ForwardExportRequestResponse)
        assert response.status_code == 200
        assert response.content == b''
        assert response.headers == {'Content-Type': 'application/x-protobuf'}
        mock_post.assert_not_called()
        assert manager.submissions[0].path == '/v1/traces'
        assert manager.submissions[0].body == b'data'


def test_forward_export_request_function_defaults_to_default_instance() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    manager = _set_successful_forwarding_manager()

    response = forwarding.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'data',
    )

    assert response.status_code == 200
    assert manager.submissions[0].body == b'data'


def test_forward_export_request_invalid_path() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = logfire.forward_export_request(path='/invalid', headers={}, body=b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_export_request_path_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = logfire.forward_export_request(path='/v1/traces/../secret', headers={}, body=b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_export_request_exception_handling() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = logfire.forward_export_request(
            path='/v1/traces', headers={'Content-Type': 'application/x-protobuf'}, body=b''
        )
        assert response.status_code == 200
        mock_post.assert_not_called()


def test_fastapi_proxy_handler(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    fastapi_app.add_route('/logfire-proxy/{path:path}', logfire.forward_export_request_starlette, methods=['POST'])

    with mock.patch('requests.post') as mock_post:
        response = fastapi_client.post(
            '/logfire-proxy/v1/traces', content=b'trace_data', headers={'Content-Type': 'application/x-protobuf'}
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_fastapi_proxy_size_limit(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    handler = functools.partial(logfire.forward_export_request_starlette, max_body_size=10)
    fastapi_app.add_route('/logfire-proxy/{path:path}', handler, methods=['POST'])

    response = fastapi_client.post(
        '/logfire-proxy/v1/traces', content=b'12345678901', headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_fastapi_proxy_invalid_content_length(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    fastapi_app.add_route('/logfire-proxy/{path:path}', logfire.forward_export_request_starlette, methods=['POST'])

    response = fastapi_client.post('/logfire-proxy/v1/traces', content=b'', headers={'Content-Length': 'invalid'})
    assert response.status_code == 400
    assert response.content == b'Invalid Content-Length header'


def test_fastapi_proxy_body_limit_late_check(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    handler = functools.partial(logfire.forward_export_request_starlette, max_body_size=10)
    fastapi_app.add_route('/logfire-proxy/{path:path}', handler, methods=['POST'])

    # Lying about Content-Length bypasses early check, so we catch it while chunking
    response = fastapi_client.post('/logfire-proxy/v1/traces', content=b'12345678901', headers={'Content-Length': '5'})
    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_forward_export_request_percent_encoded_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = logfire.forward_export_request(path='/v1/traces/%2e%2e/secret', headers={}, body=b'')
    assert response.status_code == 400


def test_forward_export_request_multi_token() -> None:
    logfire.configure(token=['tok1', 'tok2'], send_to_logfire=False)
    _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = logfire.forward_export_request(
            path='/v1/traces', headers={'Content-Type': 'application/x-protobuf'}, body=b''
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_forward_export_request_missing_token() -> None:
    logfire.configure(token='tok', send_to_logfire=False)
    _set_successful_forwarding_manager()
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch.object(logfire_instance.config, 'token', None):
        response = logfire.forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf'},
            body=b'',
        )
        assert response.status_code == 200


def test_forward_export_request_explicit_instance() -> None:
    """Test that an explicit instance can be passed to forward_export_request."""
    logfire.configure(token='explicit_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    explicit_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch('requests.post') as mock_post:
        response = explicit_instance.forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf'},
            body=b'',
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_forward_export_request_missing_content_type() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_export_request(path='/v1/traces', headers={}, body=b'')

    assert response.status_code == 415
    assert response.headers == {'Content-Type': 'text/plain'}
    assert response.content == b'Missing content type header'


def test_forward_export_request_unsupported_content_type() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_export_request(path='/v1/traces', headers={'Content-Type': 'text/plain'}, body=b'')

    assert response.status_code == 415
    assert response.content == b'Unsupported content type, must be application/json or application/x-protobuf'


def test_forward_export_request_oversized_body() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'12345',
        max_body_size=4,
    )

    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_forward_export_request_no_destination_forbidden() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )

    assert response.status_code == 403
    assert response.content == b'Logfire is not configured with an active forwarding destination'


def test_forward_export_request_submits_to_checked_forwarding_manager() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    replacement_manager = FakeForwardingManager()

    class SwappingForwardingManager(FakeForwardingManager):
        def has_destinations(self) -> bool:
            cast(Any, config)._otlp_forwarding = replacement_manager
            return True

    manager = SwappingForwardingManager()
    cast(Any, config)._otlp_forwarding = manager

    response = logfire.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'data',
    )

    assert response.status_code == 200
    assert [request.body for request in manager.submissions] == [b'data']
    assert replacement_manager.submissions == []


def test_forward_export_request_validation_before_no_destination() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_export_request(path='/invalid', headers={}, body=b'')

    assert response.status_code == 400


def test_forward_export_request_configured_token_fanout(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions: list[RecordingForwardingSession] = []

    def session_factory() -> RecordingForwardingSession:
        session = RecordingForwardingSession()
        sessions.append(session)
        return session

    def initialize_credentials_from_token(self: LogfireConfig, token: str) -> None:
        return None

    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', initialize_credentials_from_token)
    monkeypatch.setattr('logfire._internal.forwarding.OTLPExporterHttpSession', session_factory)
    logfire.configure(
        token=['pylf_v1_us_token1', 'pylf_v1_us_token2'],
        send_to_logfire=True,
        console=False,
        metrics=False,
    )

    response = logfire.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'trace-payload',
    )
    manager = logfire.DEFAULT_LOGFIRE_INSTANCE.config._otlp_forwarding  # pyright: ignore[reportPrivateUsage]

    assert response.status_code == 200
    assert manager.force_flush(1000) is True
    assert len(sessions) == 1
    assert sessions[0].calls == [
        {
            'url': 'https://logfire-us.pydantic.dev/v1/traces',
            'data': b'trace-payload',
            'headers': {
                'Content-Type': 'application/x-protobuf',
                'User-Agent': f'logfire-proxy/{logfire.VERSION}',
                'Authorization': 'pylf_v1_us_token1',
            },
            'timeout': 10.0,
        },
        {
            'url': 'https://logfire-us.pydantic.dev/v1/traces',
            'data': b'trace-payload',
            'headers': {
                'Content-Type': 'application/x-protobuf',
                'User-Agent': f'logfire-proxy/{logfire.VERSION}',
                'Authorization': 'pylf_v1_us_token2',
            },
            'timeout': 10.0,
        },
    ]


def test_forward_export_request_backend_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions: list[RecordingForwardingSession] = []

    def session_factory() -> RecordingForwardingSession:
        session = RecordingForwardingSession(fail_posts=not sessions)
        sessions.append(session)
        return session

    def initialize_credentials_from_token(self: LogfireConfig, token: str) -> None:
        return None

    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', initialize_credentials_from_token)
    monkeypatch.setattr('logfire._internal.forwarding.OTLPExporterHttpSession', session_factory)
    logfire.configure(
        token=['pylf_v1_us_token', 'pylf_v1_eu_token'],
        send_to_logfire=True,
        console=False,
        metrics=False,
    )

    response = logfire.forward_export_request(
        path='/v1/logs',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'log-payload',
    )
    manager = logfire.DEFAULT_LOGFIRE_INSTANCE.config._otlp_forwarding  # pyright: ignore[reportPrivateUsage]

    assert response.status_code == 200
    assert manager.force_flush(1000) is True
    assert len(sessions) == 2
    assert [session.calls for session in sessions] == [
        [
            {
                'url': 'https://logfire-us.pydantic.dev/v1/logs',
                'data': b'log-payload',
                'headers': {
                    'Content-Type': 'application/x-protobuf',
                    'User-Agent': f'logfire-proxy/{logfire.VERSION}',
                    'Authorization': 'pylf_v1_us_token',
                },
                'timeout': 10.0,
            }
        ],
        [
            {
                'url': 'https://logfire-eu.pydantic.dev/v1/logs',
                'data': b'log-payload',
                'headers': {
                    'Content-Type': 'application/x-protobuf',
                    'User-Agent': f'logfire-proxy/{logfire.VERSION}',
                    'Authorization': 'pylf_v1_eu_token',
                },
                'timeout': 10.0,
            }
        ],
    ]


def test_forward_export_request_header_sanitization(monkeypatch: pytest.MonkeyPatch) -> None:
    sessions: list[RecordingForwardingSession] = []

    def session_factory() -> RecordingForwardingSession:
        session = RecordingForwardingSession()
        sessions.append(session)
        return session

    def initialize_credentials_from_token(self: LogfireConfig, token: str) -> None:
        return None

    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', initialize_credentials_from_token)
    monkeypatch.setattr('logfire._internal.forwarding.OTLPExporterHttpSession', session_factory)
    logfire.configure(
        token='pylf_v1_us_server_token',
        send_to_logfire=True,
        console=False,
        metrics=False,
    )

    response = logfire.forward_export_request(
        path='/v1/metrics',
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'content-encoding': 'gzip',
            'User-Agent': 'browser-otel/1.0',
            'Authorization': 'client-token',
            'Cookie': 'session=secret',
            'Host': 'app.example.com',
            'X-Api-Key': 'client-secret',
        },
        body=b'{}',
    )
    manager = logfire.DEFAULT_LOGFIRE_INSTANCE.config._otlp_forwarding  # pyright: ignore[reportPrivateUsage]

    assert response.status_code == 200
    assert manager.force_flush(1000) is True
    assert len(sessions) == 1
    assert sessions[0].calls[0]['headers'] == {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Encoding': 'gzip',
        'User-Agent': f'logfire-proxy/{logfire.VERSION} browser-otel/1.0',
        'Authorization': 'pylf_v1_us_server_token',
    }


def test_forward_export_request_partial_success_when_backend_queue_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions: list[RecordingForwardingSession] = []

    def session_factory() -> RecordingForwardingSession:
        session = RecordingForwardingSession()
        sessions.append(session)
        return session

    def initialize_credentials_from_token(self: LogfireConfig, token: str) -> None:
        return None

    monkeypatch.setattr(LogfireConfig, '_initialize_credentials_from_token', initialize_credentials_from_token)
    monkeypatch.setattr('logfire._internal.forwarding.OTLPExporterHttpSession', session_factory)
    logfire.configure(
        token=['pylf_v1_us_token', 'pylf_v1_eu_token'],
        send_to_logfire=True,
        console=False,
        metrics=False,
    )
    manager = logfire.DEFAULT_LOGFIRE_INSTANCE.config._otlp_forwarding  # pyright: ignore[reportPrivateUsage]
    manager.pipelines['https://logfire-us.pydantic.dev'].max_queued_body_bytes = 0

    response = logfire.forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/json'},
        body=b'{}',
    )

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert json.loads(response.content) == {
        'partialSuccess': {
            'rejectedSpans': '0',
            'errorMessage': 'Forwarding request was locally dropped for 1 backend URL(s).',
        }
    }
    assert manager.force_flush(1000) is True
    assert len(sessions) == 2
    assert sessions[0].calls == []
    assert sessions[1].calls == [
        {
            'url': 'https://logfire-eu.pydantic.dev/v1/traces',
            'data': b'{}',
            'headers': {
                'Content-Type': 'application/json',
                'User-Agent': f'logfire-proxy/{logfire.VERSION}',
                'Authorization': 'pylf_v1_eu_token',
            },
            'timeout': 10.0,
        }
    ]


@pytest.mark.parametrize(
    ('path', 'rejected_field'),
    [
        ('/v1/traces', 'rejectedSpans'),
        ('/v1/logs', 'rejectedLogRecords'),
        ('/v1/metrics', 'rejectedDataPoints'),
    ],
)
def test_forward_export_request_partial_success_json(path: str, rejected_field: str) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager(ForwardingAdmissionResult(response='partial_success', message='queue full'))

    response = logfire.forward_export_request(
        path=path,
        headers={'Content-Type': 'application/json'},
        body=b'{}',
    )

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/json'}
    assert json.loads(response.content) == {'partialSuccess': {'errorMessage': 'queue full', rejected_field: '0'}}


@pytest.mark.parametrize(
    ('path', 'message_cls', 'rejected_attr'),
    [
        ('/v1/traces', ExportTraceServiceResponse, 'rejected_spans'),
        ('/v1/logs', ExportLogsServiceResponse, 'rejected_log_records'),
        ('/v1/metrics', ExportMetricsServiceResponse, 'rejected_data_points'),
    ],
)
def test_forward_export_request_partial_success_protobuf(
    path: str, message_cls: type[object], rejected_attr: str
) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager(ForwardingAdmissionResult(response='partial_success', message='closed'))

    response = logfire.forward_export_request(
        path=path,
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )
    message = message_cls()
    message.ParseFromString(response.content)  # type: ignore[attr-defined]

    assert response.status_code == 200
    assert response.headers == {'Content-Type': 'application/x-protobuf'}
    assert message.partial_success.error_message == 'closed'  # type: ignore[attr-defined]
    assert getattr(message.partial_success, rejected_attr) == 0  # type: ignore[attr-defined]


def test_fastapi_proxy_invalid_method(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    fastapi_app.add_route(
        '/logfire-proxy/{path:path}', logfire.forward_export_request_starlette, methods=['POST', 'GET']
    )

    response = fastapi_client.get('/logfire-proxy/v1/traces')
    assert response.status_code == 405
    assert response.content == b'Method Not Allowed'


def test_fastapi_proxy_missing_path(fastapi_app: FastAPI, fastapi_client: TestClient) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    fastapi_app.add_route('/logfire-proxy-missing', logfire.forward_export_request_starlette, methods=['POST'])

    response = fastapi_client.post('/logfire-proxy-missing')
    assert response.status_code == 400
    assert response.content == b'Missing path parameter. Use {path:path} in the route definition.'


@pytest.mark.anyio
async def test_fastapi_proxy_instrumentation_coverage_mock() -> None:
    request = mock.Mock()
    request.headers = {}

    async def mock_stream():
        yield b'12345'
        yield b'67890'

    request.stream = mock_stream
    request.path_params = {'path': 'v1/traces'}
    request.method = 'POST'

    with mock.patch('logfire.experimental.forwarding.forward_export_request') as mock_fwd:
        mock_fwd.return_value = ForwardExportRequestResponse(200, {'Content-Type': 'application/json'}, b'{"ok": true}')

        response = await logfire.forward_export_request_starlette(request, max_body_size=10)

        assert response.status_code == 200
        assert response.body == b'{"ok": true}'
        assert mock_fwd.call_args.kwargs == {
            'path': 'v1/traces',
            'headers': {},
            'body': b'1234567890',
            'logfire_instance': logfire.DEFAULT_LOGFIRE_INSTANCE,
            'max_body_size': 10,
        }

        mock_fwd.reset_mock()

        request.headers = {'content-length': '10'}
        response2 = await logfire.forward_export_request_starlette(request, max_body_size=10)

        assert response2.status_code == 200
        assert response2.body == b'{"ok": true}'
        assert mock_fwd.call_args.kwargs == {
            'path': 'v1/traces',
            'headers': {'content-length': '10'},
            'body': b'1234567890',
            'logfire_instance': logfire.DEFAULT_LOGFIRE_INSTANCE,
            'max_body_size': 10,
        }
