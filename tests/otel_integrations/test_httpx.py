import importlib
from unittest import mock

import httpx
import pytest
from httpx import Request
from inline_snapshot import snapshot
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor, RequestInfo, ResponseInfo
from opentelemetry.trace import Span

import logfire
import logfire._internal.integrations.httpx
from logfire.testing import TestExporter

pytestmark = pytest.mark.anyio


# The purpose of this mock transport is to ensure that the traceparent header is provided
# without needing to actually make a network request
def create_transport() -> httpx.MockTransport:
    def handler(request: Request):
        return httpx.Response(200, headers=request.headers)

    return httpx.MockTransport(handler)


def test_httpx_client_instrumentation(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client)
            try:
                response = client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            # Validation of context propagation: ensure that the traceparent header contains the trace ID
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'code.function': 'test_httpx_client_instrumentation',
                    'logfire.msg_template': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test span',
                },
            },
        ]
    )


async def test_async_httpx_client_instrumentation(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'code.function': 'test_async_httpx_client_instrumentation',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_httpx_client_instrumentation_with_capture_request_headers(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True)
            try:
                response = client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
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
                    'code.function': 'test_httpx_client_instrumentation_with_capture_request_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    def request_hook(span: Span, request: RequestInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, request_hook=request_hook)
            try:
                response = client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[2:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
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
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
                    'potato': 'potato',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_instrumentation_with_capture_request_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


async def test_async_httpx_client_instrumentation_with_capture_request_headers(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
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
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_request_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    def request_hook(span: Span, request: RequestInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, request_hook=request_hook)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[2:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
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
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
                    'potato': 'potato',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_request_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    async def async_request_hook(span: Span, request: RequestInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_request_headers=True, request_hook=async_request_hook)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[4:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 3, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 9, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 11000000000,
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
                    'http.request.header.host': ('example.org',),
                    'http.request.header.accept': ('*/*',),
                    'http.request.header.accept-encoding': ('gzip, deflate',),
                    'http.request.header.connection': ('keep-alive',),
                    'http.request.header.user-agent': ('python-httpx/0.28.1',),
                    'potato': 'potato',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 3, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_request_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_httpx_client_instrumentation_with_capture_response_headers(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_response_headers=True)
            try:
                response = client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
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
                    'code.function': 'test_httpx_client_instrumentation_with_capture_response_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    def response_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        with httpx.Client(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_response_headers=True, response_hook=response_hook)
            try:
                response = client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[2:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
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
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000002-0000000000000007-01',),
                    'potato': 'potato',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_httpx_client_instrumentation_with_capture_response_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


async def test_async_httpx_client_instrumentation_with_capture_response_headers(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_response_headers=True)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()
            traceparent_header = response.headers['traceparent']
            assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

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
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000003-01',),
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
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_response_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    def response_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_response_headers=True, response_hook=response_hook)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[2:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 2, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
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
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000002-0000000000000007-01',),
                    'potato': 'potato',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_response_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )

    async def async_response_hook(span: Span, request: RequestInfo, response: ResponseInfo) -> None:
        span.set_attribute('potato', 'potato')

    with logfire.span('test span') as span:
        async with httpx.AsyncClient(transport=create_transport()) as client:
            logfire.instrument_httpx(client, capture_response_headers=True, response_hook=async_response_hook)
            try:
                response = await client.get('https://example.org/')
            finally:
                HTTPXClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict()[4:] == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 3, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 3, 'span_id': 9, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 11000000000,
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
                    'http.response.header.host': ('example.org',),
                    'http.response.header.accept': ('*/*',),
                    'http.response.header.accept-encoding': ('gzip, deflate',),
                    'http.response.header.connection': ('keep-alive',),
                    'http.response.header.user-agent': ('python-httpx/0.28.1',),
                    'http.response.header.traceparent': ('00-00000000000000000000000000000003-000000000000000b-01',),
                    'potato': 'potato',
                    'http.target': '/',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 3, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_httpx.py',
                    'code.function': 'test_async_httpx_client_instrumentation_with_capture_response_headers',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.httpx': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.httpx)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_httpx()` requires the `opentelemetry-instrumentation-httpx` package.
You can install this with:
    pip install 'logfire[httpx]'\
""")
