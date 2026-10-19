from __future__ import annotations

import pytest
from opentelemetry.trace import Span
from starlette.testclient import TestClient
from starlette.types import Scope

pytest.importorskip('fastapi', reason='FastAPI requires pydantic>=2.7', exc_type=ImportError)

import fastapi

import logfire
from logfire._internal.integrations.fastapi import instrument_fastapi
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
