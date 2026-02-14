from __future__ import annotations

import asyncio
import inspect
import sys
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
import requests

if TYPE_CHECKING:
    pass

import logfire
from logfire import ForwardRequestResponse


def test_forward_request_logic() -> None:
    # Configure with a token
    logfire.configure(token='test_token', send_to_logfire=False)

    with mock.patch('requests.request') as mock_request:
        mock_request.return_value.status_code = 200
        mock_request.return_value.headers = {'Content-Type': 'application/json', 'Content-Length': '123'}
        mock_request.return_value.content = b'{"status": "ok"}'

        # Test valid request
        response = logfire.forward_request(
            'POST', '/v1/traces', {'Content-Type': 'application/x-protobuf', 'Host': 'example.com'}, b'data'
        )

        assert isinstance(response, ForwardRequestResponse)
        assert response.status_code == 200
        assert response.content == b'{"status": "ok"}'
        assert response.headers['Content-Type'] == 'application/json'
        # Content-Length should be removed from response headers by our logic
        assert 'Content-Length' not in response.headers

        mock_request.assert_called_once()
        _, kwargs = mock_request.call_args
        assert kwargs['method'] == 'POST'
        assert kwargs['url'] == 'https://logfire-us.pydantic.dev/v1/traces'
        assert kwargs['headers']['Authorization'] == 'test_token'
        assert kwargs['headers']['Content-Type'] == 'application/x-protobuf'
        assert 'Host' not in kwargs['headers']
        assert kwargs['data'] == b'data'


def test_forward_request_invalid_path() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    response = logfire.forward_request('POST', '/invalid', {}, b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_request_path_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    # Attempt to traverse up from traces to an invalid path
    response = logfire.forward_request('POST', '/v1/traces/../secret', {}, b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_request_exception_handling() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    with mock.patch('requests.request', side_effect=requests.RequestException('connection failure')):
        response = logfire.forward_request('POST', '/v1/traces', {}, b'')

        assert response.status_code == 502
        # Ensure we return the generic error, not the specific exception string
        assert response.content == b'Upstream service error'


def test_fastapi_proxy_instrumentation() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    logfire.instrument_fastapi_proxy(app)

    client = TestClient(app)

    with mock.patch('requests.request') as mock_request:
        mock_request.return_value.status_code = 202
        mock_request.return_value.headers = {}
        mock_request.return_value.content = b''

        response = client.post(
            '/logfire-proxy/v1/traces', content=b'trace_data', headers={'Content-Type': 'application/x-protobuf'}
        )

        assert response.status_code == 202

        mock_request.assert_called_once()
        _, kwargs = mock_request.call_args
        assert kwargs['url'].endswith('/v1/traces')
        assert kwargs['data'] == b'trace_data'
        assert kwargs['headers']['Authorization'] == 'test_token'


def test_fastapi_proxy_size_limit() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    # Set a small limit for testing
    logfire.instrument_fastapi_proxy(app, max_body_size=10)

    client = TestClient(app)

    # Content-Length check
    response = client.post(
        '/logfire-proxy/v1/traces', content=b'12345678901', headers={'Content-Type': 'application/json'}
    )
    assert response.status_code == 413
    assert response.content == b'Payload too large'


def test_fastapi_proxy_custom_prefix() -> None:
    fastapi = pytest.importorskip('fastapi', exc_type=ImportError)
    TestClient = pytest.importorskip('starlette.testclient').TestClient
    FastAPI = fastapi.FastAPI

    app = FastAPI()
    logfire.configure(token='test_token', send_to_logfire=False)

    logfire.instrument_fastapi_proxy(app, prefix='/custom-proxy')

    client = TestClient(app)

    with mock.patch('requests.request') as mock_request:
        mock_request.return_value.status_code = 200
        mock_request.return_value.headers = {}
        mock_request.return_value.content = b''

        response = client.post('/custom-proxy/v1/logs', content=b'')
        assert response.status_code == 200
        assert mock_request.call_args[1]['url'].endswith('/v1/logs')


def test_forward_request_percent_encoded_traversal() -> None:
    logfire.configure(token='test_token', send_to_logfire=False)

    # %2e%2e is ..
    # /v1/traces/%2e%2e/secret -> /v1/traces/../secret -> /v1/secret (rejected)
    response = logfire.forward_request('POST', '/v1/traces/%2e%2e/secret', {}, b'')
    assert response.status_code == 400
    assert b'Invalid path' in response.content


def test_forward_request_multi_token() -> None:
    # Test handling of list of tokens
    logfire.configure(token=['tok1', 'tok2'], send_to_logfire=False)

    with mock.patch('requests.request') as mock_req:
        mock_req.return_value.status_code = 200
        mock_req.return_value.headers = {}
        mock_req.return_value.content = b''

        logfire.forward_request('POST', '/v1/traces', {}, b'')

        # Should use first token
        headers = mock_req.call_args[1]['headers']
        assert headers['Authorization'] == 'tok1'


def test_forward_request_missing_token() -> None:
    # Test handling of missing token
    logfire.configure(token='tok', send_to_logfire=False)

    # Access the singleton instance via the bound method to correctly patch the config
    instance = logfire.forward_request.__self__

    with mock.patch.object(instance.config, 'token', None):
        response = logfire.forward_request('POST', '/v1/traces', {}, b'')
        assert response.status_code == 500
        assert b'not configured' in response.content


def test_fastapi_proxy_instrumentation_coverage_mock() -> None:

    # Create mocks
    mock_concurrency = mock.Mock()

    # run_in_threadpool is awaited in the source, so it must return an awaitable (coroutine)
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
        app = mock.Mock()

        # Call instrumentation - this defines the inner function using our mocks
        logfire.instrument_fastapi_proxy(app)

        # Extract the handler
        assert app.add_route.called
        handler = app.add_route.call_args[0][1]

        # Prepare request mock
        request = mock.Mock()
        request.headers = {}
        request.body = mock.AsyncMock(return_value=b'1234567890')
        request.path_params = {'path': 'v1/traces'}
        request.method = 'POST'

        # Mock forward_request to return success
        with mock.patch('logfire.Logfire.forward_request') as mock_fwd:
            mock_fwd.return_value = logfire.ForwardRequestResponse(
                200, {'Content-Type': 'application/json'}, b'{"ok": true}'
            )

            # Execute handler
            response = asyncio.run(handler(request))

            # Verify response
            assert response.status_code == 200
            assert response.content == b'{"ok": true}'
            assert response.headers == {'Content-Type': 'application/json'}

            # Verify our mocks were actually hit
            assert mock_concurrency.run_in_threadpool.called
