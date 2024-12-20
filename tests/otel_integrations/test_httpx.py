from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any
from unittest import mock

import httpx
import pytest
from dirty_equals import IsDict, IsStr
from httpx import Request
from inline_snapshot import snapshot
from opentelemetry.instrumentation.httpx import RequestInfo, ResponseInfo
from opentelemetry.trace.span import Span

import logfire
import logfire._internal.integrations.httpx
from logfire.testing import TestExporter

pytestmark = pytest.mark.anyio


# The purpose of this mock transport is to ensure that the traceparent header is provided
# without needing to actually make a network request
def create_transport() -> httpx.MockTransport:
    def handler(request: Request):
        return httpx.Response(200, headers=request.headers, stream=httpx.ByteStream(b'{"good": "response"}'))

    return httpx.MockTransport(handler)


@contextmanager
def check_traceparent_header():
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id

        def checker(response: httpx.Response):
            # Validation of context propagation: ensure that the traceparent header contains the trace ID
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

        yield checker


def test_httpx_client_instrumentation(exporter: TestExporter):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client)
            response = client.get('https://example.org/')
            checker(response)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'https://example.org/',
                    'url.full': 'https://example.org/',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.lineno': 123,
                    'code.function': 'check_traceparent_header',
                    'logfire.msg_template': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test span',
                },
            },
        ]
    )


async def test_async_httpx_client_instrumentation(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client)
            response = await client.get('https://example.org/')
            checker(response)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'https://example.org/',
                    'url.full': 'https://example.org/',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET /',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'check_traceparent_header',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def request_hook(span: Span, request: RequestInfo) -> None:
    span.set_attribute('request_hook', True)


def response_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
    span.set_attribute('response_hook', True)


async def async_request_hook(span: Span, request: RequestInfo) -> None:
    span.set_attribute('async_request_hook', True)


async def async_response_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
    span.set_attribute('async_response_hook', True)


REQUEST_ATTRIBUTES = {
    'http.request.header.host',
    'http.request.header.accept',
    'http.request.header.accept-encoding',
    'http.request.header.connection',
    'http.request.header.user-agent',
}


RESPONSE_ATTRIBUTES = {
    'http.response.header.host',
    'http.response.header.accept',
    'http.response.header.accept-encoding',
    'http.response.header.connection',
    'http.response.header.user-agent',
    'http.response.header.traceparent',
}


@pytest.mark.parametrize(
    ('instrument_kwargs', 'expected_attributes'),
    [
        ({'capture_request_headers': True}, REQUEST_ATTRIBUTES),
        ({'capture_request_headers': True, 'request_hook': request_hook}, {*REQUEST_ATTRIBUTES, 'request_hook'}),
        ({'capture_request_headers': False, 'request_hook': request_hook}, {'request_hook'}),
        ({'capture_response_headers': True}, RESPONSE_ATTRIBUTES),
        ({'capture_response_headers': True, 'response_hook': response_hook}, {*RESPONSE_ATTRIBUTES, 'response_hook'}),
        ({'capture_response_headers': False, 'response_hook': response_hook}, {'response_hook'}),
    ],
)
def test_httpx_client_instrumentation_with_capture_headers(
    exporter: TestExporter, instrument_kwargs: dict[str, Any], expected_attributes: set[str]
):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, **instrument_kwargs)
            response = client.get('https://example.org/')
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in expected_attributes), list(span['attributes'])


@pytest.mark.parametrize(
    ('instrument_kwargs', 'expected_attributes'),
    [
        ({'capture_request_headers': True}, REQUEST_ATTRIBUTES),
        ({'capture_request_headers': True, 'request_hook': request_hook}, {*REQUEST_ATTRIBUTES, 'request_hook'}),
        ({'capture_request_headers': False, 'request_hook': request_hook}, {'request_hook'}),
        ({'capture_response_headers': True}, RESPONSE_ATTRIBUTES),
        ({'capture_response_headers': True, 'response_hook': response_hook}, {*RESPONSE_ATTRIBUTES, 'response_hook'}),
        ({'capture_response_headers': False, 'response_hook': response_hook}, {'response_hook'}),
        (
            {'capture_request_headers': True, 'request_hook': async_request_hook},
            {*REQUEST_ATTRIBUTES, 'async_request_hook'},
        ),
        (
            {'capture_response_headers': True, 'response_hook': async_response_hook},
            {*RESPONSE_ATTRIBUTES, 'async_response_hook'},
        ),
    ],
)
async def test_async_httpx_client_instrumentation_with_capture_headers(
    exporter: TestExporter,
    instrument_kwargs: dict[str, Any],
    expected_attributes: set[str],
):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, **instrument_kwargs)
            response = await client.get('https://example.org/')
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in expected_attributes)


CAPTURE_JSON_BODY_PARAMETERS: tuple[tuple[str, ...], list[tuple[str, Any, dict[str, Any]]]] = (
    ('content_type', 'body', 'expected_attributes'),
    [
        ('application/json', '{"hello": "world"}', {'http.request.body.json': '{"hello": "world"}'}),
        ('application/json; charset=utf-8', '{"hello": "world"}', {'http.request.body.json': '{"hello": "world"}'}),
        (
            'application/json; charset=iso-8859-1',
            '{"hello": "world"}',
            {'http.request.body.json': '{"hello": "world"}'},
        ),
        ('application/json; charset=utf-32', '{"hello": "world"}', {'http.request.body.json': '{"hello": "world"}'}),
        ('application/json; charset=potato', '{"hello": "world"}', {'http.request.body.json': '{"hello": "world"}'}),
        ('application/json; charset=ascii', b'\x80\x81\x82', {'http.request.body.json': '���'}),
        ('application/json; charset=utf8', b'\x80\x81\x82', {'http.request.body.json': '���'}),
        ('text/plain', '{"hello": "world"}', {}),
        ('', '{"hello": "world"}', {}),
    ],
)


