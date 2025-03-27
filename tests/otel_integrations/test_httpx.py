from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any
from unittest import mock

import httpx
import pytest
from dirty_equals import IsAnyStr, IsStr
from httpx import Request
from inline_snapshot import snapshot
from opentelemetry.instrumentation._semconv import _OpenTelemetrySemanticConventionStability  # type: ignore
from opentelemetry.instrumentation.httpx import RequestInfo, ResponseInfo
from opentelemetry.trace.span import Span

import logfire
import logfire._internal.integrations.httpx
from logfire._internal.integrations.httpx import CODES_FOR_METHODS_WITH_DATA_PARAM, is_json_type
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
            response = client.get('https://example.org:8080/foo')
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
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


def test_httpx_client_instrumentation_old_semconv(exporter: TestExporter):
    with mock.patch.dict('os.environ', {'OTEL_SEMCONV_STABILITY_OPT_IN': ''}):
        with httpx.Client(transport=create_transport()) as client:
            # Pick up the new value of OTEL_SEMCONV_STABILITY_OPT_IN
            _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore

            logfire.instrument_httpx(client)
            client.get('https://example.org:8080/foo')

            # Now let other tests get the original value set in conftest.py
            _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.url': 'https://example.org:8080/foo',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.target': '/foo',
                },
            }
        ]
    )


async def test_async_httpx_client_instrumentation(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client)
            response = await client.get('https://example.org:8080/foo')
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
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
        ({'capture_headers': True}, {*REQUEST_ATTRIBUTES, *RESPONSE_ATTRIBUTES}),
    ],
)
def test_httpx_client_instrumentation_with_capture_headers(
    exporter: TestExporter, instrument_kwargs: dict[str, Any], expected_attributes: set[str]
):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, **instrument_kwargs)
            response = client.get('https://example.org:8080/foo')
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
            response = await client.get('https://example.org:8080/foo')
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in expected_attributes)


CAPTURE_JSON_BODY_PARAMETERS: tuple[tuple[str, ...], list[Any]] = (
    ('content_type', 'body', 'expected_http_request_body_text'),
    [
        ('application/json', '{"hello": "world"}', '{"hello": "world"}'),
        ('application/json; charset=utf-8', '{"hello": "world"}', '{"hello": "world"}'),
        ('application/json; charset=iso-8859-1', '{"hello": "world"}', '{"hello": "world"}'),
        ('application/json; charset=utf-32', '{"hello": "world"}', None),
        ('application/json; charset=potato', '{"hello": "world"}', None),
        ('application/json; charset=ascii', b'\x80\x81\x82', None),
        ('application/json; charset=utf8', b'\x80\x81\x82', None),
        ('text/plain', '{"hello": "world"}', '{"hello": "world"}'),
        ('', '{"hello": "world"}', '{"hello": "world"}'),
    ],
)


@pytest.mark.parametrize(*CAPTURE_JSON_BODY_PARAMETERS)
def test_httpx_client_instrumentation_with_capture_json_body(
    exporter: TestExporter, content_type: str, body: Any, expected_http_request_body_text: str
):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_body=True)
            headers = {'Content-Type': content_type} if content_type else {}
            response = client.post('https://example.org:8080/foo', headers=headers, content=body)
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes'].get('http.request.body.text') == expected_http_request_body_text


@pytest.mark.parametrize(*CAPTURE_JSON_BODY_PARAMETERS)
async def test_async_httpx_client_instrumentation_with_capture_json_body(
    exporter: TestExporter, content_type: str, body: Any, expected_http_request_body_text: str
):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_body=True)
            response = await client.post(
                'https://example.org:8080/foo', headers={'Content-Type': content_type}, content=body
            )
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert span['attributes'].get('http.request.body.text') == expected_http_request_body_text


CAPTURE_FULL_REQUEST_ATTRIBUTES = {
    *REQUEST_ATTRIBUTES,
    'http.request.header.content-type',
    'http.request.header.content-length',
    'http.request.body.text',
}


def test_httpx_client_capture_stream_body(exporter: TestExporter):
    def stream():
        yield b'{"hello": '
        yield b'"world"}'

    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_body=True)
            response = client.post(
                'https://example.org:8080/foo', headers={'Content-Type': 'application/json'}, content=stream()
            )
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    # Streaming bodies aren't captured
    assert 'http.request.body.json' not in span['attributes']


def test_httpx_client_capture_full_request(exporter: TestExporter):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, capture_request_body=True)
            response = client.post('https://example.org:8080/foo', json={'hello': 'world'})
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in CAPTURE_FULL_REQUEST_ATTRIBUTES)


async def test_async_httpx_client_capture_full_request(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, capture_request_body=True)
            response = await client.post('https://example.org:8080/foo', json={'hello': 'world'})
            checker(response)

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in CAPTURE_FULL_REQUEST_ATTRIBUTES)


