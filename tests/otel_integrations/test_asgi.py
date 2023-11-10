import contextlib

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.propagate import inject
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp

import logfire
from logfire.testing import TestExporter


def test_asgi_middleware(exporter: TestExporter) -> None:
    # note: this also serves as a unit test of our integration with otel's various integrations

    def homepage(_: Request):
        logfire.info('inside request handler')
        return PlainTextResponse('middleware test')

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(OpenTelemetryMiddleware)])

    client = TestClient(app)
    with logfire.span('outside request handler'):
        headers = {}
        inject(headers)
        response = client.get('/', headers=headers)

    assert response.status_code == 200
    assert response.text == 'middleware test'

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'inside request handler',
            'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 3000000000,
            'end_time': 3000000000,
            'attributes': {
                'logfire.span_type': 'log',
                'logfire.level': 'info',
                'logfire.msg_template': 'inside request handler',
                'logfire.msg': 'inside request handler',
                'code.filepath': 'test_asgi.py',
                'code.lineno': 123,
                'code.function': 'homepage',
            },
        },
        {
            'name': 'GET / http send',
            'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 4000000000,
            'end_time': 5000000000,
            'attributes': {'logfire.span_type': 'span', 'http.status_code': 200, 'type': 'http.response.start'},
        },
        {
            'name': 'GET / http send',
            'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 6000000000,
            'end_time': 7000000000,
            'attributes': {'logfire.span_type': 'span', 'type': 'http.response.body'},
        },
        {
            'name': 'GET /',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 8000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'http.scheme': 'http',
                'http.host': 'testserver',
                'net.host.port': 80,
                'http.flavor': '1.1',
                'http.target': '/',
                'http.url': 'http://testserver/',
                'http.method': 'GET',
                'http.server_name': 'testserver',
                'http.user_agent': 'testclient',
                'net.peer.ip': 'testclient',
                'net.peer.port': 50000,
                'http.status_code': 200,
            },
        },
        {
            'name': 'outside request handler',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 9000000000,
            'attributes': {
                'code.filepath': 'test_asgi.py',
                'code.lineno': 123,
                'code.function': 'test_asgi_middleware',
                'logfire.msg_template': 'outside request handler',
                'logfire.span_type': 'span',
                'logfire.msg': 'outside request handler',
            },
        },
    ]


def test_asgi_middleware_with_lifespan(exporter: TestExporter):
    startup_complete = False
    cleanup_complete = False

    @contextlib.asynccontextmanager
    async def lifespan(app: ASGIApp):
        nonlocal startup_complete, cleanup_complete
        startup_complete = True
        yield
        cleanup_complete = True

    app = Starlette(lifespan=lifespan, middleware=[Middleware(OpenTelemetryMiddleware)])

    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

    assert exporter.exported_spans_as_dict(_include_start_spans=True) == []
