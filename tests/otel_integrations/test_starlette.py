from __future__ import annotations

import importlib
import os
from unittest import mock

import pytest
from dirty_equals import IsAnyStr, IsFloat, IsInt
from inline_snapshot import snapshot
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from opentelemetry.trace import Span
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import Scope
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

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'logfire.metrics': {
                        'http.server.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.flavor': '1.1',
                                        'http.host': 'testserver',
                                        'http.method': 'GET',
                                        'http.scheme': 'http',
                                        'http.server_name': 'testserver',
                                        'http.target': '/secret/{path_param}',
                                        'net.host.port': 80,
                                    },
                                    'total': IsInt(),
                                }
                            ],
                            'total': IsInt(),
                        },
                        'http.server.request.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.route': '/secret/{path_param}',
                                        'network.protocol.version': '1.1',
                                        'url.scheme': 'http',
                                    },
                                    'total': IsFloat(),
                                }
                            ],
                            'total': IsFloat(),
                        },
                    },
                    'http.request.header.testauthorization': ("[Scrubbed due to 'auth']",),
                    'logfire.scrubbed': (
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


@pytest.mark.parametrize('record_send_receive', [False, True])
@pytest.mark.parametrize('manually_instrument', [False, True])
def test_global_starlette_instrumentation(
    exporter: TestExporter, monkeypatch: pytest.MonkeyPatch, record_send_receive: bool, manually_instrument: bool
) -> None:
    # Let monkeypatch restore the environment after capture_headers enables both settings.
    monkeypatch.setenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST', '')
    monkeypatch.setenv('OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_RESPONSE', '')

    def server_request_hook(span: Span, scope: Scope) -> None:
        span.set_attribute('test.path', scope['path'])

    logfire._internal.integrations.starlette.instrument_starlette(
        logfire.DEFAULT_LOGFIRE_INSTANCE,
        capture_headers=True,
        record_send_receive=record_send_receive,
        server_request_hook=server_request_hook,
    )
    try:
        # Obtain the patched class after global instrumentation, just as application code does.
        from starlette.applications import Starlette

        async def homepage(request: Request) -> PlainTextResponse:
            assert await request.body() == b'input'
            logfire.info('inside request handler')
            return PlainTextResponse('hello', headers={'x-test-response': 'out'})

        app = Starlette(routes=[Route('/hello/{name}', homepage, methods=['POST'])])
        if manually_instrument:
            logfire.instrument_starlette(app)

        with TestClient(app) as client:
            response = client.post('/hello/world', content=b'input', headers={'x-test-request': 'in'})
        assert response.status_code == 200
        assert response.text == 'hello'

        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        root_spans = [span for span in spans if span['name'] == 'POST /hello/{name}']
        assert len(root_spans) == 1
        root_span = root_spans[0]
        assert root_span['attributes']['http.route'] == '/hello/{name}'
        assert root_span['attributes']['http.status_code'] == 200
        assert root_span['attributes']['test.path'] == '/hello/world'
        assert root_span['attributes']['http.request.header.x_test_request'] == ('in',)
        assert root_span['attributes']['http.response.header.x_test_response'] == ('out',)
        log_span = next(span for span in spans if span['name'] == 'inside request handler')
        assert log_span['parent'] == root_span['context']
        io_spans = [span for span in spans if 'asgi.event.type' in span['attributes']]
        assert len(io_spans) == (3 if record_send_receive else 0)
        assert all(span['attributes']['logfire.level_num'] == 5 for span in io_spans)
        assert len(spans) == 2 + len(io_spans)
    finally:
        StarletteInstrumentor().uninstrument()


def test_global_starlette_websocket(exporter: TestExporter) -> None:
    logfire._internal.integrations.starlette.instrument_starlette(logfire.DEFAULT_LOGFIRE_INSTANCE)
    try:
        from starlette.applications import Starlette

        app = Starlette(routes=[WebSocketRoute('/ws/{name}', websocket_endpoint)])
        with TestClient(app) as client, client.websocket_connect('/ws/foo') as websocket:
            websocket.send_text('ping')
            assert websocket.receive_text() == 'pong'

        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': '/ws/{name}',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 2000000000,
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
                        'http.status_code': 200,
                        'http.response.status_code': 200,
                    },
                }
            ]
        )
    finally:
        StarletteInstrumentor().uninstrument()
