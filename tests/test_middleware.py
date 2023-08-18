import contextlib

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from logfire.middlewares import LogfireFastAPIMiddleware


def test_fastapi_middleware_get_attributes():
    middleware = LogfireFastAPIMiddleware(None)
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
    assert middleware._get_attributes(request) == {
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


def test_fastapi_middleware(observe, exporter):
    def homepage(request):
        return PlainTextResponse('middleware test')

    app = Starlette(routes=[Route('/', homepage)], middleware=[Middleware(LogfireFastAPIMiddleware, observe=observe)])

    client = TestClient(app)
    response = client.get('/')

    assert response.status_code == 200
    assert response.text == 'middleware test'

    observe._telemetry.provider.force_flush()

    assert len(exporter.exported_spans)


def test_fastapi_middleware_with_lifespan(observe, exporter):
    startup_complete = False
    cleanup_complete = False

    @contextlib.asynccontextmanager
    async def lifespan(app):
        nonlocal startup_complete, cleanup_complete
        startup_complete = True
        yield
        cleanup_complete = True

    app = Starlette(lifespan=lifespan, middleware=[Middleware(LogfireFastAPIMiddleware, observe=observe)])

    with TestClient(app):
        assert startup_complete
        assert not cleanup_complete
    assert startup_complete
    assert cleanup_complete

    observe._telemetry.provider.force_flush()
    assert len(exporter.exported_spans) == 0
