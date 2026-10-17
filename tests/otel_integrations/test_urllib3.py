from __future__ import annotations

import importlib
from unittest import mock

import pytest
import urllib3
from inline_snapshot import snapshot
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

import logfire
import logfire._internal.integrations.urllib3
from logfire.testing import TestExporter


@pytest.fixture
def instrument_urllib3():
    logfire.instrument_urllib3()
    yield
    URLLib3Instrumentor().uninstrument()


@pytest.mark.vcr()
def test_urllib3_instrumentation(exporter: TestExporter, instrument_urllib3: None):
    with logfire.span('test span') as span:
        assert span.context
        trace_id = span.context.trace_id
        response = urllib3.PoolManager().request('GET', 'https://httpbin.org/status/200')

    assert response.status == 200
    exported_spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(exported_spans) == 2

    request_span, parent_span = exported_spans
    assert request_span['name'] == 'GET'
    assert request_span['context']['trace_id'] == trace_id
    assert request_span['parent'] == parent_span['context']
    assert (
        request_span['attributes']
        | snapshot(
            {
                'http.method': 'GET',
                'http.request.method': 'GET',
                'http.url': 'https://httpbin.org/status/200',
                'url.full': 'https://httpbin.org/status/200',
                'http.status_code': 200,
                'http.response.status_code': 200,
            }
        )
        == request_span['attributes']
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.urllib3': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.urllib3)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_urllib3()` requires the `opentelemetry-instrumentation-urllib3` package.
You can install this with:
    pip install 'logfire[urllib3]'\
""")


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
