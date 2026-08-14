from __future__ import annotations

import importlib
import inspect
import io
import warnings
from typing import Any
from unittest import mock

import pytest
import requests
from dirty_equals import IsFloat, IsNumeric, IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.trace import Span

import logfire
import logfire._internal.integrations.requests
from logfire.testing import TestExporter


@pytest.fixture(autouse=True)  # only applies within this module
def instrument_requests(monkeypatch: pytest.MonkeyPatch):
    # The following monkeypatching is similar in purpose to the mock transport in test_httpx.py.

    def send(self: Any, request: requests.PreparedRequest, **kwargs: Any):
        if str(request.url).endswith('/transport-error'):
            raise transport_error
        response = requests.Response()
        response.status_code = 200
        response.headers = request.headers
        response.request = request
        if not kwargs.get('stream'):
            if str(request.url).endswith('/empty'):
                response._content = b''
            elif str(request.url).endswith('/large'):
                response._content = b'x' * (1024 * 1024 + 1)
            else:
                response._content = b'{"password":"secret","value":1}'
        return response

    transport_error = requests.ConnectionError('transport')
    monkeypatch.setattr(requests.Session, 'send', send)

    def instrument(*args: Any, **kwargs: Any) -> None:
        RequestsInstrumentor().uninstrument()
        logfire.instrument_requests(*args, **kwargs)

    instrument()
    instrument.__dict__['transport_error'] = transport_error
    yield instrument
    instrumentor = RequestsInstrumentor()
    instrumentor.uninstrument()


@pytest.mark.anyio
async def test_requests_instrumentation(exporter: TestExporter):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        response = requests.get('https://example.org:8080/foo')
        # Validation of context propagation: ensure that the traceparent header contains the trace ID
        traceparent_header = response.headers['traceparent']
        assert f'{trace_id:032x}' == traceparent_header.split('-')[1]

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
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
                    'user_agent.original': IsStr(),
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
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'example.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'example.org',
                                        'net.peer.port': 8080,
                                    },
                                    'total': IsNumeric(),
                                }
                            ],
                            'total': IsNumeric(),
                        },
                        'http.client.request.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'example.org',
                                        'server.port': 8080,
                                    },
                                    'total': IsFloat(),
                                }
                            ],
                            'total': IsFloat(),
                        },
                    },
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
                    'code.filepath': 'test_requests.py',
                    'code.lineno': 123,
                    'code.function': 'test_requests_instrumentation',
                    'logfire.msg_template': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test span',
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'example.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'example.org',
                                        'net.peer.port': 8080,
                                    },
                                    'total': IsNumeric(),
                                }
                            ],
                            'total': IsNumeric(),
                        },
                        'http.client.request.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'example.org',
                                        'server.port': 8080,
                                    },
                                    'total': IsFloat(),
                                }
                            ],
                            'total': IsFloat(),
                        },
                    },
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.requests': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.requests)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_requests()` requires the `opentelemetry-instrumentation-requests` package.
You can install this with:
    pip install 'logfire[requests]'\
