import os

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocket

import logfire
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
        WebSocketRoute('/ws', websocket_endpoint),
    ]

    app = Starlette(routes=routes)
    try:
        logfire.instrument_starlette(app)
        yield app
    finally:
        StarletteInstrumentor.uninstrument_app(app)


@pytest.fixture()
def client(app: Starlette) -> TestClient:
    return TestClient(app)


def test_websocket(client: TestClient, exporter: TestExporter) -> None:
    with client.websocket_connect('/ws') as websocket:
        websocket.send_text('ping')
        data = websocket.receive_text()
        assert data == 'pong'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': '/ws websocket receive connect',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws websocket receive connect',
                    'asgi.event.type': 'websocket.connect',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws websocket send accept',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws websocket send accept',
                    'asgi.event.type': 'websocket.accept',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws websocket receive',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws websocket receive',
                    'http.status_code': 200,
                    'asgi.event.type': 'websocket.receive',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws websocket send',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws websocket send',
                    'http.status_code': 200,
                    'asgi.event.type': 'websocket.send',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws websocket send close',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws websocket send close',
                    'asgi.event.type': 'websocket.close',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '/ws',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '/ws',
                    'http.scheme': 'ws',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.target': '/ws',
                    'http.url': 'ws://testserver/ws',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/ws',
                    'http.status_code': 200,
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
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/secret/my_token',
                    'http.url': 'http://testserver/secret/my_token?foo=foo_val&password=hunter2',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/secret/{path_param}',
                    'http.request.header.testauthorization': ("[Redacted due to 'auth']",),
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
