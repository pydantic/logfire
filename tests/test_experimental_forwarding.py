from __future__ import annotations

import inspect
import sys
from typing import Any
from unittest import mock

import pytest
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire
import logfire.experimental.forwarding as forwarding
from logfire.experimental.forwarding import ForwardExportRequestResponse, forward_export_request, logfire_proxy
from logfire.version import VERSION


class FakeRetryer:
    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.tasks: list[tuple[bytes, dict[str, Any]]] = []

    def add_task(self, data: bytes, kwargs: dict[str, Any]) -> bool:
        self.tasks.append((data, kwargs))
        return self.accepted


def test_forward_export_request_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    retryer = FakeRetryer()
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    response = forward_export_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf', 'Host': 'example.com'},
        body=b'data',
    )

    assert isinstance(response, ForwardExportRequestResponse)
    assert response.status_code == 200
    assert response.content == b''
    assert response.headers['Content-Type'] == 'application/x-protobuf'

    assert retryer.tasks == [
        (
            b'data',
            {
                'url': 'https://logfire-us.pydantic.dev/v1/traces',
                'headers': {
                    'Content-Type': 'application/x-protobuf',
                    'User-Agent': f'logfire-proxy/{VERSION}',
                    'Authorization': 'test_token',
                },
                'stream': False,
                'timeout': 5.0,
            },
        )
    ]


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


def test_forward_export_request_queue_full_returns_partial_success(monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    retryer = FakeRetryer(accepted=False)
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    response = forward_export_request(path='/v1/traces', headers={}, body=b'data')

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/x-protobuf'
    otlp_response = ExportTraceServiceResponse.FromString(response.content)
    assert otlp_response.partial_success.error_message == (
        'Logfire proxy retry queue is full or unavailable; telemetry was dropped.'
    )


@pytest.mark.parametrize(
    ('path', 'response_type'),
    [
        ('/v1/logs', ExportLogsServiceResponse),
        ('/v1/metrics', ExportMetricsServiceResponse),
    ],
)
def test_forward_export_request_empty_body_returns_signal_success(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    response_type: type[ExportLogsServiceResponse] | type[ExportMetricsServiceResponse],
) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    retryer = FakeRetryer()
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    response = forward_export_request(path=path, headers={}, body=None)

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/x-protobuf'
    assert response.content == response_type().SerializeToString()
    assert not retryer.tasks


@pytest.mark.parametrize(
    ('path', 'response_type'),
    [
        ('/v1/logs', ExportLogsServiceResponse),
        ('/v1/metrics', ExportMetricsServiceResponse),
    ],
)
def test_forward_export_request_queue_full_returns_signal_partial_success(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    response_type: type[ExportLogsServiceResponse] | type[ExportMetricsServiceResponse],
) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    retryer = FakeRetryer(accepted=False)
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    response = forward_export_request(path=path, headers={}, body=b'data')

    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/x-protobuf'
    otlp_response = response_type.FromString(response.content)
    assert otlp_response.partial_success.error_message == (
        'Logfire proxy retry queue is full or unavailable; telemetry was dropped.'
    )


def test_get_forwarding_retryer_recreates_closed_retryer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(forwarding, '_forwarding_retryer', None)
    monkeypatch.setattr(forwarding, '_forwarding_retryer_shutdown', False)
    get_forwarding_retryer = getattr(forwarding, '_get_forwarding_retryer')

    retryer = get_forwarding_retryer()
    assert retryer is not None
    assert retryer.initial_delay == 0
    assert retryer.success_delay == 0
    assert get_forwarding_retryer() is retryer

    retryer.close()
    new_retryer = get_forwarding_retryer()
    assert new_retryer is not None
    assert new_retryer is not retryer
    assert new_retryer.initial_delay == 0
    assert new_retryer.success_delay == 0
    new_retryer.close()


def test_forwarding_retryer_does_not_recreate_after_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.configure(token='test_token', send_to_logfire=False)
    monkeypatch.setattr(forwarding, '_forwarding_retryer', None)
    monkeypatch.setattr(forwarding, '_forwarding_retryer_shutdown', False)
    get_forwarding_retryer = getattr(forwarding, '_get_forwarding_retryer')
    close_forwarding_retryer = getattr(forwarding, '_close_forwarding_retryer')

    retryer = get_forwarding_retryer()
    assert retryer is not None

    close_forwarding_retryer()

    assert retryer.closed
    assert get_forwarding_retryer() is None

    response = forward_export_request(path='/v1/traces', headers={}, body=b'data')
    assert response.status_code == 200
    otlp_response = ExportTraceServiceResponse.FromString(response.content)
    assert otlp_response.partial_success.error_message == (
        'Logfire proxy retry queue is full or unavailable; telemetry was dropped.'
    )


def test_fastapi_proxy_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)
    retryer = FakeRetryer()
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    app.add_route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST'])

    client = TestClient(app)

    response = client.post(
        '/logfire-proxy/v1/traces', content=b'trace_data', headers={'Content-Type': 'application/x-protobuf'}
    )

    assert response.status_code == 200
    assert response.content == b''

    assert len(retryer.tasks) == 1
    data, kwargs = retryer.tasks[0]
    assert data == b'trace_data'
    assert kwargs['url'].endswith('/v1/traces')


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


def test_forward_export_request_multi_token(monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.configure(token=['tok1', 'tok2'], send_to_logfire=False)

    retryer = FakeRetryer()
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    forward_export_request(path='/v1/traces', headers={}, body=b'data')
    headers = retryer.tasks[0][1]['headers']
    assert headers['Authorization'] == 'tok1'


def test_forward_export_request_missing_token() -> None:
    logfire.configure(token='tok', send_to_logfire=False)
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch.object(logfire_instance.config, 'token', None):
        response = forward_export_request(path='/v1/traces', headers={}, body=b'', logfire_instance=logfire_instance)
        assert response.status_code == 403
        assert b'not configured' in response.content


def test_forward_export_request_explicit_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that an explicit instance can be passed to forward_export_request."""
    logfire.configure(token='explicit_token', send_to_logfire=False)
    retryer = FakeRetryer()
    monkeypatch.setattr('logfire.experimental.forwarding._get_forwarding_retryer', lambda: retryer)

    explicit_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    response = forward_export_request(path='/v1/traces', headers={}, body=b'data', logfire_instance=explicit_instance)

    assert response.status_code == 200

    headers = retryer.tasks[0][1]['headers']
    assert headers['Authorization'] == 'explicit_token'


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
