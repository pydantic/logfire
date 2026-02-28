from __future__ import annotations

import inspect
import sys
from typing import Any
from unittest import mock

import pytest
import requests

import logfire
from logfire.experimental.forwarding import ForwardExportRequestResponse, forward_export_request, logfire_proxy


def test_forward_export_request_logic() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    with mock.patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.headers = {
            'Content-Type': 'application/json',
            'Content-Length': '123',
            'Set-Cookie': 'secret=value',
        }
        mock_post.return_value.content = b'{"status": "ok"}'

        response = forward_export_request(
            path='/v1/traces',
            headers={'Content-Type': 'application/x-protobuf', 'Host': 'example.com'},
            body=b'data',
        )

        assert isinstance(response, ForwardExportRequestResponse)
        assert response.status_code == 200
        assert response.content == b'{"status": "ok"}'
        assert response.headers['Content-Type'] == 'application/json'
        assert 'Content-Length' not in response.headers
        assert 'Set-Cookie' not in response.headers

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs['url'] == 'https://logfire-us.pydantic.dev/v1/traces'
        assert kwargs['headers']['Authorization'] == 'test_token'
        assert kwargs['headers']['Content-Type'] == 'application/x-protobuf'
        assert 'Host' not in kwargs['headers']
        assert kwargs['data'] == b'data'


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

    with mock.patch('requests.post', side_effect=requests.RequestException('connection failure')):
        response = forward_export_request(path='/v1/traces', headers={}, body=b'')
        assert response.status_code == 502
        assert response.content == b'Upstream service error'


def test_fastapi_proxy_handler() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    app.add_route('/logfire-proxy/{path:path}', logfire_proxy, methods=['POST'])

    client = TestClient(app)

    with mock.patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 202
        mock_post.return_value.headers = {}
        mock_post.return_value.content = b''

        response = client.post(
            '/logfire-proxy/v1/traces', content=b'trace_data', headers={'Content-Type': 'application/x-protobuf'}
        )

        assert response.status_code == 202

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert kwargs['url'].endswith('/v1/traces')
        assert kwargs['data'] == b'trace_data'


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

    with mock.patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.headers = {}
        mock_post.return_value.content = b''

        forward_export_request(path='/v1/traces', headers={}, body=b'')
        headers = mock_post.call_args[1]['headers']
        assert headers['Authorization'] == 'tok1'


def test_forward_export_request_missing_token() -> None:
    logfire.configure(token='tok', send_to_logfire=False)
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch.object(logfire_instance.config, 'token', None):
        response = forward_export_request(path='/v1/traces', headers={}, body=b'', logfire_instance=logfire_instance)
        assert response.status_code == 500
        assert b'not configured' in response.content


def test_forward_export_request_explicit_instance() -> None:
    """Test that an explicit instance can be passed to forward_export_request."""
    logfire.configure(token='explicit_token', send_to_logfire=False)

    explicit_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    with mock.patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.headers = {}
        mock_post.return_value.content = b'ok'

        response = forward_export_request(path='/v1/traces', headers={}, body=b'', logfire_instance=explicit_instance)

        assert response.status_code == 200

        headers = mock_post.call_args[1]['headers']
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
