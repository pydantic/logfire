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