def test_httpx_client_capture_full(exporter: TestExporter):
    with check_traceparent_header() as checker:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(
                client, capture_headers=True, capture_request_body=True, capture_response_body=True
            )
            response = client.post('https://example.org:8080/foo', json={'hello': 'world'})
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'http.request.header.host': ('example.org:8080',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': (IsStr(),),
                    'http.request.header.content-length': (IsStr(),),
                    'http.request.header.content-type': ('application/json',),
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.text":{"type":"object"}}}',
                    'http.request.body.text': '{"hello":"world"}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.response.header.host': ('example.org:8080',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': (IsStr(),),
                    'http.response.header.content-length': (IsStr(),),
                    'http.response.header.content-type': ('application/json',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
                    'http.target': '/foo',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_capture_full',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
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
                client, capture_headers=True, capture_request_body=True, capture_response_body=True
            )
            response = await client.post('https://example.org:8080/foo', json={'hello': 'world'})
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'http.request.header.host': ('example.org:8080',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': (IsStr(),),
                    'http.request.header.content-length': (IsStr(),),
                    'http.request.header.content-type': ('application/json',),
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.text":{"type":"object"}}}',
                    'http.request.body.text': '{"hello":"world"}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.response.header.host': ('example.org:8080',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': (IsStr(),),
                    'http.response.header.content-length': (IsStr(),),
                    'http.response.header.content-type': ('application/json',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
                    'http.target': '/foo',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_capture_full',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
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


def test_httpx_client_not_capture_response_body_on_wrong_encoding(exporter: TestExporter):
    def handler(request: Request):
        return httpx.Response(200, headers=request.headers, stream=httpx.ByteStream(b'\x80\x81\x82'))

    with check_traceparent_header() as checker:
        with httpx.Client(transport=httpx.MockTransport(handler=handler)) as client:
            logfire.instrument_httpx(client, capture_response_body=True)
            response = client.post('https://example.org:8080/foo')
            checker(response)

    spans = exporter.exported_spans_as_dict()
    assert spans == snapshot(
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_not_capture_response_body_on_wrong_encoding',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
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


def test_httpx_client_capture_request_form_data(exporter: TestExporter):
    assert len({code.co_filename for code in CODES_FOR_METHODS_WITH_DATA_PARAM}) == 1
    assert [code.co_name for code in CODES_FOR_METHODS_WITH_DATA_PARAM] == ['request', 'stream', 'request', 'stream']

    with httpx.Client(transport=create_transport()) as client:
        logfire.instrument_httpx(client, capture_request_body=True)
        client.post('https://example.org:8080/foo', data={'form': 'values'})

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'POST',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'http.request.body.form': '{"form":"values"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.form":{"type":"object"}}}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
                },
            }
        ]
    )


def test_httpx_client_capture_request_text_body(exporter: TestExporter):
    with httpx.Client(transport=create_transport()) as client:
        logfire.instrument_httpx(client, capture_request_body=True)
        client.post('https://example.org:8080/foo', headers={'Content-Type': 'text/plain'}, content='hello')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'POST',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'POST',
                    'http.request.method': 'POST',
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.text":{"type":"object"}}}',
                    'http.request.body.text': 'hello',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
                },
            }
        ]
    )


def test_is_json_type():
    assert is_json_type('application/json')
    assert is_json_type(' APPLICATION / JSON ')
    assert is_json_type('application/json; charset=utf-8')
    assert is_json_type('application/json; charset=potato; foo=bar')
    assert is_json_type('application/json+ld')
    assert is_json_type('application/x-json+ld')
    assert is_json_type('application/ld+xml+json')
    assert not is_json_type('json')
    assert not is_json_type('json/application')
    assert not is_json_type('text/json')
    assert not is_json_type('other/json')
    assert not is_json_type('')
    assert not is_json_type('application/json-x')
    assert not is_json_type('application//json')


async def test_httpx_client_capture_all(exporter: TestExporter):
    with check_traceparent_header() as checker:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_all=True)
            response = await client.post('https://example.org:8080/foo', json={'hello': 'world'})
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
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'POST example.org/foo',
                    'http.request.header.host': ('example.org:8080',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
                    'http.request.header.content-length': ('17',),
                    'http.request.header.content-type': ('application/json',),
                    'logfire.json_schema': '{"type":"object","properties":{"http.request.body.text":{"type":"object"}}}',
                    'http.request.body.text': '{"hello":"world"}',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.response.header.host': ('example.org:8080',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': (
                        IsAnyStr(regex='^gzip, deflate(?:, br|, zstd|, br, zstd)?$'),
                    ),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.content-length': ('17',),
                    'http.response.header.content-type': ('application/json',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
                    'http.target': '/foo',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_capture_all',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
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


async def test_httpx_client_no_capture_empty_body(exporter: TestExporter):
    async with httpx.AsyncClient(transport=create_transport()) as client:
        logfire.instrument_httpx(client, capture_request_body=True)
        await client.get('https://example.org:8080/foo')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'https://example.org:8080/foo',
                    'url.full': 'https://example.org:8080/foo',
                    'http.host': 'example.org',
                    'server.address': 'example.org',
                    'network.peer.address': 'example.org',
                    'net.peer.port': 8080,
                    'server.port': 8080,
                    'network.peer.port': 8080,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/foo',
                },
            }
        ]
    )


def test_httpx_capture_all_and_other_flags_should_warn(exporter: TestExporter):
    with httpx.Client(transport=create_transport()) as client:
        with pytest.warns(
            UserWarning, match='You should use either `capture_all` or the specific capture parameters, not both.'
        ):
            logfire.instrument_httpx(client, capture_all=True, capture_request_body=True)


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.httpx': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.httpx)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_httpx()` requires the `opentelemetry-instrumentation-httpx` package.
You can install this with:
    pip install 'logfire[httpx]'\
""")
