import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import inject
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

import logfire
from logfire.testing import TestExporter


@pytest.fixture()
def app() -> FastAPI:
    async def homepage() -> PlainTextResponse:
        logfire.info('inside request handler')
        return PlainTextResponse('middleware test')

    return FastAPI(routes=[APIRoute('/', homepage)])


@pytest.fixture(autouse=True)  # only applies within this module
def instrument_httpx(app: FastAPI):
    FastAPIInstrumentor.instrument_app(app)  # type: ignore
    yield
    FastAPIInstrumentor.uninstrument_app(app)


def test_asgi_middleware(app: FastAPI, exporter: TestExporter) -> None:
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
                'logfire.level_name': 'info',
                'logfire.level_num': 9,
                'logfire.msg_template': 'inside request handler',
                'logfire.msg': 'inside request handler',
                'code.lineno': 123,
                'code.filepath': 'test_fastapi.py',
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
                'http.route': '/',
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
                'code.filepath': 'test_fastapi.py',
                'code.function': 'test_asgi_middleware',
                'logfire.msg_template': 'outside request handler',
                'logfire.span_type': 'span',
                'logfire.msg': 'outside request handler',
            },
        },
    ]
