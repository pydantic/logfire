import importlib
from unittest import mock

import aiohttp
import aiohttp.test_utils
import aiohttp.web
import pytest
from dirty_equals import IsInt, IsStr, IsTuple
from inline_snapshot import snapshot
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

import logfire
import logfire._internal.integrations.aiohttp_client
from logfire.testing import TestExporter


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
async def test_aiohttp_client_capture_headers(exporter: TestExporter):
    """Test that aiohttp client captures headers when configured to do so."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response(
                {'received_headers': dict(request.headers), 'status': 'ok'},
                headers={'Server-Custom-Header': 'server-value'},
            )

        app = aiohttp.web.Application()
        app.router.add_get('/test', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_all=True)

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

    spans = exporter.exported_spans_as_dict()

    http_spans = [span for span in spans if span['name'] == 'GET']
    assert len(http_spans) == 1

    http_span = http_spans[0]

    assert http_span == snapshot(
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
                'http.response.header.Server-Custom-Header': ('server-value',),
                'http.response.header.Content-Type': ('application/json; charset=utf-8',),
                'http.response.header.Content-Length': ('298',),
                'http.response.header.Date': IsTuple(IsStr()),
                'http.response.header.Server': IsTuple(IsStr()),
                'http.status_code': 200,
                'http.response.status_code': 200,
                'http.target': '/test',
                'logfire.scrubbed': '[{"path": ["attributes", "http.request.header.Authorization"], "matched_substring": "Auth"}]',
            },
        }
    )


@pytest.mark.anyio
async def test_aiohttp_client_exception_handling(exporter: TestExporter):
    """Test that aiohttp client handles exceptions and creates appropriate spans."""

    try:
        logfire.instrument_aiohttp_client(capture_all=True)

        async with aiohttp.ClientSession() as session:
            # Test connection error by trying to connect to a non-existent host
            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get('http://non-existent-host-12345.example.com/test'):
                    pass
    finally:
        AioHttpClientInstrumentor().uninstrument()

    spans = exporter.exported_spans_as_dict()

    http_spans = [span for span in spans if span['name'] == 'GET']
    assert len(http_spans) == 1

    http_span = http_spans[0]

    assert http_span == snapshot(
        {
            'name': 'GET',
            'context': {'trace_id': IsInt(), 'span_id': IsInt(), 'is_remote': False},
            'parent': None,
            'start_time': IsInt(),
            'end_time': IsInt(),
            'attributes': {
                'http.method': 'GET',
                'http.request.method': 'GET',
                'http.url': 'http://non-existent-host-12345.example.com/test',
                'url.full': 'http://non-existent-host-12345.example.com/test',
                'http.host': 'non-existent-host-12345.example.com',
                'server.address': 'non-existent-host-12345.example.com',
                'logfire.span_type': 'span',
                'error.type': 'ClientConnectorDNSError',
                'logfire.msg': 'GET non-existent-host-12345.example.com/test',
                'http.target': '/test',
                'logfire.level_num': 17,
            },
            'events': [
                {
                    'name': 'exception',
                    'timestamp': IsInt(),
                    'attributes': {
                        'exception.type': 'aiohttp.client_exceptions.ClientConnectorDNSError',
                        'exception.message': IsStr(),
                        'exception.stacktrace': IsStr(),
                        'exception.escaped': 'False',
                    },
                }
            ],
        }
    )


@pytest.mark.anyio
async def test_aiohttp_client_exception_header_capture(exporter: TestExporter):
    """Test that request headers are captured even when exceptions occur."""

    try:
        logfire.instrument_aiohttp_client(capture_headers=True)

        async with aiohttp.ClientSession() as session:
            custom_headers = {
                'User-Agent': 'test-client/1.0',
                'X-Custom-Header': 'custom-value',
                'Authorization': 'Bearer test-token',
            }

            with pytest.raises(aiohttp.ClientConnectorError):
                async with session.get('http://non-existent-host-12345.example.com/test', headers=custom_headers):
                    pass
    finally:
        AioHttpClientInstrumentor().uninstrument()

    spans = exporter.exported_spans_as_dict()

    http_spans = [span for span in spans if span['name'] == 'GET']
    assert len(http_spans) == 1

    http_span = http_spans[0]

    assert http_span == snapshot(
        {
            'name': 'GET',
            'context': {'trace_id': IsInt(), 'span_id': IsInt(), 'is_remote': False},
            'parent': None,
            'start_time': IsInt(),
            'end_time': IsInt(),
            'attributes': {
                'http.method': 'GET',
                'http.request.method': 'GET',
                'http.url': 'http://non-existent-host-12345.example.com/test',
                'url.full': 'http://non-existent-host-12345.example.com/test',
                'http.host': 'non-existent-host-12345.example.com',
                'server.address': 'non-existent-host-12345.example.com',
                'logfire.span_type': 'span',
                'logfire.msg': 'GET non-existent-host-12345.example.com/test',
                'http.request.header.User-Agent': ('test-client/1.0',),
                'http.request.header.X-Custom-Header': ('custom-value',),
                'error.type': 'ClientConnectorDNSError',
                'http.request.header.Authorization': ("[Scrubbed due to 'Auth']",),
                'logfire.level_num': 17,
                'http.target': '/test',
                'logfire.scrubbed': '[{"path": ["attributes", "http.request.header.Authorization"], "matched_substring": "Auth"}]',
            },
            'events': [
                {
                    'name': 'exception',
                    'timestamp': IsInt(),
                    'attributes': {
                        'exception.type': 'aiohttp.client_exceptions.ClientConnectorDNSError',
                        'exception.message': IsStr(),
                        'exception.stacktrace': IsStr(),
                        'exception.escaped': 'False',
                    },
                }
            ],
        }
    )


def test_capture_all_with_specific_parameters_warning() -> None:
    """Test that a warning is issued when using capture_all with specific capture parameters."""

    try:
        with pytest.warns(
            UserWarning, match='You should use either `capture_all` or the specific capture parameters, not both.'
        ):
            logfire.instrument_aiohttp_client(capture_all=True, capture_headers=True, capture_request_body=True)
    finally:
        AioHttpClientInstrumentor().uninstrument()


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aiohttp_client': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aiohttp_client)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.
You can install this with:
    pip install 'logfire[aiohttp-client]'\
""")


@pytest.mark.anyio
async def test_run_hook_via_response_hook(exporter: TestExporter) -> None:
    """Test that run_hook is called when a response hook is provided."""
    
    try:
        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_get('/test', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            response_hook = mock.Mock()
            
            logfire.instrument_aiohttp_client(response_hook=response_hook)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/test'):  # type: ignore
                    pass

            response_hook.assert_called_once()
            
    finally:
        AioHttpClientInstrumentor().uninstrument()
