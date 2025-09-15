from __future__ import annotations

from typing import Any

import aiohttp
import aiohttp.test_utils
import aiohttp.web
import pytest
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from dirty_equals import IsInt, IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.trace import Span

import logfire
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
        # Clean up instrumentation to avoid test isolation issues
        AioHttpClientInstrumentor().uninstrument()


@pytest.mark.anyio
async def test_aiohttp_client_capture_headers(exporter: TestExporter):
    """Test that aiohttp client captures headers when configured to do so."""

    try:
        # Create a simple handler that echoes back the request headers
        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response(
                {'received_headers': dict(request.headers), 'status': 'ok'},
                headers={'Server-Custom-Header': 'server-value'},
            )

        # Create test server
        app = aiohttp.web.Application()
        app.router.add_get('/test', handler)

        # Start server
        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            # Instrument aiohttp client with header capture enabled
            logfire.instrument_aiohttp_client(capture_all=True)

            # Make request with custom headers
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
        # Clean up instrumentation to avoid test isolation issues
        AioHttpClientInstrumentor().uninstrument()

    # Check that spans were exported with header information
    spans = exporter.exported_spans_as_dict()

    # Filter to get the HTTP client span
    http_spans = [span for span in spans if span['name'] == 'GET']
    assert len(http_spans) == 1

    http_span = http_spans[0]

    # Verify that request and response headers are captured
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
                'http.response.header.User-Agent': ('test-client/1.0',),
                'http.response.header.X-Custom-Header': ('custom-value',),
                'http.response.header.Authorization': ("[Scrubbed due to 'Auth']",),
                'http.response.header.traceparent': ('00-00000000000000000000000000000001-0000000000000001-01',),
                'http.status_code': 200,
                'http.response.status_code': 200,
                'http.target': '/test',
                'logfire.scrubbed': '[{"path": ["attributes", "http.request.header.Authorization"], "matched_substring": "Auth"}, {"path": ["attributes", "http.response.header.Authorization"], "matched_substring": "Auth"}]',
            },
        }
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_response_body(exporter: TestExporter):
    """Test that aiohttp client captures response body when configured to do so."""

    try:
        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'good': 'response'})

        app = aiohttp.web.Application()
        app.router.add_get('/body', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_all=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/body') as response:  # type: ignore
                    await response.json()
    finally:
        AioHttpClientInstrumentor().uninstrument()

    spans = exporter.exported_spans_as_dict()
    body_spans = [span for span in spans if span['name'] == 'Reading response body']
    assert len(body_spans) == 1 # Only reading the body once
    assert body_spans[0]['attributes']['http.response.body.text'] == '{"good": "response"}'


@pytest.mark.anyio
async def test_aiohttp_client_hooks(exporter: TestExporter):
    """Test that aiohttp client hooks receive the correct parameters."""

    # Track what parameters the hooks receive
    request_hook_calls: list[dict[str, Any]] = []
    response_hook_calls: list[dict[str, Any]] = []

    def test_request_hook(span: Span, params: TraceRequestStartParams):
        request_hook_calls.append({
            'span': span,
            'params_type': type(params).__name__,
            'method': params.method,
            'url': str(params.url),
            'has_headers': hasattr(params, 'headers')
        })

    def test_response_hook(span: Span, params: TraceRequestEndParams | TraceRequestExceptionParams):
        response_hook_calls.append({
            'span': span,
            'params_type': type(params).__name__,
            'method': params.method,
            'url': str(params.url),
            'has_response': hasattr(params, 'response'),
            'has_exception': hasattr(params, 'exception')
        })

    try:
        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_get('/test-hooks', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(
                request_hook=test_request_hook,
                response_hook=test_response_hook
            )

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/test-hooks') as response:  # type: ignore
                    await response.json()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    # Verify hooks were called with correct parameters
    assert len(request_hook_calls) == 1
    assert len(response_hook_calls) == 1
    
    # Verify request hook received TraceRequestStartParams
    request_call = request_hook_calls[0]
    assert request_call['params_type'] == 'TraceRequestStartParams'
    assert request_call['method'] == 'GET'
    assert '/test-hooks' in request_call['url']
    assert request_call['has_headers'] is True

    # Verify response hook received TraceRequestEndParams
    response_call = response_hook_calls[0]
    assert response_call['params_type'] == 'TraceRequestEndParams'
    assert response_call['method'] == 'GET'
    assert '/test-hooks' in response_call['url']
    assert response_call['has_response'] is True
    assert response_call['has_exception'] is False
