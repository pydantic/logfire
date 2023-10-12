import contextlib

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from logfire import Logfire
from logfire.integrations.asgi import LogfireMiddleware
from logfire.testing import TestExporter


def test_fastapi_middleware_get_attributes():
    request = Request(
        {
            'type': 'http',
            'path': '/test',
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'https',
            'client': ('127.0.0.1', 8080),
            'server': ('192.168.1.2', 443),
        }
    )
    assert LogfireMiddleware._get_attributes(request) == {
        'http.scheme': 'https',
        'http.host': '192.168.1.2:443',
        'net.host.port': 443,
        'http.flavor': '1.1',
        'http.target': '/test',
        'http.url': 'https://192.168.1.2:443/test',
        'http.method': 'GET',
        'net.peer.ip': '127.0.0.1',
        'net.peer.port': 8080,
    }


def test_fastapi_middleware(logfire: Logfire, exporter: TestExporter):
    def homepage(request: Request):
        return PlainTextResponse('middleware test')

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(LogfireMiddleware, logfire=logfire)])

    client = TestClient(app)
    response = client.get('/')

    assert response.status_code == 200
    assert response.text == 'middleware test'

    assert len(exporter.exported_spans)


def test_fastapi_middleware_with_lifespan(logfire: Logfire, exporter: TestExporter):
    startup_complete = False
    cleanup_complete = False

    @contextlib.asynccontextmanager
    async def lifespan(app: ASGIApp):
        nonlocal startup_complete, cleanup_complete
        startup_complete = True
        yield
        cleanup_complete = True

    app = Starlette(lifespan=lifespan, middleware=[Middleware(LogfireMiddleware, logfire=logfire)])

    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

    assert len(exporter.exported_spans) == 0
