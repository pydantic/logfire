from __future__ import annotations

import inspect
import json
import sys
from typing import Any, cast
from unittest import mock

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire
from logfire._internal.forwarding import ForwardingAdmissionResult, ForwardingRequest
from logfire.experimental.forwarding import ForwardExportRequestResponse, forward_export_request, logfire_proxy


class FakeForwardingManager:
    def __init__(self, result: ForwardingAdmissionResult | None = None) -> None:
        self.result = result or ForwardingAdmissionResult(response='success', message=None)
        self.submissions: list[ForwardingRequest] = []

    def has_destinations(self) -> bool:
        return True

    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult:
        self.submissions.append(request)
        return self.result

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        return True


def _set_successful_forwarding_manager(
    result: ForwardingAdmissionResult | None = None,
) -> FakeForwardingManager:
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    manager = FakeForwardingManager(result)
    cast(Any, config)._otlp_forwarding = manager
    return manager


def test_forward_export_request_logic() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    manager = _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = forward_export_request(
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


def test_forward_export_request_invalid_path() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = forward_export_request(path='/invalid', headers={}, body=b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_export_request_path_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = forward_export_request(path='/v1/traces/../secret', headers={}, body=b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_export_request_exception_handling() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = forward_export_request(
            path='/v1/traces', headers={'Content-Type': 'application/x-protobuf'}, body=b''
        )
        assert response.status_code == 200
        mock_post.assert_not_called()


def test_fastapi_proxy_handler() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    app.add_route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST'])

    client = TestClient(app)

    with mock.patch('requests.post') as mock_post:
        response = client.post(
            '/logfire-proxy/v1/traces', content=b'trace_data', headers={'Content-Type': 'application/x-protobuf'}
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_fastapi_proxy_size_limit() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI
    import functools

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    handler = functools.partial(logfire_proxy, max_body_size=10)
    app.add_route('/logfire-proxy/{path:path}', handler, methods=['POST'])

    client = TestClient(app)

    response = client.post(
        '/logfire-proxy/v1/traces', content=b'12345678901', headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_fastapi_proxy_invalid_content_length() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)
    app.add_route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST'])

    client = TestClient(app)

    response = client.post('/logfire-proxy/v1/traces', content=b'', headers={'Content-Length': 'invalid'})
    assert response.status_code == 400
    assert response.content == b'Invalid Content-Length header'


def test_fastapi_proxy_body_limit_late_check() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI
    import functools

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    handler = functools.partial(logfire_proxy, max_body_size=10)
    app.add_route('/logfire-proxy/{path:path}', handler, methods=['POST'])

    client = TestClient(app)

    # Lying about Content-Length bypasses early check, so we catch it while chunking
    response = client.post('/logfire-proxy/v1/traces', content=b'12345678901', headers={'Content-Length': '5'})
    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_forward_export_request_percent_encoded_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    response = forward_export_request(path='/v1/traces/%2e%2e/secret', headers={}, body=b'')
    assert response.status_code == 400


def test_forward_export_request_multi_token() -> None:
    logfire.configure(token=['tok1', 'tok2'], send_to_logfire=False)
    _set_successful_forwarding_manager()

    with mock.patch('requests.post') as mock_post:
        response = forward_export_request(
            path='/v1/traces', headers={'Content-Type': 'application/x-protobuf'}, body=b''
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_forward_export_request_missing_token() -> None:
    logfire.configure(token='tok', send_to_logfire=False)
    _set_successful_forwarding_manager()
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch.object(logfire_instance.config, 'token', None):
        response = forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf'},
            body=b'',
            logfire_instance=logfire_instance,
        )
        assert response.status_code == 200


def test_forward_export_request_explicit_instance() -> None:
    """Test that an explicit instance can be passed to forward_export_request."""
    logfire.configure(token='explicit_token', send_to_logfire=False)
    _set_successful_forwarding_manager()

    explicit_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch('requests.post') as mock_post:
        response = forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf'},
            body=b'',
            logfire_instance=explicit_instance,
        )

        assert response.status_code == 200
        mock_post.assert_not_called()


def test_forward_export_request_missing_content_type() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = forward_export_request(path='/v1/traces', headers={}, body=b'')

    assert response.status_code == 415
    assert response.headers == {'Content-Type': 'text/plain'}
    assert response.content == b'Unsupported content type'


def test_forward_export_request_unsupported_content_type() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = forward_export_request(path='/v1/traces', headers={'Content-Type': 'text/plain'}, body=b'')

    assert response.status_code == 415
    assert response.content == b'Unsupported content type'


def test_forward_export_request_oversized_body() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'12345',
        max_body_size=4,
    )

    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_forward_export_request_no_destination_forbidden() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )

    assert response.status_code == 403
    assert response.content == b'Logfire is not configured with an active forwarding destination'


def test_forward_export_request_validation_before_no_destination() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = forward_export_request(path='/invalid', headers={}, body=b'')

    assert response.status_code == 400


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

    response = forward_export_request(
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

    response = forward_export_request(
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


def test_fastapi_proxy_invalid_method() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)
    app.add_route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST', 'GET'])

    client = TestClient(app)
    response = client.get('/logfire-proxy/v1/traces')
    assert response.status_code == 405
    assert response.content == b'Method Not Allowed'


def test_fastapi_proxy_missing_path() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)
    app.add_route('/logfire-proxy-missing', logfire_proxy, methods=['POST'])

    client = TestClient(app)
    response = client.post('/logfire-proxy-missing')
    assert response.status_code == 400
    assert response.content == b'Missing path parameter. Use {path:path} in the route definition.'


def test_fastapi_proxy_instrumentation_coverage_mock() -> None:
    mock_concurrency = mock.Mock()

    async def mock_run_in_threadpool(func: Any, *args: Any, **kwargs: Any) -> Any:
        if inspect.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    mock_concurrency.run_in_threadpool = mock.AsyncMock(side_effect=mock_run_in_threadpool)
    mock_responses = mock.Mock()

    class MockResponse:
        def __init__(self, content: Any, status_code: int, headers: dict[str, str] | None = None) -> None:
            self.content = content
            self.status_code = status_code
            self.headers = headers or {}

    mock_responses.Response = MockResponse

    with mock.patch.dict(
        sys.modules,
        {'starlette': mock.Mock(), 'starlette.concurrency': mock_concurrency, 'starlette.responses': mock_responses},
    ):
        request = mock.Mock()
        request.headers = {}

        async def mock_stream():
            yield b'12345'
            yield b'67890'

        request.stream = mock_stream
        request.path_params = {'path': 'v1/traces'}
        request.method = 'POST'

        with mock.patch('logfire.experimental.forwarding.forward_export_request') as mock_fwd:
            mock_fwd.return_value = ForwardExportRequestResponse(
                200, {'Content-Type': 'application/json'}, b'{"ok": true}'
            )

            import asyncio

            response = asyncio.run(logfire_proxy(request))

            assert response.status_code == 200
            assert response.content == b'{"ok": true}'
            assert mock_concurrency.run_in_threadpool.called

            mock_concurrency.run_in_threadpool.reset_mock()
            mock_fwd.reset_mock()

            request.headers = {'content-length': '10'}
            response2 = asyncio.run(logfire_proxy(request))

            assert response2.status_code == 200
            assert response2.content == b'{"ok": true}'
            assert mock_concurrency.run_in_threadpool.called