""")


def _request_span(exporter: TestExporter) -> dict[str, Any]:
    return exporter.exported_spans_as_dict(parse_json_attributes=True)[-1]


@pytest.mark.parametrize(
    ('options', 'headers_captured', 'request_captured', 'response_captured'),
    [
        ({}, False, False, False),
        ({'capture_headers': True}, True, False, False),
        ({'capture_request_body': True}, False, True, False),
        ({'capture_response_body': True}, False, False, True),
        ({'capture_all': True}, True, True, True),
    ],
)
def test_body_capture_flags(
    exporter: TestExporter,
    instrument_requests: Any,
    options: dict[str, bool],
    headers_captured: bool,
    request_captured: bool,
    response_captured: bool,
) -> None:
    instrument_requests(**options)
    requests.post('https://example.org', data='request text', headers={'X-Test': 'header value'})
    attributes = _request_span(exporter)['attributes']
    assert ('http.request.header.x-test' in attributes) is headers_captured
    assert ('http.response.header.x-test' in attributes) is headers_captured
    assert ('http.request.body.text' in attributes) is request_captured
    assert ('http.response.body.text' in attributes) is response_captured


@pytest.mark.parametrize('body', ['123', 'true', 'null', '"hello"'])
def test_raw_json_scalars(exporter: TestExporter, instrument_requests: Any, body: str) -> None:
    instrument_requests(capture_request_body=True)
    requests.post('https://example.org', data=body, headers={'Content-Type': 'application/json'})
    assert _request_span(exporter)['attributes']['http.request.body.text'] == body


def test_json_scrubbing(exporter: TestExporter, instrument_requests: Any) -> None:
    instrument_requests(capture_all=True)
    requests.post(
        'https://example.org',
        data='{"nested":{"password":"secret"}, "value":1}',
        headers={'Content-Type': 'application/json'},
    )
    attributes = _request_span(exporter)['attributes']
    assert attributes['http.request.body.text'] == {
        'nested': {'password': "[Scrubbed due to 'password']"},
        'value': 1,
    }
    assert attributes['http.response.body.text'] == {
        'password': "[Scrubbed due to 'password']",
        'value': 1,
    }


def test_body_types_and_charsets(exporter: TestExporter, instrument_requests: Any) -> None:
    instrument_requests(capture_request_body=True)
    requests.post('https://example.org/str', data='café', headers={'Content-Type': 'text/plain; charset=ascii'})
    requests.post(
        'https://example.org/bytes',
        data='café'.encode('latin-1'),
        headers={'Content-Type': 'text/plain; charset=latin-1'},
    )
    requests.post('https://example.org/memoryview', data=memoryview(b'view'))
    requests.post(
        'https://example.org/memoryview-bad',
        data=memoryview(b'\xff'),
        headers={'Content-Type': 'text/plain; charset=utf-8'},
    )
    # Requests accepts bytearray at runtime even though types-requests omits it from `_Data`.
    requests.post('https://example.org/bytearray', data=bytearray(b'array'))  # pyright: ignore[reportArgumentType]
    requests.post('https://example.org/bad', data=b'\xff', headers={'Content-Type': 'text/plain; charset=utf-8'})
    requests.post('https://example.org/unknown', data=b'body', headers={'Content-Type': 'text/plain; charset=unknown'})
    requests.post(
        'https://example.org/invalid-parameter',
        data='café'.encode('latin-1'),
        headers={'Content-Type': 'text/plain; invalid; charset=latin-1'},
    )
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert [span['attributes'].get('http.request.body.text') for span in spans] == [
        'café',
        'café',
        'view',
        None,
        'array',
        None,
        None,
        'café',
    ]


def test_empty_and_large_bodies_are_skipped(exporter: TestExporter, instrument_requests: Any) -> None:
    instrument_requests(capture_all=True)
    requests.post('https://example.org/empty', data=b'')
    requests.post('https://example.org/large', data=b'x' * (1024 * 1024 + 1))
    requests.post('https://example.org/large-str', data='x' * (1024 * 1024 + 1))
    requests.post('https://example.org/large-memoryview', data=memoryview(b'x' * (1024 * 1024 + 1)))

    for span in exporter.exported_spans_as_dict():
        assert 'http.request.body.text' not in span['attributes']

    first_two_spans = exporter.exported_spans_as_dict()[:2]
    assert all('http.response.body.text' not in span['attributes'] for span in first_two_spans)


@pytest.mark.parametrize('body', ['', memoryview(b'')])
def test_other_empty_body_types_are_skipped(body: Any) -> None:
    span = mock.Mock(spec=Span)
    logfire._internal.integrations.requests._capture_body(  # pyright: ignore[reportPrivateUsage]
        span, body, None, 'http.request.body.text'
    )
    span.set_attribute.assert_not_called()


@pytest.mark.parametrize('content_type', ['multipart/form-data; boundary=x', 'multipart/mixed', 'multipart/related'])
def test_multipart_is_skipped(exporter: TestExporter, instrument_requests: Any, content_type: str) -> None:
    instrument_requests(capture_all=True)
    requests.post('https://example.org', data=b'body', headers={'Content-Type': content_type})
    attributes = _request_span(exporter)['attributes']
    assert 'http.request.body.text' not in attributes
    assert 'http.response.body.text' not in attributes


def test_streams_are_not_consumed(exporter: TestExporter, instrument_requests: Any) -> None:
    instrument_requests(capture_all=True)
    file = io.BytesIO(b'file')
    file.seek(2)
    generator = (part for part in [b'a', b'b'])
    requests.post('https://example.org/file', data=file)
    requests.post('https://example.org/generator', data=generator)
    requests.get('https://example.org/stream', stream=True)
    assert file.tell() == 2
    assert next(generator) == b'a'
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 3
    assert all('http.request.body.text' not in span['attributes'] for span in spans)
    assert ['http.response.body.text' in span['attributes'] for span in spans] == [True, True, False]


def test_hooks_and_exceptions(exporter: TestExporter, instrument_requests: Any) -> None:
    calls: list[str] = []

    def request_hook(span: Span, request: requests.PreparedRequest) -> None:
        calls.append('request')
        assert span.attributes['http.request.body.text'] == 'body'  # type: ignore[attr-defined]

    def response_hook(span: Span, request: requests.PreparedRequest, response: requests.Response) -> None:
        calls.append('response')
        assert span.attributes['http.response.body.text'] == '{"password":"secret","value":1}'  # type: ignore[attr-defined]

    # The original three arguments remain positional for backward compatibility.
    instrument_requests(None, request_hook, response_hook, capture_all=True)
    requests.post('https://example.org', data='body')
    assert calls == ['request', 'response']

    error = RuntimeError('hook')

    def failing_hook(span: Span, request: requests.PreparedRequest) -> None:
        raise error

    instrument_requests(capture_request_body=True, request_hook=failing_hook)
    with pytest.raises(RuntimeError) as exc_info:
        requests.get('https://example.org')
    assert exc_info.value is error

    # Falsey and non-callable hooks keep the instrumentor's existing no-op behavior.
    instrument_requests(capture_all=True, request_hook=0, response_hook=object())
    requests.get('https://example.org')


def test_transport_exception_identity(instrument_requests: Any) -> None:
    instrument_requests(capture_all=True)
    with pytest.raises(requests.ConnectionError) as exc_info:
        requests.get('https://example.org/transport-error')
    assert exc_info.value is instrument_requests.__dict__['transport_error']


def test_warning_stacklevel_and_signature(instrument_requests: Any) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        instrument_requests(capture_all=True, capture_request_body=True)
    assert caught[-1].filename == __file__
    capture_all = inspect.signature(logfire.instrument_requests).parameters['capture_all']
    assert capture_all.kind is inspect.Parameter.KEYWORD_ONLY
