from __future__ import annotations

import importlib
import os
from typing import Any
from unittest import mock

import pytest
from dirty_equals import IsJson
from fastapi import BackgroundTasks, FastAPI, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.params import Header
from fastapi.security import SecurityScopes
from inline_snapshot import snapshot
from opentelemetry.propagate import inject
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient
from typing_extensions import Annotated

import logfire
import logfire._internal
import logfire._internal.integrations
import logfire._internal.integrations.fastapi
from logfire.testing import TestExporter


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.fastapi': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.fastapi)
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_fastapi()` requires the `opentelemetry-instrumentation-fastapi` package.
You can install this with:
    pip install 'logfire[fastapi]'\
""")


async def homepage() -> PlainTextResponse:
    logfire.info('inside request handler')
    return PlainTextResponse('middleware test')


async def other_route(
    foo: str,
    bar: int,
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    security_scopes: SecurityScopes,
):
    pass  # pragma: no cover


async def exception():
    raise ValueError('test exception')


async def validation_error():
    raise RequestValidationError([])


async def with_path_param(param: str):
    return {'param': param}


async def get_secret(path_param: str, foo: str, password: str, testauthorization: Annotated[str, Header()]):
    return {'foo': foo, 'password': password, 'testauthorization': testauthorization, 'path_param': path_param}


@pytest.fixture()
def app():
    # Don't define the endpoint functions in this fixture to prevent a qualname with <locals> in it
    # which won't be stripped out of the logfire msg, complicating things in different python versions.
    app = FastAPI()
    app.get('/')(homepage)
    app.get('/other', name='other_route_name', operation_id='other_route_operation_id')(other_route)
    app.get('/exception')(exception)
    app.get('/validation_error')(validation_error)
    app.get('/with_path_param/{param}')(with_path_param)
    app.get('/secret/{path_param}', name='secret')(get_secret)
    return app


@pytest.fixture(autouse=True)  # only applies within this module
def auto_instrument_fastapi(app: FastAPI):
    def request_attributes_mapper(request: Request | WebSocket, attributes: dict[str, Any]) -> dict[str, Any] | None:
        if request.scope['route'].name in ('other_route_name', 'secret'):
            attributes['custom_attr'] = 'custom_value'
            return attributes

    # uninstrument at the end of each test
    with logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper):
        yield


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_404(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/missing')
    assert response.status_code == 404

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET http send response.start',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET http send response.start',
                    'http.status_code': 404,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET http send response.body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /missing',
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/missing',
                    'http.url': 'http://testserver/missing',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.status_code': 404,
                },
            },
        ]
    )


def test_path_param(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/with_path_param/param_val')
    assert response.status_code == 200
    assert response.json() == {'param': 'param_val'}

    span_dicts = exporter.exported_spans_as_dict(_include_pending_spans=True)

    # Highlights of the below mega-assert:
    assert span_dicts[0]['name'] == 'GET /with_path_param/{param} (pending)'
    assert span_dicts[0]['attributes']['logfire.msg'] == 'GET /with_path_param/param_val'
    assert span_dicts[-1]['name'] == 'GET /with_path_param/{param}'
    assert span_dicts[-1]['attributes']['logfire.msg'] == 'GET /with_path_param/param_val'
    # TODO maybe later the messages for "endpoint function" and "http send response" etc.
    #   should also show the target instead of the route?

    assert span_dicts == snapshot(
        [
            {
                'name': 'GET /with_path_param/{param} (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/with_path_param/param_val',
                    'http.url': 'http://testserver/with_path_param/param_val',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/with_path_param/{param}',
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /with_path_param/param_val',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'FastAPI arguments (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.span_type': 'span',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '{method} {http.route} ({code.function}) (pending)',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'method': 'GET',
                    'http.route': '/with_path_param/{param}',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'with_path_param',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.span_type': 'pending_span',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.msg': 'GET /with_path_param/{param} (with_path_param)',
                    'logfire.level_num': 5,
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'method': 'GET',
                    'http.route': '/with_path_param/{param}',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'with_path_param',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.msg': 'GET /with_path_param/{param} (with_path_param)',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send (pending)',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /with_path_param/{param} http send',
                    'logfire.level_num': 5,
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /with_path_param/{param} http send response.start',
                    'logfire.level_num': 5,
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send (pending)',
                'context': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /with_path_param/{param} http send',
                    'logfire.level_num': 5,
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /with_path_param/{param} http send response.body',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'GET /with_path_param/{param}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /with_path_param/param_val',
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/with_path_param/param_val',
                    'http.url': 'http://testserver/with_path_param/param_val',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/with_path_param/{param}',
                    'http.status_code': 200,
                },
            },
        ]
    )


def test_fastapi_instrumentation(client: TestClient, exporter: TestExporter) -> None:
    with logfire.span('outside request handler'):
        headers: dict[str, str] = {}
        inject(headers)
        response = client.get('/', headers=headers)

    assert response.status_code == 200
    assert response.text == 'middleware test'

    assert exporter.exported_spans_as_dict(_include_pending_spans=True) == snapshot(
        [
            {
                'name': 'outside request handler (pending)',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.lineno': 123,
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'test_fastapi_instrumentation',
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'GET / (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
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
                    'http.route': '/',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                    'logfire.msg': 'GET /',
                },
            },
            {
                'name': 'FastAPI arguments (pending)',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000003',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.tags': ('fastapi',),
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '{method} {http.route} ({code.function}) (pending)',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'homepage',
                    'code.lineno': 123,
                    'method': 'GET',
                    'http.route': '/',
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET / (homepage)',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.pending_parent_id': '0000000000000003',
                },
            },
            {
                'name': 'inside request handler',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.msg_template': 'inside request handler',
                    'logfire.level_num': 9,
                    'logfire.msg': 'inside request handler',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'homepage',
                    'code.lineno': 123,
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 7000000000,
                'attributes': {
                    'method': 'GET',
                    'http.route': '/',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'homepage',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.msg': 'GET / (homepage)',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET / http send (pending)',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000003',
                    'logfire.level_num': 5,
                    'logfire.msg': 'GET / http send',
                },
            },
            {
                'name': 'GET / http send response.start',
                'context': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.start',
                    'logfire.level_num': 5,
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                },
            },
            {
                'name': 'GET / http send (pending)',
                'context': {'trace_id': 1, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 12, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET / http send',
                    'logfire.level_num': 5,
                    'logfire.pending_parent_id': '0000000000000003',
                },
            },
            {
                'name': 'GET / http send response.body',
                'context': {'trace_id': 1, 'span_id': 12, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.body',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'GET /',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 12000000000,
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
                    'http.route': '/',
                    'http.status_code': 200,
                },
            },
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'test_fastapi_instrumentation',
                    'code.lineno': 123,
                    'logfire.msg_template': 'outside request handler',
                    'logfire.msg': 'outside request handler',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_fastapi_arguments(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/other?foo=foo_val&bar=bar_val')
    assert response.status_code == 422
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'custom_attr': 'custom_value',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'values': '{"foo":"foo_val"}',
                    'errors': '[{"type":"int_parsing","loc":["query","bar"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"bar_val"}]',
                    'http.method': 'GET',
                    'http.route': '/other',
                    'fastapi.route.name': 'other_route_name',
                    'fastapi.route.operation_id': 'other_route_operation_id',
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'values': {'type': 'object'},
                                'errors': {
                                    'type': 'array',
                                    'items': {
                                        'type': 'object',
                                        'properties': {'loc': {'type': 'array', 'x-python-datatype': 'tuple'}},
                                    },
                                },
                                'http.method': {},
                                'http.route': {},
                                'fastapi.route.name': {},
                                'fastapi.route.operation_id': {},
                                'custom_attr': {},
                            },
                        }
                    ),
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'GET /other http send response.start',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other http send response.start',
                    'http.status_code': 422,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /other http send response.body',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /other',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other',
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/other',
                    'http.url': 'http://testserver/other?foo=foo_val&bar=bar_val',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/other',
                    'http.status_code': 422,
                },
            },
        ]
    )


def test_fastapi_unhandled_exception(client: TestClient, exporter: TestExporter) -> None:
    with pytest.raises(ValueError):
        client.get('/exception')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'attributes': {
                    'method': 'GET',
                    'http.route': '/exception',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'exception',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /exception (exception)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 5000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test exception',
                            'exception.stacktrace': 'ValueError: test exception',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
            {
                'name': 'GET /exception',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /exception',
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/exception',
                    'http.url': 'http://testserver/exception',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/exception',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 7000000000,
                        'attributes': {
                            'exception.type': 'ValueError',
                            'exception.message': 'test exception',
                            'exception.stacktrace': 'ValueError: test exception',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            },
        ]
    )


def test_fastapi_handled_exception(client: TestClient, exporter: TestExporter) -> None:
    # FastAPI automatically handles RequestValidationError and returns a 422 response.
    # Our instrumentation still captures the exception as it happens in the endpoint.
    response = client.get('/validation_error')
    assert response.status_code == 422

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'attributes': {
                    'method': 'GET',
                    'http.route': '/validation_error',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'validation_error',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /validation_error (validation_error)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 5000000000,
                        'attributes': {
                            'exception.type': 'fastapi.exceptions.RequestValidationError',
                            'exception.message': '[]',
                            'exception.stacktrace': 'fastapi.exceptions.RequestValidationError: []',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
            {
                'name': 'GET /validation_error http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error http send response.start',
                    'logfire.level_num': 5,
                    'http.status_code': 422,
                    'asgi.event.type': 'http.response.start',
                },
            },
            {
                'name': 'GET /validation_error http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error http send response.body',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'GET /validation_error',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error',
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/validation_error',
                    'http.url': 'http://testserver/validation_error',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/validation_error',
                    'http.status_code': 422,
                },
            },
        ]
    )


def test_scrubbing(client: TestClient, exporter: TestExporter) -> None:
    os.environ['OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST'] = 'TestAuthorization'

    response = client.get(
        '/secret/test_auth?foo=foo_val&password=hunter2',
        headers={'TestAuthorization': 'Bearer abcd'},
    )
    assert response.status_code == 200

    # TODO scrub URL parameters
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'values': '{"path_param": "[Redacted due to \'auth\']", "foo": "foo_val", "password": "[Redacted due to \'password\']", "testauthorization": "[Redacted due to \'auth\']"}',
                    'errors': '[]',
                    'custom_attr': 'custom_value',
                    'http.method': 'GET',
                    'http.route': '/secret/{path_param}',
                    'fastapi.route.name': 'secret',
                    'logfire.null_args': ('fastapi.route.operation_id',),
                    'logfire.json_schema': '{"type":"object","properties":{"values":{"type":"object"},"errors":{"type":"array"},"custom_attr":{},"http.method":{},"http.route":{},"fastapi.route.name":{},"fastapi.route.operation_id":{}}}',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'get_secret',
                    'code.lineno': 123,
                    'method': 'GET',
                    'http.route': '/secret/{path_param}',
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /secret/{path_param} (get_secret)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'GET /secret/{path_param} http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /secret/{path_param} http send response.start',
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /secret/{path_param} http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /secret/{path_param} http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /secret/{path_param}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /secret/test_auth ? foo='foo_val' & password='hunter2'",
                    'http.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'http.flavor': '1.1',
                    'http.target': '/secret/test_auth',
                    'http.url': 'http://testserver/secret/test_auth?foo=foo_val&password=hunter2',
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'net.peer.ip': 'testclient',
                    'net.peer.port': 50000,
                    'http.route': '/secret/{path_param}',
                    'http.request.header.testauthorization': ("[Redacted due to 'auth']",),
                    'http.status_code': 200,
                },
            },
        ]
    )
