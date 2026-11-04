from __future__ import annotations

from unittest import mock

import pytest
import urllib3
from dirty_equals import IsFloat, IsNumeric
from inline_snapshot import snapshot
from opentelemetry.instrumentation.urllib3 import RequestInfo, URLLib3Instrumentor
from opentelemetry.sdk.trace import Span

import logfire
from logfire.testing import TestExporter


@pytest.fixture
def instrument_urllib3():
    logfire.instrument_urllib3()
    yield
    URLLib3Instrumentor().uninstrument()


@pytest.mark.vcr()
def test_urllib3_instrumentation(exporter: TestExporter, instrument_urllib3: None):
    with logfire.span('test span'):
        response = urllib3.PoolManager().request('GET', 'https://httpbin.org/status/200')

    assert response.status == 200
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
                    'http.url': 'https://httpbin.org/status/200',
                    'url.full': 'https://httpbin.org/status/200',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET httpbin.org/status/200',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
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
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': IsFloat(),
                                }
                            ],
                            'total': IsFloat(),
                        },
                        'http.client.request.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.request.body.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.response.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.response.body.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                    },
                    'http.target': '/status/200',
                },
            },
            {
                'name': 'test span',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_urllib3.py',
                    'code.function': 'test_urllib3_instrumentation',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test span',
                    'logfire.msg': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.metrics': {
                        'http.client.duration': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
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
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': IsFloat(),
                                }
                            ],
                            'total': IsFloat(),
                        },
                        'http.client.request.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.request.body.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.response.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.host': 'httpbin.org',
                                        'http.method': 'GET',
                                        'http.scheme': 'https',
                                        'http.status_code': 200,
                                        'net.peer.name': 'httpbin.org',
                                        'net.peer.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                        'http.client.response.body.size': {
                            'details': [
                                {
                                    'attributes': {
                                        'http.request.method': 'GET',
                                        'http.response.status_code': 200,
                                        'server.address': 'httpbin.org',
                                        'server.port': 443,
                                    },
                                    'total': 0,
                                }
                            ],
                            'total': 0,
                        },
                    },
                },
            },
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.urllib3': None}):
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_urllib3()
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_urllib3()` requires the `opentelemetry-instrumentation-urllib3` package.
You can install a compatible version with:
    pip install -U 'logfire[urllib3]'\
""")


def test_internal_opentelemetry_import_error() -> None:
    module = 'opentelemetry.instrumentation.urllib3.version'
    with mock.patch.dict('sys.modules', {module: None}):
        with pytest.raises(ModuleNotFoundError) as exc_info:
            logfire.instrument_urllib3()
    assert exc_info.value.name == module


def test_unsupported_opentelemetry_version() -> None:
    with mock.patch('opentelemetry.instrumentation.urllib3.version.__version__', '0.64b0'):
        with pytest.raises(RuntimeError, match='opentelemetry-instrumentation-urllib3 >= 0.65b0'):
            logfire.instrument_urllib3()


@pytest.mark.parametrize('custom_filter', [False, True])
@pytest.mark.parametrize(
    'parameter',
    [
        'AWSAccessKeyId',
        'Signature',
        'sig',
        'X-Goog-Signature',
        'X-Amz-Signature',
        'X-Amz-Credential',
        'X-Amz-Security-Token',
    ],
)
def test_signed_url_redaction(exporter: TestExporter, custom_filter: bool, parameter: str):
    url = f'https://example.com/object?{parameter}=private-credential&public=value'
    logfire.instrument_urllib3(url_filter=(lambda _: url) if custom_filter else None)
    try:
        with mock.patch(
            'urllib3.connectionpool.HTTPConnectionPool._make_request',
            return_value=urllib3.HTTPResponse(status=200),
        ):
            urllib3.PoolManager().request('GET', url)
        attributes = exporter.exported_spans_as_dict()[0]['attributes']
        redacted = '%5BREDACTED%5D' if parameter.startswith('X-Amz-') else 'REDACTED'
        for key in ('http.url', 'url.full'):
            assert attributes[key] == f'https://example.com/object?{parameter}={redacted}&public=value'
        assert 'private-credential' not in repr(exporter.exported_spans_as_dict())
    finally:
        URLLib3Instrumentor().uninstrument()


def test_invalid_filtered_url(exporter: TestExporter):
    logfire.instrument_urllib3(url_filter=lambda _: 'https://[private-credential')
    try:
        with mock.patch(
            'urllib3.connectionpool.HTTPConnectionPool._make_request',
            return_value=urllib3.HTTPResponse(status=200),
        ):
            response = urllib3.PoolManager().request('GET', 'https://example.com/')
        assert response.status == 200
        attributes = exporter.exported_spans_as_dict()[0]['attributes']
        assert attributes['http.url'] == attributes['url.full'] == '[REDACTED]'
        assert 'private-credential' not in repr(exporter.exported_spans_as_dict())
    finally:
        URLLib3Instrumentor().uninstrument()


def test_urllib3_options_forwarded():
    request_hook = mock.Mock()
    response_hook = mock.Mock()
    tracer_provider = mock.Mock()
    meter_provider = mock.Mock()
    with mock.patch.object(URLLib3Instrumentor, 'instrument') as instrument:
        logfire.instrument_urllib3(
            excluded_urls='health',
            request_hook=request_hook,
            response_hook=response_hook,
            url_filter=lambda url: url + '?sig=secret',
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            captured_request_headers=['content-type'],
        )
    options = dict(instrument.call_args.kwargs)
    assert options.pop('url_filter')('https://example.com') == 'https://example.com?sig=REDACTED'
    assert options == {
        'excluded_urls': 'health',
        'request_hook': request_hook,
        'response_hook': response_hook,
        'tracer_provider': tracer_provider,
        'meter_provider': meter_provider,
        'captured_request_headers': ['content-type'],
    }


def test_urllib3_hooks_exclusion_and_repeated_installation(exporter: TestExporter, caplog: pytest.LogCaptureFixture):
    pool = urllib3.HTTPSConnectionPool('example.com')

    def request_hook(span: Span, pool: urllib3.HTTPConnectionPool, request: RequestInfo) -> None:
        span.set_attribute('test.request_method', request.method)

    def response_hook(span: Span, pool: urllib3.HTTPConnectionPool, response: urllib3.HTTPResponse) -> None:
        span.set_attribute('test.response_status', response.status)

    logfire.instrument_urllib3(
        excluded_urls='/health',
        request_hook=request_hook,
        response_hook=response_hook,
        captured_request_headers=['x-example'],
        sensitive_headers=['x-example'],
    )
    try:
        logfire.instrument_urllib3(excluded_urls='.*')
        assert 'Attempting to instrument while already instrumented' in caplog.text

        with mock.patch.object(
            pool, '_make_request', side_effect=[urllib3.HTTPResponse(status=200), urllib3.HTTPResponse(status=200)]
        ):
            pool.urlopen('GET', '/health')
            response = pool.urlopen('POST', '/example', b'private-body', {'X-Example': 'private-credential'})
        assert response.status == 200
        (span,) = exporter.exported_spans_as_dict(parse_json_attributes=True)
        assert span['attributes']['test.request_method'] == 'POST'
        assert span['attributes']['test.response_status'] == 200
        assert span['attributes']['http.request.header.x_example'] == ('[REDACTED]',)
        assert 'private-body' not in repr(span)
        assert 'private-credential' not in repr(span)
    finally:
        URLLib3Instrumentor().uninstrument()


def test_urllib3_request_failure_restores_context(exporter: TestExporter, instrument_urllib3: None):
    error = urllib3.exceptions.ProtocolError('connection dropped')
    with logfire.span('parent'):
        with mock.patch.object(urllib3.HTTPConnectionPool, '_make_request', side_effect=error):
            with pytest.raises(urllib3.exceptions.ProtocolError) as exc_info:
                urllib3.PoolManager().request('GET', 'https://example.com/', retries=False)
        assert exc_info.value is error
        logfire.info('after request')

    request, after, parent = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert request['parent'] == after['parent'] == parent['context']
    assert request['events'][0]['name'] == 'exception'
    assert request['events'][0]['attributes']['exception.message'] == 'connection dropped'
