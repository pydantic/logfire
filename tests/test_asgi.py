import contextlib

from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from logfire.testing import TestExporter


def test_fastapi_middleware(exporter: TestExporter) -> None:
    # note: this also serves as a unit test of our integration with otel's various integrations

    def homepage(_: Request):
        return PlainTextResponse('middleware test')

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(OpenTelemetryMiddleware)])

    client = TestClient(app)
    response = client.get('/')

    assert response.status_code == 200
    assert response.text == 'middleware test'

    # insert_assert(exporter.exported_spans_as_dict(map_times=False, map_span_ids=False, map_trace_ids=False))
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'GET / (start)',
            'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 1000000000,
            'end_time': 1000000000,
            'attributes': {
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
                'logfire.span_type': 'start_span',
                'logfire.start_parent_id': '0',
            },
        },
        {
            'name': 'GET / http send (start)',
            'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 2000000000,
            'attributes': {'logfire.span_type': 'start_span', 'logfire.start_parent_id': '1'},
        },
        {
            'name': 'GET / http send',
            'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 2000000000,
            'end_time': 3000000000,
            'attributes': {'logfire.span_type': 'span', 'http.status_code': 200, 'type': 'http.response.start'},
        },
        {
            'name': 'GET / http send (start)',
            'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
            'start_time': 4000000000,
            'end_time': 4000000000,
            'attributes': {'logfire.span_type': 'start_span', 'logfire.start_parent_id': '1'},
        },
        {
            'name': 'GET / http send',
            'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
            'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'start_time': 4000000000,
            'end_time': 5000000000,
            'attributes': {'logfire.span_type': 'span', 'type': 'http.response.body'},
        },
        {
            'name': 'GET /',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 6000000000,
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
    ]


def test_fastapi_middleware_with_lifespan(exporter: TestExporter):
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

    assert exporter.exported_spans_as_dict() == []
