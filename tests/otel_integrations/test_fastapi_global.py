from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.trace import Span
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.testclient import TestClient
from starlette.types import Scope
from starlette.websockets import WebSocket

pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)

import fastapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

import logfire
from logfire._internal.integrations.fastapi import OncePerRequest, instrument_fastapi
from logfire.testing import TestExporter


@pytest.mark.parametrize('extra_spans', [False, True])
@pytest.mark.parametrize('excluded_urls', ['/health', ['/health']])
def test_global_fastapi_enrichment(exporter: TestExporter, extra_spans: bool, excluded_urls: str | list[str]) -> None:
    original_fastapi = fastapi.FastAPI

    def server_request_hook(span: Span, scope: Scope) -> None:
        span.set_attribute('test.path', scope['path'])

    with instrument_fastapi(
        logfire.DEFAULT_LOGFIRE_INSTANCE,
        extra_spans=extra_spans,
        excluded_urls=excluded_urls,
        server_request_hook=server_request_hook,
    ):
        app = fastapi.FastAPI()

        @app.get('/items/{item_id}')
        async def homepage(item_id: int, q: str = 'hello') -> dict[str, int | str]:
            logfire.info('inside request handler')
            return {'item_id': item_id, 'q': q}

        @app.get('/health')
        async def health() -> str:
            return 'ok'

        with TestClient(app) as client:
            assert client.get('/items/123?q=world').json() == {'item_id': 123, 'q': 'world'}
            assert client.get('/items/invalid').status_code == 422
            assert client.get('/health').status_code == 200

        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        roots = [span for span in spans if span['name'] == 'GET /items/{item_id}']
        assert len(roots) == 2
        attributes = roots[0]['attributes']
        assert attributes['fastapi.route.name'] == 'homepage'
        assert attributes['fastapi.arguments.values'] == {'item_id': 123, 'q': 'world'}
        assert attributes['fastapi.arguments.errors'] == []
        assert attributes['test.path'] == '/items/123'
        for phase in ('arguments', 'endpoint_function'):
            for boundary in ('start_timestamp', 'end_timestamp'):
                assert f'fastapi.{phase}.{boundary}' in attributes
        assert roots[1]['attributes']['http.status_code'] == 422
        assert roots[1]['attributes']['fastapi.arguments.errors'][0]['type'] == 'int_parsing'
        assert not any('asgi.event.type' in span['attributes'] for span in spans)
        assert len(spans) == (6 if extra_spans else 3)

    assert fastapi.FastAPI is original_fastapi
    exporter.clear()
    with TestClient(app) as client:
        assert client.get('/items/123').status_code == 200
    # New FastAPI releases resume their native telemetry after OTel instrumentation is removed.
    spans = exporter.exported_spans_as_dict()
    assert sum(span['name'] == 'inside request handler' for span in spans) == 1
    assert not any('fastapi.arguments.start_timestamp' in span['attributes'] for span in spans)
    assert not any('test.path' in span['attributes'] for span in spans)


@pytest.mark.parametrize('record_send_receive', [False, True])
@pytest.mark.parametrize('mounted', [False, True])
def test_global_fastapi_websocket(exporter: TestExporter, record_send_receive: bool, mounted: bool) -> None:
    with instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE, record_send_receive=record_send_receive):
        app = fastapi.FastAPI()
        child = fastapi.FastAPI() if mounted else app
        if mounted:
            app.mount('/child', child)

        @child.websocket('/ws/{name}')
        async def echo(websocket: WebSocket, name: str) -> None:
            await websocket.accept()
            assert await websocket.receive_text() == 'ping'
            await websocket.send_text(name)
            await websocket.close()

        with (
            TestClient(app) as client,
            client.websocket_connect('/child/ws/foo' if mounted else '/ws/foo') as websocket,
        ):
            websocket.send_text('ping')
            assert websocket.receive_text() == 'foo'

        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        roots = [span for span in spans if span['name'] == ('HTTP /child' if mounted else 'HTTP /ws/{name}')]
        assert len(roots) == 1
        assert roots[0]['attributes']['fastapi.route.name'] == 'echo'
        assert roots[0]['attributes']['fastapi.arguments.values'] == {'name': 'foo'}
        assert roots[0]['attributes']['fastapi.arguments.errors'] == []
        io_spans = [span for span in spans if 'asgi.event.type' in span['attributes']]
        assert bool(io_spans) == record_send_receive
        assert all(span['attributes']['logfire.level_num'] == 5 for span in io_spans)
        assert len(spans) == 1 + len(io_spans)


