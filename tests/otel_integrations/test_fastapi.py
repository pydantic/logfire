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
from fastapi.staticfiles import StaticFiles
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


async def echo_body(request: Request):
    return await request.body()


@pytest.fixture()
def app():
    # Don't define the endpoint functions in this fixture to prevent a qualname with <locals> in it
    # which won't be stripped out of the logfire msg, complicating things in different python versions.
    app = FastAPI()
    first_lvl_app = FastAPI()
    second_lvl_app = FastAPI()
    app.mount('/static', StaticFiles(), name='static')  # https://github.com/pydantic/logfire/issues/288
    app.mount('/first_lvl', first_lvl_app)
    first_lvl_app.mount('/second_lvl', second_lvl_app)

    app.get('/')(homepage)
    app.get('/other', name='other_route_name', operation_id='other_route_operation_id')(other_route)
    app.get('/exception')(exception)
    app.get('/validation_error')(validation_error)
    app.get('/with_path_param/{param}')(with_path_param)
    app.get('/secret/{path_param}', name='secret')(get_secret)
    first_lvl_app.get('/other', name='other_route_name', operation_id='other_route_operation_id')(other_route)
    second_lvl_app.get('/other', name='other_route_name', operation_id='other_route_operation_id')(other_route)
    return app


@pytest.fixture(autouse=True)  # only applies within this module
def auto_instrument_fastapi(app: FastAPI):
    def request_attributes_mapper(request: Request | WebSocket, attributes: dict[str, Any]) -> dict[str, Any] | None:
        if request.scope['route'].name in ('other_route_name', 'secret'):
            attributes['custom_attr'] = 'custom_value'
            return attributes

    # uninstrument at the end of each test
    with logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper, record_send_receive=True):
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
                    'http.response.status_code': 404,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/missing',
                    'url.path': '/missing',
                    'http.url': 'http://testserver/missing',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.status_code': 404,
                    'http.response.status_code': 404,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/with_path_param/param_val',
                    'url.path': '/with_path_param/param_val',
                    'http.url': 'http://testserver/with_path_param/param_val',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
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
                    'http.response.status_code': 200,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/with_path_param/param_val',
                    'url.path': '/with_path_param/param_val',
                    'http.url': 'http://testserver/with_path_param/param_val',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/with_path_param/{param}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
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
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
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
                    'http.response.status_code': 200,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
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
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
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
                    'http.response.status_code': 422,
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
                    'logfire.msg': "GET /other ? bar='bar_val' & foo='foo_val'",
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/other',
                    'url.path': '/other',
                    'url.query': 'foo=foo_val&bar=bar_val',
                    'http.url': 'http://testserver/other?foo=foo_val&bar=bar_val',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/other',
                    'http.status_code': 422,
                    'http.response.status_code': 422,
                },
            },
        ]
    )


def test_get_fastapi_arguments(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/other?foo=foo_val&bar=1')
    assert response.status_code == 200
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
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'values': '{"foo":"foo_val","bar":1}',
                    'errors': '[]',
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
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'method': 'GET',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'other_route',
                    'code.lineno': 123,
                    'http.route': '/other',
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /other (other_route)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'GET /other http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other http send response.start',
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /other http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
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
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /other ? bar='1' & foo='foo_val'",
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/other',
                    'url.path': '/other',
                    'url.query': 'foo=foo_val&bar=1',
                    'http.url': 'http://testserver/other?foo=foo_val&bar=1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/other',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_first_lvl_subapp_fastapi_arguments(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/first_lvl/other?foo=foo_val&bar=1')
    assert response.status_code == 200
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
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'values': '{"foo":"foo_val","bar":1}',
                    'errors': '[]',
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
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'method': 'GET',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'other_route',
                    'code.lineno': 123,
                    'http.route': '/other',
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /other (other_route)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'GET /first_lvl http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /first_lvl http send response.start',
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /first_lvl http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /first_lvl http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /first_lvl',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /first_lvl/other ? bar='1' & foo='foo_val'",
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/first_lvl/other',
                    'url.path': '/first_lvl/other',
                    'url.query': 'foo=foo_val&bar=1',
                    'http.url': 'http://testserver/first_lvl/other?foo=foo_val&bar=1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/first_lvl',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_second_lvl_subapp_fastapi_arguments(client: TestClient, exporter: TestExporter) -> None:
    response = client.get('/first_lvl/second_lvl/other?foo=foo_val&bar=1')
    assert response.status_code == 200
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
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'values': '{"foo":"foo_val","bar":1}',
                    'errors': '[]',
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
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'other_route',
                    'code.lineno': 123,
                    'method': 'GET',
                    'http.route': '/other',
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'GET /other (other_route)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'GET /first_lvl http send response.start',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /first_lvl http send response.start',
                    'http.status_code': 200,
                    'asgi.event.type': 'http.response.start',
                    'logfire.level_num': 5,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'GET /first_lvl http send response.body',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /first_lvl http send response.body',
                    'asgi.event.type': 'http.response.body',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'GET /first_lvl',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /first_lvl/second_lvl/other ? bar='1' & foo='foo_val'",
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/first_lvl/second_lvl/other',
                    'url.path': '/first_lvl/second_lvl/other',
                    'url.query': 'foo=foo_val&bar=1',
                    'http.url': 'http://testserver/first_lvl/second_lvl/other?foo=foo_val&bar=1',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/first_lvl',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/exception',
                    'url.path': '/exception',
                    'http.url': 'http://testserver/exception',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/exception',
                    'logfire.level_num': 17,
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
                    'http.response.status_code': 422,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/validation_error',
                    'url.path': '/validation_error',
                    'http.url': 'http://testserver/validation_error',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/validation_error',
                    'http.status_code': 422,
                    'http.response.status_code': 422,
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
                    'values': IsJson(
                        {
                            'path_param': "[Scrubbed due to 'auth']",
                            'foo': 'foo_val',
                            'password': "[Scrubbed due to 'password']",
                            'testauthorization': "[Scrubbed due to 'auth']",
                        }
                    ),
                    'errors': '[]',
                    'custom_attr': 'custom_value',
                    'http.method': 'GET',
                    'http.route': '/secret/{path_param}',
                    'fastapi.route.name': 'secret',
                    'logfire.null_args': ('fastapi.route.operation_id',),
                    'logfire.json_schema': '{"type":"object","properties":{"values":{"type":"object"},"errors":{"type":"array"},"custom_attr":{},"http.method":{},"http.route":{},"fastapi.route.name":{},"fastapi.route.operation_id":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.scrubbed': IsJson(
                        [
                            {'path': ['attributes', 'values', 'path_param'], 'matched_substring': 'auth'},
                            {'path': ['attributes', 'values', 'password'], 'matched_substring': 'password'},
                            {'path': ['attributes', 'values', 'testauthorization'], 'matched_substring': 'auth'},
                        ]
                    ),
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
                    'http.response.status_code': 200,
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
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/secret/test_auth',
                    'url.path': '/secret/test_auth',
                    'url.query': 'foo=foo_val&password=hunter2',
                    'http.url': 'http://testserver/secret/test_auth?foo=foo_val&password=hunter2',
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/secret/{path_param}',
                    'http.request.header.testauthorization': ("[Scrubbed due to 'auth']",),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'logfire.scrubbed': IsJson(
                        [{'path': ['attributes', 'http.request.header.testauthorization'], 'matched_substring': 'auth'}]
                    ),
                },
            },
        ]
    )


def make_request_hook_spans(record_send_receive: bool):
    # Instrument an app with request hooks to make sure that they work.
    # We make a new app here instead of using the fixtures because the same app can't be instrumented twice.
    # Then make a request to it to generate spans.
    # The tests then check that the spans are in the right place both with and without send/receive spans.
    app = FastAPI()
    # This endpoint reads the request body, which means that OTEL will create an ASGI receive span.
    app.post('/echo_body')(echo_body)
    client = TestClient(app)

    with logfire.instrument_fastapi(
        app,
        record_send_receive=record_send_receive,
        server_request_hook=lambda *_, **__: logfire.info('server_request_hook'),  # type: ignore
        client_request_hook=lambda *_, **__: logfire.info('client_request_hook'),  # type: ignore
        client_response_hook=lambda *_, **__: logfire.info('client_response_hook'),  # type: ignore
    ):
        response = client.post('/echo_body', content=b'hello')
        assert response.status_code == 200
        assert response.content == b'"hello"'


