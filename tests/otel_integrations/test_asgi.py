from __future__ import annotations

import contextlib

from inline_snapshot import snapshot
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

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(OpenTelemetryMiddleware)])  # type: ignore

    client = TestClient(app)
    with logfire.span('outside request handler'):
        headers: dict[str, str] = {}
        inject(headers)
        response = client.get('/', headers=headers)

    assert response.status_code == 200
    assert response.text == 'middleware test'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'inside request handler',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'inside request handler',
                    'logfire.msg': 'inside request handler',
                    'code.lineno': 123,
                    'code.filepath': 'test_asgi.py',
                    'code.function': 'homepage',
                },
            },
            {
                'name': 'GET / http send response.start',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.start',
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET / http send response.body',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
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
                    'code.lineno': 123,
                    'code.filepath': 'test_asgi.py',
                    'code.function': 'test_asgi_middleware',
                    'logfire.msg_template': 'outside request handler',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'outside request handler',
                },
            },
        ]
    )


def test_asgi_middleware_with_lifespan(exporter: TestExporter):
    startup_complete = False
    cleanup_complete = False

    @contextlib.asynccontextmanager
    async def lifespan(app: ASGIApp):
        nonlocal startup_complete, cleanup_complete
        startup_complete = True
        yield
        cleanup_complete = True

    app = Starlette(lifespan=lifespan, middleware=[Middleware(OpenTelemetryMiddleware)])  # type: ignore

    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []
