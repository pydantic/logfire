from __future__ import annotations

from typing import TYPE_CHECKING
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
        assert kwargs['headers']['Authorization'] == 'Bearer test_token'
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
    fastapi = pytest.importorskip('fastapi')
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
        assert kwargs['headers']['Authorization'] == 'Bearer test_token'


def test_fastapi_proxy_size_limit() -> None:
    fastapi = pytest.importorskip('fastapi')
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
    fastapi = pytest.importorskip('fastapi')
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