def test_request_hooks_without_send_receiev_spans(exporter: TestExporter):
    make_request_hook_spans(record_send_receive=False)
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'server_request_hook',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'server_request_hook',
                    'logfire.msg': 'server_request_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'values': '{}',
                    'errors': '[]',
                    'http.method': 'POST',
                    'http.route': '/echo_body',
                    'fastapi.route.name': 'echo_body',
                    'logfire.null_args': ('fastapi.route.operation_id',),
                    'logfire.json_schema': '{"type":"object","properties":{"values":{"type":"object"},"errors":{"type":"array"},"http.method":{},"http.route":{},"fastapi.route.name":{},"fastapi.route.operation_id":{}}}',
                },
            },
            {
                'name': 'client_request_hook',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_request_hook',
                    'logfire.msg': 'client_request_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 7000000000,
                'attributes': {
                    'method': 'POST',
                    'http.route': '/echo_body',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'echo_body',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'POST /echo_body (echo_body)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'client_response_hook',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_response_hook',
                    'logfire.msg': 'client_response_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'client_response_hook',
                'context': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 9000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_response_hook',
                    'logfire.msg': 'client_response_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'POST /echo_body',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo_body',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/echo_body',
                    'url.path': '/echo_body',
                    'http.url': 'http://testserver/echo_body',
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/echo_body',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )


def test_request_hooks_with_send_receive_spans(exporter: TestExporter):
    make_request_hook_spans(record_send_receive=True)
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'server_request_hook',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'server_request_hook',
                    'logfire.msg': 'server_request_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'FastAPI arguments',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'logfire.tags': ('fastapi',),
                    'logfire.span_type': 'span',
                    'values': '{}',
                    'errors': '[]',
                    'http.method': 'POST',
                    'http.route': '/echo_body',
                    'fastapi.route.name': 'echo_body',
                    'logfire.null_args': ('fastapi.route.operation_id',),
                    'logfire.json_schema': '{"type":"object","properties":{"values":{"type":"object"},"errors":{"type":"array"},"http.method":{},"http.route":{},"fastapi.route.name":{},"fastapi.route.operation_id":{}}}',
                },
            },
            {
                'name': 'client_request_hook',
                'context': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_request_hook',
                    'logfire.msg': 'client_request_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'POST /echo_body http receive request',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo_body http receive request',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.request',
                },
            },
            {
                'name': '{method} {http.route} ({code.function})',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 9000000000,
                'attributes': {
                    'method': 'POST',
                    'http.route': '/echo_body',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'echo_body',
                    'code.lineno': 123,
                    'logfire.msg_template': '{method} {http.route} ({code.function})',
                    'logfire.msg': 'POST /echo_body (echo_body)',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"http.route":{}}}',
                    'logfire.tags': ('fastapi',),
                    'logfire.level_num': 5,
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'client_response_hook',
                'context': {'trace_id': 1, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 11000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_response_hook',
                    'logfire.msg': 'client_response_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'POST /echo_body http send response.start',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo_body http send response.start',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.response.start',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
            {
                'name': 'client_response_hook',
                'context': {'trace_id': 1, 'span_id': 16, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 14, 'is_remote': False},
                'start_time': 14000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'client_response_hook',
                    'logfire.msg': 'client_response_hook',
                    'code.filepath': 'test_fastapi.py',
                    'code.function': '<lambda>',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'POST /echo_body http send response.body',
                'context': {'trace_id': 1, 'span_id': 14, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 13000000000,
                'end_time': 15000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo_body http send response.body',
                    'logfire.level_num': 5,
                    'asgi.event.type': 'http.response.body',
                },
            },
            {
                'name': 'POST /echo_body',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 16000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /echo_body',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'http.host': 'testserver',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/echo_body',
                    'url.path': '/echo_body',
                    'http.url': 'http://testserver/echo_body',
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.server_name': 'testserver',
                    'http.user_agent': 'testclient',
                    'user_agent.original': 'testclient',
                    'net.peer.ip': 'testclient',
                    'client.address': 'testserver',
                    'net.peer.port': 50000,
                    'client.port': 50000,
                    'http.route': '/echo_body',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                },
            },
        ]
    )
