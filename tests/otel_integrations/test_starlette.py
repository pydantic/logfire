from __future__ import annotations

import importlib
import os
from unittest import mock

import pytest
from dirty_equals import IsAnyStr, IsJson
from inline_snapshot import snapshot
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

import logfire
import logfire._internal.integrations.starlette
from logfire.testing import TestExporter


async def secret(path_param: str):
    raise ValueError('test exception')


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    assert (await websocket.receive_text()) == 'ping'
    await websocket.send_text('pong')
    await websocket.close()


@pytest.fixture()
def app():
    routes = [
        Route('/secret/{path_param}', secret),
        WebSocketRoute('/ws/{name}', websocket_endpoint),
    ]

    app = Starlette(routes=routes)
    try:
        logfire.instrument_starlette(app, capture_headers=True, record_send_receive=True)
        yield app
    finally:
        StarletteInstrumentor.uninstrument_app(app)
        del os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST']
        del os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE']


@pytest.fixture()
def client(app: Starlette) -> TestClient:
    return TestClient(app)


def test_websocket(client: TestClient, exporter: TestExporter) -> None:
    with client.websocket_connect('/ws/foo') as websocket:
        websocket.send_text('ping')
        data = websocket.receive_text()
        assert data == 'pong'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': '/ws/{name} websocket receive connect',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/{name} websocket receive connect',
                    'asgi.event.type': 'websocket.connect',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws/{name} websocket send accept',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/{name} websocket send accept',
                    'asgi.event.type': 'websocket.accept',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws/{name} websocket receive',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/{name} websocket receive',
                    'http.status_code': 200,
                    'asgi.event.type': 'websocket.receive',
                    'http.response.status_code': 200,
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws/{name} websocket send',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/{name} websocket send',
                    'http.status_code': 200,
                    'asgi.event.type': 'websocket.send',
                    'logfire.level_num': 5,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': '/ws/{name} websocket send close',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/{name} websocket send close',
                    'asgi.event.type': 'websocket.close',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws/{name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws/foo',
                    'http.scheme': 'ws',
                    'url.scheme': 'ws',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.target': '/ws/foo',
                    'url.path': '/ws/foo',
                    'http.url': 'ws://testserver/ws/foo',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/ws/{name}',
                    'http.request.header.host': ('testserver',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept_encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.request.header.user_agent': ('testclient',),
                    'http.request.header.connection': ('upgrade',),
                    'http.request.header.sec_websocket_key': ('testserver==',),
                    'http.request.header.sec_websocket_version': ('13',),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_scrubbing(client: TestClient, exporter: TestExporter) -> None:
    os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST'] = 'TestAuthorization'

    with pytest.raises(ValueError):
        client.get(
            '/secret/my_token?foo=foo_val&password=hunter2',
            headers={'TestAuthorization': 'Bearer abcd'},
        )

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET /secret/{path_param}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /secret/my_token ? foo='foo_val' & password='hunter2'",
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/secret/my_token',
                    'url.path': '/secret/my_token',
                    'url.query': 'foo=foo_val&password=hunter2',
                    'http.url': 'http://testserver/secret/my_token?foo=foo_val&password=hunter2',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/secret/{path_param}',
                    'logfire.level_num': 17,
                    'http.request.header.testauthorization': ("[Scrubbed due to 'auth']",),
                    'logfire.scrubbed': IsJson(
                        [{'path': ['attributes', 'http.request.header.testauthorization'], 'matched_substring': 'auth'}]
                    ),
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test exception',
                            'exception.stacktrace': 'ValueError: test exception',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.starlette': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.starlette)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_starlette()` requires the `opentelemetry-instrumentation-starlette` package.
You can install this with:
    pip install 'logfire[starlette]'\
""")