@pytest.mark.parametrize('preexisting_app', [False, True])
def test_global_fastapi_rejects_per_app_instrumentation(exporter: TestExporter, preexisting_app: bool) -> None:
    app = fastapi.FastAPI() if preexisting_app else None
    with instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE):
        if app is None:
            app = fastapi.FastAPI()

        @app.get('/items/{item_id}')
        async def homepage(item_id: int) -> int:
            return item_id

        with pytest.raises(ValueError) as exc:
            logfire.instrument_fastapi(app)
        assert str(exc.value) == (
            'Global FastAPI instrumentation cannot be combined with logfire.instrument_fastapi(app). '
            'Run your application with `logfire run --exclude fastapi ...` to use app-specific instrumentation instead. '
            'If you need both global and app-specific instrumentation, please open an issue at '
            'https://github.com/pydantic/logfire/issues.'
        )
        with pytest.raises(ValueError, match='Global FastAPI instrumentation cannot be combined'):
            instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE)
        if not preexisting_app:
            with TestClient(app) as client:
                assert client.get('/items/123').json() == 123
            spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
            assert [span['attributes']['fastapi.arguments.values'] for span in spans] == [{'item_id': 123}]
            exporter.clear()

    # A rejected call must not register the app or prevent app-specific setup later.
    with logfire.instrument_fastapi(app):
        with pytest.raises(ValueError, match='This app has already been instrumented'):
            logfire.instrument_fastapi(app)
        with pytest.raises(ValueError, match='Global FastAPI instrumentation cannot be combined'):
            instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE)


def test_per_app_fastapi_rejects_global_instrumentation(exporter: TestExporter) -> None:
    app = fastapi.FastAPI()

    @app.get('/items/{item_id}')
    async def homepage(item_id: int) -> int:
        return item_id

    with logfire.instrument_fastapi(app):
        with pytest.raises(ValueError, match='Global FastAPI instrumentation cannot be combined'):
            instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE)
        with TestClient(app) as client:
            assert client.get('/items/456').json() == 456
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        assert [span['attributes']['fastapi.arguments.values'] for span in spans] == [{'item_id': 456}]


def test_global_fastapi_mounted_app_exclusion(exporter: TestExporter) -> None:
    with instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE, excluded_urls='/private'):
        app = fastapi.FastAPI()
        child = fastapi.FastAPI()
        grandchild = fastapi.FastAPI()
        app.mount('/child', child)
        child.mount('/nested', grandchild)

        @grandchild.post('/private')
        @grandchild.post('/public')
        async def endpoint(payload: dict[str, str]) -> dict[str, str]:
            return payload

        payload = {'message': 'private-value'}
        with TestClient(app) as client:
            assert client.post('/child/nested/private', json=payload).json() == payload
            assert exporter.exported_spans_as_dict() == []
            assert client.post('/child/nested/public', json=payload).json() == payload
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        assert len(spans) == 1
        assert spans[0]['name'] == 'POST /child'
        assert spans[0]['attributes']['fastapi.arguments.values'] == {'payload': payload}

        exporter.clear()
        with TestClient(grandchild) as client:
            assert client.post('/public', json=payload).json() == payload
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        assert len(spans) == 1
        assert spans[0]['name'] == 'POST /public'
        assert spans[0]['attributes']['fastapi.arguments.values'] == {'payload': payload}


def test_global_fastapi_unexpected_middleware_stack(monkeypatch: pytest.MonkeyPatch) -> None:
    def skip_instrumentation(_app: fastapi.FastAPI, **_kwargs: Any) -> None:
        pass

    with instrument_fastapi(logfire.DEFAULT_LOGFIRE_INSTANCE):
        with monkeypatch.context() as patch:
            patch.setattr(FastAPIInstrumentor, 'instrument_app', skip_instrumentation)
            app = fastapi.FastAPI()

        stack = app.build_middleware_stack()
        assert isinstance(stack, ServerErrorMiddleware)
        assert not isinstance(stack.app, OncePerRequest)
