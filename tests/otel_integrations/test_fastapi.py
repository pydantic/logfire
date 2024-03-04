import pytest
from dirty_equals import IsJson, IsUrl
from fastapi import BackgroundTasks, FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.security import SecurityScopes
from inline_snapshot import snapshot
from opentelemetry.propagate import inject
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

import logfire
from logfire.testing import TestExporter


@pytest.fixture()
def app() -> FastAPI:
    app = FastAPI()

    @app.get('/')
    async def homepage() -> PlainTextResponse:
        logfire.info('inside request handler')
        return PlainTextResponse('middleware test')

    @app.get('/other', name='other_route_name', operation_id='other_route_operation_id')
    async def other_route(
        foo: str,
        bar: int,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        security_scopes: SecurityScopes,
    ):
        pass

    @app.get('/exception')
    async def exception():
        raise ValueError('test exception')

    @app.get('/validation_error')
    async def validation_error():
        raise RequestValidationError([])

    @app.get('/with_path_param/{param}')
    async def with_path_param(param: str):
        return {'param': param}

    return app


@pytest.fixture(autouse=True)  # only applies within this module
def auto_instrument_fastapi(app: FastAPI):
    def request_attributes_mapper(request, attributes):
        if request.scope['route'].name == 'other_route_name':
            attributes['custom_attr'] = 'custom_value'
            return attributes

    # uninstrument at the end of each test
    with logfire.instrument_fastapi(app, request_attributes_mapper=request_attributes_mapper):
        yield


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


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
                    'http.route': '/with_path_param/{param}',
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /with_path_param/param_val',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': '{method} {route} endpoint function (pending)',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/with_path_param/{param}',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.msg': 'GET /with_path_param/{param} endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': '{method} {route} endpoint function',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/with_path_param/{param}',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.msg': 'GET /with_path_param/{param} endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send (pending)',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.msg': 'GET /with_path_param/{param} http send',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send response.start',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /with_path_param/{param} http send response.start',
                    'http.status_code': 200,
                    'type': 'http.response.start',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
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
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'GET /with_path_param/{param} http send response.body',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /with_path_param/{param} http send response.body',
                    'type': 'http.response.body',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /with_path_param/{param}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
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
                    'http.route': '/with_path_param/{param}',
                    'http.status_code': 200,
                },
            },
        ]
    )


def test_fastapi_instrumentation(client: TestClient, exporter: TestExporter) -> None:
    with logfire.span('outside request handler'):
        headers = {}
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
                    'http.route': '/',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                    'logfire.msg': 'GET /',
                },
            },
            {
                'name': '{method} {route} endpoint function (pending)',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.msg': 'GET / endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000003',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'inside request handler',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 4000000000,
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
                'name': '{method} {route} endpoint function',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / endpoint function',
                    'logfire.tags': ('fastapi',),
                },
            },
            {
                'name': 'GET / http send (pending)',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000003',
                    'logfire.msg': 'GET / http send',
                },
            },
            {
                'name': 'GET / http send response.start',
                'context': {'trace_id': 1, 'span_id': 8, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.start',
                    'http.status_code': 200,
                    'type': 'http.response.start',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
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
                    'logfire.msg': 'GET / http send',
                },
            },
            {
                'name': 'GET / http send response.body',
                'context': {'trace_id': 1, 'span_id': 10, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET / http send response.body',
                    'type': 'http.response.body',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 10000000000,
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
                    'http.route': '/',
                    'http.status_code': 200,
                },
            },
            {
                'name': 'outside request handler',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 11000000000,
                'attributes': {
                    'code.lineno': 123,
                    'code.filepath': 'test_fastapi.py',
                    'code.function': 'test_fastapi_instrumentation',
                    'logfire.msg_template': 'outside request handler',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'outside request handler',
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
                'end_time': 2000000000,
                'attributes': {
                    'custom_attr': 'custom_value',
                    'logfire.span_type': 'log',
                    'logfire.level_name': 'error',
                    'logfire.level_num': 17,
                    'logfire.msg_template': 'FastAPI arguments',
                    'logfire.msg': 'FastAPI arguments',
                    'code.filepath': '_fastapi.py',
                    'code.function': 'solve_dependencies',
                    'code.lineno': 123,
                    'values': '{"foo":"foo_val"}',
                    'errors': IsJson(
                        [
                            {
                                'type': 'int_parsing',
                                'loc': ['query', 'bar'],
                                'msg': 'Input should be a valid integer, unable to parse string as an integer',
                                'input': 'bar_val',
                                'url': IsUrl,
                            }
                        ]
                    ),
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
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other http send response.start',
                    'http.status_code': 422,
                    'type': 'http.response.start',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /other http send response.body',
                'context': {'trace_id': 1, 'span_id': 6, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /other http send response.body',
                    'type': 'http.response.body',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /other',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 7000000000,
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
                'name': '{method} {route} endpoint function',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/exception',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.level_name': 'error',
                    'logfire.msg': 'GET /exception endpoint function',
                    'logfire.tags': ('fastapi',),
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
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
                'end_time': 6000000000,
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
                    'http.route': '/exception',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 5000000000,
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
                'name': '{method} {route} endpoint function',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': '_fastapi.py',
                    'code.function': 'run_endpoint_function',
                    'code.lineno': 123,
                    'method': 'GET',
                    'route': '/validation_error',
                    'logfire.msg_template': '{method} {route} endpoint function',
                    'logfire.json_schema': '{"type":"object","properties":{"method":{},"route":{}}}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error endpoint function',
                    'logfire.level_num': 17,
                    'logfire.level_name': 'error',
                    'logfire.tags': ('fastapi',),
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 3000000000,
                        'attributes': {
                            'exception.type': 'RequestValidationError',
                            'exception.message': '[]',
                            'exception.stacktrace': 'fastapi.exceptions.RequestValidationError: []',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            },
            {
                'name': 'GET /validation_error http send response.start',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error http send response.start',
                    'http.status_code': 422,
                    'type': 'http.response.start',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /validation_error http send response.body',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /validation_error http send response.body',
                    'type': 'http.response.body',
                    'logfire.level_num': 5,
                    'logfire.level_name': 'debug',
                },
            },
            {
                'name': 'GET /validation_error',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 9000000000,
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
                    'http.route': '/validation_error',
                    'http.status_code': 422,
                },
            },
        ]
    )
