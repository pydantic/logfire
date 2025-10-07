from __future__ import annotations

import importlib
from unittest import mock

import aiohttp
import aiohttp.test_utils
import aiohttp.web
import pytest
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from dirty_equals import IsInt, IsStr, IsTuple
from inline_snapshot import snapshot
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.trace import Span

import logfire
import logfire._internal.integrations.aiohttp_client
from logfire.testing import TestExporter


async def mock_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Standard mock handler that returns received headers and a custom server header."""
    return aiohttp.web.json_response(
        {'received_headers': dict(request.headers), 'status': 'ok'},
        headers={'Server-Custom-Header': 'server-value'},
    )


@pytest.fixture
def test_app() -> aiohttp.web.Application:
    """Pytest fixture that creates a test aiohttp application with standard routes."""
    app = aiohttp.web.Application()
    app.router.add_get('/test', mock_handler)
    return app


def request_hook(span: Span, params: TraceRequestStartParams) -> None:
    """Custom request hook that adds custom attributes and logs request details."""
    span.set_attribute('custom.request.name', 'Custom Request')


def response_hook(span: Span, params: TraceRequestEndParams | TraceRequestExceptionParams) -> None:
    """Custom response hook that adds custom attributes and logs response details."""
    if isinstance(params, TraceRequestEndParams):
        span.set_attribute('custom.response.content', 'Custom Content')
    else:
        span.set_attribute('custom.response.exception', 'Custom Exception')


@pytest.mark.anyio
async def test_instrument_aiohttp():
    """Test that aiohttp client instrumentation modifies the ClientSession class."""
    try:
        cls = aiohttp.ClientSession
        original_init = cls.__init__
        assert cls.__init__ is original_init
        logfire.instrument_aiohttp_client()
        assert cls.__init__ is not original_init
    finally:
        AioHttpClientInstrumentor().uninstrument()


@pytest.mark.anyio
async def test_aiohttp_client_no_capture_headers_with_hooks(exporter: TestExporter, test_app: aiohttp.web.Application):
    """Test that aiohttp client works when capture_headers=False but hooks are provided."""

    try:
        async with aiohttp.test_utils.TestServer(test_app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(request_hook=request_hook, response_hook=response_hook)

            async with aiohttp.ClientSession() as session:
                custom_headers = {
                    'User-Agent': 'test-client/1.0',
                    'X-Custom-Header': 'custom-value',
                }

                async with session.get(
                    f'http://localhost:{server.port}/test',  # type: ignore
                    headers=custom_headers,
                ) as response:
                    await response.json()
    finally:
        AioHttpClientInstrumentor().uninstrument()

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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET localhost/test',
                    'custom.request.name': 'Custom Request',
                    'custom.response.content': 'Custom Content',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/test',
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_headers(exporter: TestExporter, test_app: aiohttp.web.Application):
    """Test that aiohttp client captures headers when configured to do so."""

    try:
        async with aiohttp.test_utils.TestServer(test_app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(
                capture_headers=True, request_hook=request_hook, response_hook=response_hook
            )

            async with aiohttp.ClientSession() as session:
                custom_headers = {
                    'User-Agent': 'test-client/1.0',
                    'X-Custom-Header': 'custom-value',
                    'Authorization': 'Bearer test-token',
                }

                async with session.get(
                    f'http://localhost:{server.port}/test',  # type: ignore
                    headers=custom_headers,
                ) as response:
                    await response.json()
    finally:
        AioHttpClientInstrumentor().uninstrument()

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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET localhost/test',
                    'http.request.header.User-Agent': ('test-client/1.0',),
                    'http.request.header.X-Custom-Header': ('custom-value',),
                    'http.request.header.Authorization': ("[Scrubbed due to 'Auth']",),
                    'custom.request.name': 'Custom Request',
                    'http.response.header.Server-Custom-Header': ('server-value',),
                    'http.response.header.Content-Type': ('application/json; charset=utf-8',),
                    'http.response.header.Content-Length': IsTuple(IsStr()),
                    'http.response.header.Date': IsTuple(IsStr()),
                    'http.response.header.Server': IsTuple(IsStr()),
                    'custom.response.content': 'Custom Content',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/test',
                    'logfire.scrubbed': '[{"path": ["attributes", "http.request.header.Authorization"], "matched_substring": "Auth"}]',
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_exception_handling(exporter: TestExporter):
    """Test that aiohttp client handles exceptions and creates appropriate spans."""

    try:
        logfire.instrument_aiohttp_client(capture_headers=True)

        async with aiohttp.ClientSession() as session:
            # Test connection error by trying to connect to a non-existent host
            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get('http://non-existent-host-12345.example.com/test'):
                    pass
    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'http://non-existent-host-12345.example.com/test',
                    'url.full': 'http://non-existent-host-12345.example.com/test',
                    'http.host': 'non-existent-host-12345.example.com',
                    'server.address': 'non-existent-host-12345.example.com',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET non-existent-host-12345.example.com/test',
                    'error.type': 'ClientConnectorDNSError',
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'http.target': '/test',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'aiohttp.client_exceptions.ClientConnectorDNSError',
                            'exception.message': IsStr(),
                            'exception.stacktrace': IsStr(),
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_exception_handling_with_hooks(exporter: TestExporter):
    """Test that aiohttp client handles exceptions and creates appropriate spans."""

    try:
        logfire.instrument_aiohttp_client(capture_headers=True, request_hook=request_hook, response_hook=response_hook)

        async with aiohttp.ClientSession() as session:
            # Test connection error by trying to connect to a non-existent host
            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get('http://non-existent-host-12345.example.com/test'):
                    pass
    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'http://non-existent-host-12345.example.com/test',
                    'url.full': 'http://non-existent-host-12345.example.com/test',
                    'http.host': 'non-existent-host-12345.example.com',
                    'server.address': 'non-existent-host-12345.example.com',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET non-existent-host-12345.example.com/test',
                    'custom.request.name': 'Custom Request',
                    'error.type': 'ClientConnectorDNSError',
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'custom.response.exception': 'Custom Exception',
                    'http.target': '/test',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'aiohttp.client_exceptions.ClientConnectorDNSError',
                            'exception.message': IsStr(),
                            'exception.stacktrace': IsStr(),
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_response_body(exporter: TestExporter, test_app: aiohttp.web.Application):
    """Test that aiohttp client captures response body and headers when configured to do so."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'good': 'response'})

        test_app.router.add_get('/body', handler)

        async with aiohttp.test_utils.TestServer(test_app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_headers=True, capture_response_body=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/body') as response:  # type: ignore
                    assert await response.json() == {'good': 'response'}
                    assert await response.read() == b'{"good": "response"}'

    finally:
        AioHttpClientInstrumentor().uninstrument()

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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET localhost/body',
                    'http.response.header.Content-Type': ('application/json; charset=utf-8',),
                    'http.response.header.Content-Length': IsTuple(IsStr()),
                    'http.response.header.Date': IsTuple(IsStr()),
                    'http.response.header.Server': IsTuple(IsStr()),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/body',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_aiohttp_client.py',
                    'code.function': 'test_aiohttp_client_capture_response_body',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_response_body_exception(exporter: TestExporter):
    """Test that aiohttp client captures response body when configured to do so."""

    try:
        logfire.instrument_aiohttp_client(capture_response_body=True)

        async with aiohttp.ClientSession() as session:
            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get('http://non-existent-host-12345.example.com/test'):
                    pass

    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.request.method': 'GET',
                    'http.url': 'http://non-existent-host-12345.example.com/test',
                    'url.full': 'http://non-existent-host-12345.example.com/test',
                    'http.host': 'non-existent-host-12345.example.com',
                    'server.address': 'non-existent-host-12345.example.com',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET non-existent-host-12345.example.com/test',
                    'error.type': 'ClientConnectorDNSError',
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                    'http.target': '/test',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'aiohttp.client_exceptions.ClientConnectorDNSError',
                            'exception.message': IsStr(),
                            'exception.stacktrace': IsStr(),
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_encoding_error_handling(exporter: TestExporter, test_app: aiohttp.web.Application):
    """Test that capture_body_if_text handles encoding errors gracefully."""

    try:

        async def handler_with_invalid_encoding(_request: aiohttp.web.Request) -> aiohttp.web.Response:
            invalid_bytes = b'\xff\xfe\x00\x00invalid utf-8 \x80\x81\x82'
            return aiohttp.web.Response(body=invalid_bytes, content_type='text/plain')

        test_app.router.add_get('/encoding-error', handler_with_invalid_encoding)

        async with aiohttp.test_utils.TestServer(test_app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_response_body=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/encoding-error') as response:  # type: ignore
                    await response.read()
    finally:
        AioHttpClientInstrumentor().uninstrument()

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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET localhost/encoding-error',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/encoding-error',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_aiohttp_client.py',
                    'code.function': 'test_aiohttp_client_encoding_error_handling',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aiohttp_client': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aiohttp_client)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.
You can install this with:
    pip install 'logfire[aiohttp-client]'\
""")
