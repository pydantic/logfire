from __future__ import annotations

import importlib
from typing import Any
from unittest import mock

import pytest
import urllib3
from dirty_equals import IsFloat, IsNumeric
from inline_snapshot import snapshot
from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor

import logfire
import logfire._internal.integrations.urllib3
from logfire.testing import TestExporter

_COMMON_OLD_METRIC_ATTRS = {
    'http.host': 'example.org',
    'http.method': 'GET',
    'http.scheme': 'https',
    'http.status_code': 200,
    'net.peer.name': 'example.org',
    'net.peer.port': 8080,
}

_COMMON_NEW_METRIC_ATTRS = {
    'http.request.method': 'GET',
    'http.response.status_code': 200,
    'server.address': 'example.org',
    'server.port': 8080,
}


def _expected_metrics() -> dict[str, Any]:
    return {
        'http.client.duration': {
            'details': [{'attributes': _COMMON_OLD_METRIC_ATTRS, 'total': IsNumeric()}],
            'total': IsNumeric(),
        },
        'http.client.request.duration': {
            'details': [{'attributes': _COMMON_NEW_METRIC_ATTRS, 'total': IsFloat()}],
            'total': IsFloat(),
        },
        'http.client.request.size': {
            'details': [{'attributes': _COMMON_OLD_METRIC_ATTRS, 'total': IsNumeric()}],
            'total': IsNumeric(),
        },
        'http.client.request.body.size': {
            'details': [{'attributes': _COMMON_NEW_METRIC_ATTRS, 'total': IsNumeric()}],
            'total': IsNumeric(),
        },
        'http.client.response.size': {
            'details': [{'attributes': _COMMON_OLD_METRIC_ATTRS, 'total': IsNumeric()}],
            'total': IsNumeric(),
        },
        'http.client.response.body.size': {
            'details': [{'attributes': _COMMON_NEW_METRIC_ATTRS, 'total': IsNumeric()}],
            'total': IsNumeric(),
        },
    }


@pytest.fixture(autouse=True)
def instrument_urllib3(monkeypatch: pytest.MonkeyPatch):
    def mock_urlopen(self: Any, method: str, url: str, **kwargs: Any) -> urllib3.response.HTTPResponse:
        return urllib3.response.HTTPResponse(
            status=200,
            headers={},
        )

    monkeypatch.setattr(urllib3.HTTPConnectionPool, 'urlopen', mock_urlopen)

    logfire.instrument_urllib3()
    yield
    URLLib3Instrumentor().uninstrument()


@pytest.mark.anyio
async def test_urllib3_instrumentation(exporter: TestExporter):
    with logfire.span('test span'):
        http = urllib3.PoolManager()
        http.request('GET', 'https://example.org:8080/foo')

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
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET example.org/foo',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
                    'logfire.metrics': _expected_metrics(),
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
                    'code.filepath': 'test_urllib3.py',
                    'code.lineno': 123,
                    'code.function': 'test_urllib3_instrumentation',
                    'logfire.msg_template': 'test span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test span',
                    'logfire.metrics': _expected_metrics(),
                },
            },
        ]
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
