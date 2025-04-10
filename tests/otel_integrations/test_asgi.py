from __future__ import annotations

import contextlib

from inline_snapshot import snapshot
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

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(logfire.instrument_asgi)])  # type: ignore

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
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'server.address': 'testserver',
                    'client.address': 'testclient',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                    'url.path': '/',
                    'http.url': 'http://testserver/',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_asgi.py',
                    'code.function': 'test_asgi_middleware',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'span',
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

    app = Starlette(lifespan=lifespan, middleware=[Middleware(logfire.instrument_asgi)])  # type: ignore

    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == []
