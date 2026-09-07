from __future__ import annotations

import os
import subprocess
import sys
from typing import Annotated, Any, cast
from unittest import mock

import pytest

pytest.importorskip(
    'pydantic',
    minversion='2.5',
    reason='Litestar 2.11 and later require Pydantic 2.5 or later.',
)

from inline_snapshot import snapshot
from litestar import Litestar, Request, Router, WebSocket, asgi, get, post, websocket
from litestar.params import Parameter
from opentelemetry.trace import Span
from starlette.testclient import TestClient
from starlette.types import ASGIApp

import logfire
from logfire.testing import TestExporter


@get('/users/{user_id:int}')
async def user(user_id: Annotated[int, Parameter()]) -> dict[str, int]:
    return {'user_id': user_id}


@get('/health')
async def health() -> dict[str, str]:
    return {'status': 'ok'}


@post('/echo')
async def echo(request: Request[Any, Any, Any]) -> dict[str, str]:
    return {'body': (await request.body()).decode()}


@get('/error')
async def error() -> None:
    raise RuntimeError('litestar test error')


@asgi(['/mounted', '/other'], is_mount=True, copy_scope=True)
async def mounted(scope: Any, receive: Any, send: Any) -> None:
    await send({'type': 'http.response.start', 'status': 200, 'headers': []})
    await send({'type': 'http.response.body', 'body': b'ok'})


@websocket('/chat')
async def chat(socket: WebSocket[Any, Any, Any]) -> None:
    await socket.accept()


def make_app(**instrument_kwargs: Any) -> ASGIApp:
    app = Litestar(route_handlers=[user, health, echo, error])
    return cast(ASGIApp, logfire.instrument_litestar(app, **instrument_kwargs))


@pytest.fixture(autouse=True)
def restore_header_capture_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST', raising=False)
    monkeypatch.delenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE', raising=False)


def test_routes(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/users/1').status_code == 200
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /users/{user_id}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /users/1',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/users/1',
                    'url.path': '/users/1',
                    'http.url': 'http://testserver/users/1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/users/{user_id}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /health',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_missing_route_has_method_only(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/missing').status_code == 404

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /missing',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/missing',
                    'url.path': '/missing',
                    'http.url': 'http://testserver/missing',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.status_code': 404,
                    'http.response.status_code': 404,
                    'logfire.level_num': 13,
                },
            }
        ]
    )


def test_handler_error_is_marked_as_an_error(exporter: TestExporter) -> None:
    with TestClient(make_app(), raise_server_exceptions=False) as client:
        assert client.get('/error').status_code == 500

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /error',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /error',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/error',
                    'url.path': '/error',
                    'http.url': 'http://testserver/error',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/error',
                    'http.status_code': 500,
                    'http.response.status_code': 500,
                    'error.type': '500',
                    'logfire.level_num': 17,
                },
            }
        ]
    )


def test_route_path_preserves_whitespace(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/health%20').status_code == 404

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == 'GET'
    assert 'http.route' not in span['attributes']


def test_root_path_is_included_in_canonical_route(exporter: TestExporter) -> None:
    with TestClient(make_app(), root_path='/api') as client:
        assert client.get('/api/users/1').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /api/users/{user_id}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /api/users/1',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/api/users/1',
                    'url.path': '/api/users/1',
                    'http.url': 'http://testserver/api/users/1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/api/users/{user_id}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )


def test_mounted_app_uses_canonical_mount_route(exporter: TestExporter) -> None:
    app = cast(ASGIApp, logfire.instrument_litestar(Litestar(route_handlers=[mounted])))
    with TestClient(app) as client:
        assert client.get('/mounted/attacker-controlled').status_code == 200

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == 'GET /mounted'
    assert span['attributes']['http.route'] == '/mounted'


def test_websocket_route_has_no_leading_space(exporter: TestExporter) -> None:
    app = cast(ASGIApp, logfire.instrument_litestar(Litestar(route_handlers=[chat])))
    with TestClient(app) as client:
        with client.websocket_connect('/chat'):
            pass

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == '/chat'
    assert span['attributes']['http.route'] == '/chat'


@pytest.mark.parametrize('root_path', ['', '/api'])
def test_root_route(exporter: TestExporter, root_path: str) -> None:
    @get('/')
    async def root() -> str:
        return 'ok'

    app = cast(ASGIApp, logfire.instrument_litestar(Litestar(route_handlers=[root])))
    with TestClient(app, root_path=root_path) as client:
        assert client.get(root_path or '/').status_code == 200

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == f'GET {root_path}/'
    assert span['attributes']['http.route'] == f'{root_path}/'


def test_custom_span_details(exporter: TestExporter) -> None:
    def span_details(scope: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        return 'custom', {'custom.path': scope['path']}

    with TestClient(make_app(default_span_details=span_details)) as client:
        assert client.get('/health').status_code == 200

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == 'custom'
    assert span['attributes']['custom.path'] == '/health'


def test_excluded_urls(exporter: TestExporter) -> None:
    with TestClient(make_app(excluded_urls='health')) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/users/1').status_code == 200

    [span] = exporter.exported_spans_as_dict()
    assert span['name'] == 'GET /users/{user_id}'


def test_lifespan_is_forwarded() -> None:
    calls: list[str] = []

    async def startup() -> None:
        calls.append('startup')

    async def shutdown() -> None:
        calls.append('shutdown')

    app = cast(
        ASGIApp,
        logfire.instrument_litestar(Litestar(route_handlers=[health], on_startup=[startup], on_shutdown=[shutdown])),
    )
    with TestClient(app) as client:
        assert calls == ['startup']
        assert client.get('/health').status_code == 200
    assert calls == ['startup', 'shutdown']


def test_hooks_are_forwarded(exporter: TestExporter) -> None:
    calls: list[str] = []

    def server_hook(span: Span, scope: dict[str, Any]) -> None:
        calls.append('server')

    def client_request_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]) -> None:
        calls.append('request')

    def client_response_hook(span: Span, scope: dict[str, Any], message: dict[str, Any]) -> None:
        calls.append('response')

    with TestClient(
        make_app(
            server_request_hook=server_hook,
            client_request_hook=client_request_hook,
            client_response_hook=client_response_hook,
        )
    ) as client:
        assert client.post('/echo', content='test').status_code == 201

    assert calls[0] == 'server'
    assert 'request' in calls
    assert calls.count('response') >= 1
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'POST /echo',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/echo',
                    'url.path': '/echo',
                    'http.url': 'http://testserver/echo',
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/echo',
                    'http.status_code': 201,
                    'http.response.status_code': 201,
                },
            }
        ]
    )


def test_record_send_receive_default(exporter: TestExporter) -> None:
    with TestClient(make_app()) as client:
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )


def test_record_send_receive_enabled(exporter: TestExporter) -> None:
    with TestClient(make_app(record_send_receive=True)) as client:
        assert client.get('/health').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health http send response.start',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health http send response.start',
                    'asgi.event.type': 'http.response.start',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /health http send response.body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health http send response.body',
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_capture_headers(exporter: TestExporter) -> None:
    with TestClient(make_app(capture_headers=True)) as client:
        assert client.get('/health', headers={'x-test-header': 'value'}).status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /health',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /health',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/health',
                    'url.path': '/health',
                    'http.url': 'http://testserver/health',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/health',
                    'http.request.header.host': ('testserver',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept_encoding': ('gzip, deflate, zstd',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user_agent': ('testclient',),
                    'http.request.header.x_test_header': ('value',),
                    'http.response.header.content_type': ('application/json',),
                    'http.response.header.content_length': ('15',),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            }
        ]
    )
    assert os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST'] == '.*'
    assert os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE'] == '.*'


@pytest.mark.parametrize('missing_module', ['litestar', 'opentelemetry.instrumentation.asgi'])
def test_missing_dependency(missing_module: str) -> None:
    app = Litestar(route_handlers=[health])
    modules = {
        name: module
        for name, module in sys.modules.items()
        if name not in {'logfire._internal.integrations.litestar', 'logfire._internal.integrations.asgi', 'litestar'}
        and not name.startswith('litestar.')
    }
    with mock.patch.dict('sys.modules', {**modules, missing_module: None}, clear=True):
        with pytest.raises(RuntimeError, match=r"pip install 'logfire\[litestar\]'") as exc_info:
            logfire.instrument_litestar(app, capture_headers=True)
        assert isinstance(exc_info.value.__cause__, ImportError)

    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST' not in os.environ
    assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE' not in os.environ


def test_nested_mounts_use_resolved_paths(exporter: TestExporter) -> None:
    app = cast(
        ASGIApp,
        logfire.instrument_litestar(Litestar(route_handlers=[Router(path='/api', route_handlers=[health, mounted])])),
    )
    with TestClient(app, root_path='/proxy') as client:
        assert client.get('/proxy/api/mounted/one').status_code == 200
        assert client.get('/proxy/api/mounted/two').status_code == 200
        assert client.get('/proxy/api/other/three').status_code == 200

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET /proxy/api/mounted',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /proxy/api/mounted/one',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/proxy/api/mounted/one',
                    'url.path': '/proxy/api/mounted/one',
                    'http.url': 'http://testserver/proxy/api/mounted/one',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/proxy/api/mounted',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /proxy/api/mounted',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /proxy/api/mounted/two',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/proxy/api/mounted/two',
                    'url.path': '/proxy/api/mounted/two',
                    'http.url': 'http://testserver/proxy/api/mounted/two',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/proxy/api/mounted',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /proxy/api/other',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /proxy/api/other/three',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/proxy/api/other/three',
                    'url.path': '/proxy/api/other/three',
                    'http.url': 'http://testserver/proxy/api/other/three',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/proxy/api/other',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_missing_asgi_dependency_in_fresh_process() -> None:
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            """
import os
import sys
from litestar import Litestar

app = Litestar([])
sys.modules['opentelemetry.instrumentation.asgi'] = None

import logfire

logfire.configure(send_to_logfire=False, console=False)
try:
    logfire.instrument_litestar(app, capture_headers=True)
except RuntimeError as exc:
    assert "pip install 'logfire[litestar]'" in str(exc)
else:
    raise AssertionError('Expected installation guidance')
assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST' not in os.environ
assert 'OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE' not in os.environ
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
