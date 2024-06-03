import importlib
from unittest import mock

import pytest
from django.http import HttpResponse
from django.test import Client
from inline_snapshot import snapshot

import logfire
import logfire._internal
import logfire._internal.integrations
import logfire._internal.integrations.django
from logfire.testing import TestExporter


def test_good_route(client: Client, exporter: TestExporter):
    logfire.instrument_django()
    response: HttpResponse = client.get(  # type: ignore
        '/django_test_app/123/?very_long_query_param_name=very+long+query+param+value&foo=1'
    )
    assert response.status_code == 200
    assert response.content == b'item_id: 123'

    # TODO route and target should consistently start with /, including in the name/message
    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET django_test_app/<int:item_id>/',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /django_test_app/123/ ? foo='1' & very_long…aram_name='very long…ram value'",
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'net.host.port': 80,
                    'http.url': 'http://testserver/django_test_app/123/?very_long_query_param_name=very+long+query+param+value&foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'http.flavor': '1.1',
                    'http.route': 'django_test_app/<int:item_id>/',
                    'http.status_code': 200,
                    'http.target': '/django_test_app/123/',
                },
            }
        ]
    )


def test_error_route(client: Client, exporter: TestExporter):
    logfire.instrument_django()
    response: HttpResponse = client.get('/django_test_app/bad/?foo=1')  # type: ignore
    assert response.status_code == 400

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET django_test_app/bad/',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /django_test_app/bad/ ? foo='1'",
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'net.host.port': 80,
                    'http.url': 'http://testserver/django_test_app/bad/?foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'http.flavor': '1.1',
                    'http.route': 'django_test_app/bad/',
                    'http.status_code': 400,
                    'http.target': '/django_test_app/bad/',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'BadRequest',
                            'exception.message': 'bad request',
                            'exception.stacktrace': 'django.core.exceptions.BadRequest: bad request',
                            'exception.escaped': 'False',
                        },
                    }
                ],
            }
        ]
    )


def test_no_matching_route(client: Client, exporter: TestExporter):
    logfire.instrument_django()
    response: HttpResponse = client.get('/django_test_app/nowhere/?foo=1')  # type: ignore
    assert response.status_code == 404

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "GET /django_test_app/nowhere/ ? foo='1'",
                    'http.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'net.host.port': 80,
                    'http.url': 'http://testserver/django_test_app/nowhere/?foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'http.flavor': '1.1',
                    'http.status_code': 404,
                    'http.target': '/django_test_app/nowhere/',
                },
            }
        ]
    )


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.django': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.django)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_django()` requires the `opentelemetry-instrumentation-django` package.
You can install this with:
    pip install 'logfire[django]'\
""")
