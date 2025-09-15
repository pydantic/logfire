from __future__ import annotations

import importlib
import os
from typing import Any
from unittest import mock

import aiohttp
import aiohttp.test_utils
import aiohttp.web
import pytest
from aiohttp.tracing import TraceRequestEndParams, TraceRequestExceptionParams, TraceRequestStartParams
from dirty_equals import IsInt, IsStr, IsTuple
from inline_snapshot import snapshot
from opentelemetry.instrumentation._semconv import _OpenTelemetrySemanticConventionStability  # type: ignore
from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
from opentelemetry.trace import Span

import logfire
import logfire._internal.integrations.aiohttp_client
from logfire.testing import TestExporter


def without_metrics(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove metrics from spans for comparison."""
    for span in spans:
        span['attributes'].pop('logfire.metrics', None)
    return spans


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
                'http.request.header.traceparent': ('00-00000000000000000000000000000001-0000000000000001-01',),
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
    assert len(body_spans) == 1  # Only reading the body once
    assert body_spans[0]['attributes']['http.response.body.text'] == '{"good": "response"}'


@pytest.mark.anyio
async def test_aiohttp_client_hooks(exporter: TestExporter):
    """Test that aiohttp client hooks receive the correct parameters."""

    request_hook_calls: list[dict[str, Any]] = []
    response_hook_calls: list[dict[str, Any]] = []

    def test_request_hook(span: Span, params: TraceRequestStartParams):
        request_hook_calls.append(
            {
                'params_type': type(params).__name__,
                'method': params.method,
                'url': str(params.url),
                'has_headers': hasattr(params, 'headers'),
            }
        )

    def test_response_hook(span: Span, params: TraceRequestEndParams | TraceRequestExceptionParams):
        response_hook_calls.append(
            {
                'params_type': type(params).__name__,
                'method': params.method,
                'url': str(params.url),
                'has_response': hasattr(params, 'response'),
                'has_exception': hasattr(params, 'exception'),
            }
        )

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_get('/test-hooks', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(request_hook=test_request_hook, response_hook=test_response_hook)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/test-hooks') as response:  # type: ignore
                    await response.json()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert request_hook_calls == snapshot(
        [
            {
                'params_type': 'TraceRequestStartParams',
                'method': 'GET',
                'url': IsStr(regex=r'.*\/test-hooks'),
                'has_headers': True,
            }
        ]
    )

    assert response_hook_calls == snapshot(
        [
            {
                'params_type': 'TraceRequestEndParams',
                'method': 'GET',
                'url': IsStr(regex=r'.*\/test-hooks'),
                'has_response': True,
                'has_exception': False,
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_basic_instrumentation(exporter: TestExporter):
    """Test basic aiohttp client instrumentation without capture_all."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_get('/basic', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client()

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/basic') as response:  # type: ignore
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
                'logfire.msg': IsStr(regex=r'GET localhost/basic'),
                'http.status_code': 200,
                'http.response.status_code': 200,
                'http.target': '/basic',
            },
        }
    )


@pytest.mark.anyio
async def test_aiohttp_client_instrumentation_old_semconv(exporter: TestExporter):
    """Test aiohttp client instrumentation with old semantic conventions."""

    with mock.patch.dict('os.environ', {'OTEL_SEMCONV_STABILITY_OPT_IN': ''}):
        try:

            async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
                return aiohttp.web.json_response({'status': 'ok'})

            app = aiohttp.web.Application()
            app.router.add_get('/old-semconv', handler)

            async with aiohttp.test_utils.TestServer(app) as server:
                await server.start_server()

                # Pick up the new value of OTEL_SEMCONV_STABILITY_OPT_IN
                _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore

                logfire.instrument_aiohttp_client()

                async with aiohttp.ClientSession() as session:
                    async with session.get(f'http://localhost:{server.port}/old-semconv') as response:  # type: ignore
                        await response.json()

                # Now let other tests get the original value set in conftest.py
                _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore

        finally:
            AioHttpClientInstrumentor().uninstrument()

    assert without_metrics(exporter.exported_spans_as_dict()) == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'http.method': 'GET',
                    'http.url': IsStr(),
                    'logfire.span_type': 'span',
                    'logfire.msg': IsStr(regex=r'GET localhost/old-semconv'),
                    'http.status_code': 200,
                    'http.target': '/old-semconv',
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_all_environment_variable(exporter: TestExporter):
    """Test that LOGFIRE_AIOHTTP_CLIENT_CAPTURE_ALL environment variable works."""

    with mock.patch.dict(os.environ, {'LOGFIRE_AIOHTTP_CLIENT_CAPTURE_ALL': 'true'}):
        try:

            async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
                return aiohttp.web.json_response({'response': 'data'})

            app = aiohttp.web.Application()
            app.router.add_post('/env-test', handler)

            async with aiohttp.test_utils.TestServer(app) as server:
                await server.start_server()

                # Pass capture_all=None so environment variable takes effect
                logfire.instrument_aiohttp_client()

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f'http://localhost:{server.port}/env-test',  # type: ignore
                        json={'test': 'data'},
                        headers={'Custom-Header': 'test-value'},
                    ) as response:
                        await response.json()
                        await response.read()

        finally:
            AioHttpClientInstrumentor().uninstrument()

    assert without_metrics(exporter.exported_spans_as_dict()) == snapshot(
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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': IsStr(regex=r'POST localhost/env-test'),
                    'http.request.header.Custom-Header': ('test-value',),
                    'http.request.header.traceparent': IsTuple(IsStr()),
                    'http.response.header.Content-Type': ('application/json; charset=utf-8',),
                    'http.response.header.Content-Length': IsTuple(IsStr()),
                    'http.response.header.Date': IsTuple(IsStr()),
                    'http.response.header.Server': IsTuple(IsStr()),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/env-test',
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
                    'code.function': 'test_aiohttp_client_capture_all_environment_variable',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"response": "data"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_aiohttp_client.py',
                    'code.function': 'test_aiohttp_client_capture_all_environment_variable',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"response": "data"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_capture_warnings(exporter: TestExporter):
    """Test that using capture_all with specific capture flags raises a warning."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_get('/warning-test', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            with pytest.warns(
                UserWarning, match='You should use either `capture_all` or the specific capture parameters, not both.'
            ):
                logfire.instrument_aiohttp_client(capture_all=True, capture_headers=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/warning-test') as response:  # type: ignore
                    await response.json()
    finally:
        AioHttpClientInstrumentor().uninstrument()


REQUEST_ATTRIBUTES: set[str] = {
    'http.request.header.Custom-Header',
    'http.request.header.traceparent',
}

RESPONSE_ATTRIBUTES: set[str] = {
    'http.response.header.Content-Type',
    'http.response.header.Content-Length',
    'http.response.header.Date',
    'http.response.header.Server',
}


@pytest.mark.parametrize(
    ('instrument_kwargs', 'expected_attributes'),
    [
        ({'capture_headers': True}, REQUEST_ATTRIBUTES | RESPONSE_ATTRIBUTES),
        ({'capture_all': True}, REQUEST_ATTRIBUTES | RESPONSE_ATTRIBUTES),
    ],
)
@pytest.mark.anyio
async def test_aiohttp_client_instrumentation_with_capture_headers(
    exporter: TestExporter, instrument_kwargs: dict[str, Any], expected_attributes: set[str]
):
    """Test aiohttp client instrumentation with different header capture configurations."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'status': 'ok'})

        app = aiohttp.web.Application()
        app.router.add_post('/headers-test', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(**instrument_kwargs)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://localhost:{server.port}/headers-test',  # type: ignore
                    json={'test': 'data'},
                    headers={'Custom-Header': 'test-value'},
                ) as response:
                    await response.json()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    span = exporter.exported_spans_as_dict()[0]
    assert all(key in span['attributes'] for key in expected_attributes), list(span['attributes'])


@pytest.mark.parametrize(
    ('instrument_kwargs', 'should_have_response_body'),
    [
        ({'capture_response_body': True}, True),
        ({'capture_response_body': False}, False),
        ({'capture_all': True}, True),
        ({}, False),
    ],
)
@pytest.mark.anyio
async def test_aiohttp_client_capture_response_body_flag(
    exporter: TestExporter, instrument_kwargs: dict[str, Any], should_have_response_body: bool
):
    """Test aiohttp client instrumentation with capture_response_body flag."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'response': 'data'})

        app = aiohttp.web.Application()
        app.router.add_post('/response-body-test', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(**instrument_kwargs)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://localhost:{server.port}/response-body-test',  # type: ignore
                    json={'test': 'data'},
                ) as response:
                    await response.json()  # This triggers response body reading
                    await response.read()  # Read again to ensure body capture works

    finally:
        AioHttpClientInstrumentor().uninstrument()

    spans = exporter.exported_spans_as_dict()

    # Check if we have response body spans
    body_spans = [span for span in spans if span['name'] == 'Reading response body']

    if should_have_response_body:
        assert len(body_spans) >= 1, f'Expected response body spans but got {len(body_spans)}'
        # Check that at least one span has the response body text
        body_texts = [span['attributes'].get('http.response.body.text') for span in body_spans]
        assert any('response' in str(text) and 'data' in str(text) for text in body_texts if text), (
            f'Expected response body content but got: {body_texts}'
        )
    else:
        assert len(body_spans) == 0, f'Expected no response body spans but got {len(body_spans)}'


@pytest.mark.anyio
async def test_aiohttp_client_no_capture_empty_body(exporter: TestExporter):
    """Test that empty request/response bodies are captured as empty strings."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.Response(text='', status=204)

        app = aiohttp.web.Application()
        app.router.add_get('/empty', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_all=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/empty') as response:  # type: ignore
                    await response.read()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert without_metrics(exporter.exported_spans_as_dict()) == snapshot(
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
                    'logfire.msg': IsStr(regex=r'GET localhost/empty'),
                    'http.request.header.traceparent': IsTuple(IsStr()),
                    'http.response.header.Content-Type': ('text/plain; charset=utf-8',),
                    'http.response.header.Date': IsTuple(IsStr()),
                    'http.response.header.Server': IsTuple(IsStr()),
                    'http.status_code': 204,
                    'http.response.status_code': 204,
                    'http.target': '/empty',
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
                    'code.function': 'test_aiohttp_client_no_capture_empty_body',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_aiohttp_client_not_capture_response_body_on_wrong_encoding(exporter: TestExporter):
    """Test that response body with wrong encoding is not captured."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            # Return invalid UTF-8 bytes
            return aiohttp.web.Response(body=b'\x80\x81\x82', content_type='text/plain')

        app = aiohttp.web.Application()
        app.router.add_get('/bad-encoding', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_all=True)

            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:{server.port}/bad-encoding') as response:  # type: ignore
                    await response.read()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    spans = exporter.exported_spans_as_dict()

    body_spans = [span for span in spans if span['name'] == 'Reading response body']
    if body_spans:
        # Should not have captured the body text due to encoding error
        assert 'http.response.body.text' not in body_spans[0]['attributes']


@pytest.mark.anyio
async def test_aiohttp_client_capture_all(exporter: TestExporter):
    """Test aiohttp client capture_all functionality similar to httpx."""

    try:

        async def handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
            return aiohttp.web.json_response({'good': 'response'})

        app = aiohttp.web.Application()
        app.router.add_post('/capture-all', handler)

        async with aiohttp.test_utils.TestServer(app) as server:
            await server.start_server()

            logfire.instrument_aiohttp_client(capture_all=True)

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f'http://localhost:{server.port}/capture-all',  # type: ignore
                    json={'hello': 'world'},
                    headers={'Custom-Header': 'test-value'},
                ) as response:
                    await response.json()
                    await response.read()

    finally:
        AioHttpClientInstrumentor().uninstrument()

    assert without_metrics(exporter.exported_spans_as_dict()) == snapshot(
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
                    'http.url': IsStr(),
                    'url.full': IsStr(),
                    'http.host': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                    'logfire.span_type': 'span',
                    'logfire.msg': IsStr(regex=r'POST localhost/capture-all'),
                    'http.request.header.Custom-Header': ('test-value',),
                    'http.request.header.traceparent': IsTuple(IsStr()),
                    'http.response.header.Content-Type': ('application/json; charset=utf-8',),
                    'http.response.header.Content-Length': IsTuple(IsStr()),
                    'http.response.header.Date': IsTuple(IsStr()),
                    'http.response.header.Server': IsTuple(IsStr()),
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'http.target': '/capture-all',
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
                    'code.function': 'test_aiohttp_client_capture_all',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Reading response body',
                    'logfire.msg': 'Reading response body',
                    'logfire.span_type': 'span',
                    'http.response.body.text': '{"good": "response"}',
                    'logfire.json_schema': '{"type":"object","properties":{"http.response.body.text":{"type":"object"}}}',
                },
            },
            {
                'name': 'Reading response body',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_aiohttp_client.py',
                    'code.function': 'test_aiohttp_client_capture_all',
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


def test_missing_opentelemetry_dependency() -> None:
    """Test that missing opentelemetry dependency raises appropriate error."""

    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.aiohttp_client': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.aiohttp_client)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_aiohttp_client()` requires the `opentelemetry-instrumentation-aiohttp-client` package.
You can install this with:
    pip install 'logfire[aiohttp-client]'\
""")