@pytest.mark.parametrize(*CAPTURE_JSON_BODY_PARAMETERS)
def test_httpx_client_instrumentation_with_capture_json_body(
    exporter: TestExporter, content_type: str, body: Any, expected_attributes: dict[str, Any]
):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_json_body=True)
            headers = {'Content-Type': content_type} if content_type else {}
            response = client.post('https://example.org/', headers=headers, content=body)
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes'] == IsDict(expected_attributes).settings(partial=True)


@pytest.mark.parametrize(*CAPTURE_JSON_BODY_PARAMETERS)
async def test_async_httpx_client_instrumentation_with_capture_json_body(
    exporter: TestExporter, content_type: str, body: Any, expected_attributes: dict[str, Any]
):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_json_body=True)
            response = await client.post('https://example.org/', headers={'Content-Type': content_type}, content=body)
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes'] == IsDict(expected_attributes).settings(partial=True)


CAPTURE_FULL_REQUEST_ATTRIBUTES = {
    'http.request.header.host',
    'http.request.header.accept',
    'http.request.header.accept-encoding',
    'http.request.header.connection',
    'http.request.header.user-agent',
    'http.request.header.content-type',
    'http.request.header.content-length',
    'http.request.body.json',
}


def test_httpx_client_capture_stream_body(exporter: TestExporter):
    def stream():
        yield b'{"hello": '
        yield b'"world"}'

    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_json_body=True)
            response = client.post(
                'https://example.org/', headers={'Content-Type': 'application/json'}, content=stream()
            )
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    # Streaming bodies aren't captured
    assert 'http.request.body.json' not in span['attributes']


def test_httpx_client_capture_full_request(exporter: TestExporter):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, capture_request_json_body=True)
            response = client.post('https://example.org/', json={'hello': 'world'})
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in CAPTURE_FULL_REQUEST_ATTRIBUTES)


async def test_async_httpx_client_capture_full_request(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, capture_request_json_body=True)
            response = await client.post('https://example.org/', json={'hello': 'world'})
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in CAPTURE_FULL_REQUEST_ATTRIBUTES)


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.httpx': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.httpx)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_httpx()` requires the `opentelemetry-instrumentation-httpx` package.
You can install this with:
    pip install 'logfire[httpx]'\
""")


def test_httpx_client_capture_full(exporter: TestExporter):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(
                client,
                capture_request_headers=True,
                capture_request_json_body=True,
                capture_response_headers=True,
                capture_response_json_body=True,
            )
            response = client.post('https://example.org/', json={'hello': 'world'})
            checker(response)
            assert response.json() == {'good': 'response'}
            assert response.read() == b'{"good": "response"}'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'POST',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.url': 'https://example.org/',
                    'url.full': 'https://example.org/',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /',
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': (IsStr(),),
                    'http.request.header.content-length': (IsStr(),),
                    'http.request.header.content-type': ('application/json',),
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.json":{"type":"object"}}}',
                    'http.request.body.json': '{"hello":"world"}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': (IsStr(),),
                    'http.response.header.content-length': (IsStr(),),
                    'http.response.header.content-type': ('application/json',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
                    'http.target': '/',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': True},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_capture_full',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.json': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.json":{"type":"object"}}}',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'check_traceparent_header',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


async def test_async_httpx_client_capture_full(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(
                client,
                capture_request_headers=True,
                capture_request_json_body=True,
                capture_response_headers=True,
                capture_response_json_body=True,
            )
            response = await client.post('https://example.org/', json={'hello': 'world'})
            checker(response)
            assert response.json() == {'good': 'response'}
            assert await response.aread() == b'{"good": "response"}'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'POST',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.url': 'https://example.org/',
                    'url.full': 'https://example.org/',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST /',
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': (IsStr(),),
                    'http.request.header.content-length': (IsStr(),),
                    'http.request.header.content-type': ('application/json',),
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.json":{"type":"object"}}}',
                    'http.request.body.json': '{"hello":"world"}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': (IsStr(),),
                    'http.response.header.content-length': (IsStr(),),
                    'http.response.header.content-type': ('application/json',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
                    'http.target': '/',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': True},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_capture_full',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.json': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.json":{"type":"object"}}}',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'check_traceparent_header',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_httpx_client_capture_json_response_checks_header(exporter: TestExporter):
    with httpx.Client(transport=create_transport()) as client:
        logfire.instrument_httpx(client, capture_response_json_body=True)
        response = client.post('https://example.org/', content=b'hello')
        assert response.json() == {'good': 'response'}

    spans = exporter.exported_spans_as_dict()
    assert len(spans) == 1
    assert spans[0]['name'] == 'POST'
    assert 'http.response.body.json' not in str(spans)


async def test_httpx_async_client_capture_json_response_checks_header(exporter: TestExporter):
    async with httpx.AsyncClient(transport=create_transport()) as client:
        logfire.instrument_httpx(client, capture_response_json_body=True)
        response = await client.post('https://example.org/', content=b'hello')
        assert response.json() == {'good': 'response'}

    spans = exporter.exported_spans_as_dict()
    assert len(spans) == 1
    assert spans[0]['name'] == 'POST'
    assert 'http.response.body.json' not in str(spans)
