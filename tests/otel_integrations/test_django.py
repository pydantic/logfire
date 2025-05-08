import importlib
from unittest import mock

import pytest
from dirty_equals import IsInt, IsNumeric
from django.http import HttpResponse
from django.test import Client
from inline_snapshot import snapshot
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import logfire
import logfire._internal
import logfire._internal.integrations
import logfire._internal.integrations.django
from logfire.testing import TestExporter
from tests.test_metrics import get_collected_metrics


def test_good_route(client: Client, exporter: TestExporter, metrics_reader: InMemoryMetricReader):
    logfire.instrument_django()
    response: HttpResponse = client.get(  # type: ignore
        '/django_test_app/123/?very_long_query_param_name=very+long+query+param+value&foo=1'
    )
    assert response.status_code == 200
    assert response.content == b'item_id: 123'

    assert get_collected_metrics(metrics_reader) == snapshot(
        [
            {
                'name': 'http.server.active_requests',
                'description': 'Number of active HTTP server requests.',
                'unit': '{request}',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'http.method': 'GET',
                                'http.scheme': 'http',
                                'http.flavor': '1.1',
                                'http.request.method': 'GET',
                                'url.scheme': 'http',
                            },
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'value': 0,
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': 2,
                    'is_monotonic': False,
                },
            },
            {
                'name': 'http.server.duration',
                'description': 'Measures the duration of inbound HTTP requests.',
                'unit': 'ms',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'http.method': 'GET',
                                'http.server_name': 'testserver',
                                'http.scheme': 'http',
                                'net.host.port': 80,
                                'http.flavor': '1.1',
                                'http.status_code': 200,
                                'http.target': 'django_test_app/<int:item_id>/',
                            },
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 1,
                            'sum': IsNumeric(),
                            'scale': 20,
                            'zero_count': 0,
                            'positive': {'offset': IsInt(), 'bucket_counts': [1]},
                            'negative': {'offset': 0, 'bucket_counts': [0]},
                            'flags': 0,
                            'min': IsNumeric(),
                            'max': IsNumeric(),
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': 1,
                },
            },
            {
                'name': 'http.server.request.duration',
                'description': 'Duration of HTTP server requests.',
                'unit': 's',
                'data': {
                    'data_points': [
                        {
                            'attributes': {
                                'http.request.method': 'GET',
                                'url.scheme': 'http',
                                'network.protocol.version': '1.1',
                                'http.route': 'django_test_app/<int:item_id>/',
                                'http.response.status_code': 200,
                            },
                            'start_time_unix_nano': IsInt(),
                            'time_unix_nano': IsInt(),
                            'count': 1,
                            'sum': IsNumeric(),
                            'scale': 20,
                            'zero_count': 0,
                            'positive': {'offset': IsInt(), 'bucket_counts': [1]},
                            'negative': {'offset': 0, 'bucket_counts': [0]},
                            'flags': 0,
                            'min': IsNumeric(),
                            'max': IsNumeric(),
                            'exemplars': [],
                        }
                    ],
                    'aggregation_temporality': 1,
                },
            },
        ]
    )

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
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.url': 'http://testserver/django_test_app/123/?very_long_query_param_name=very+long+query+param+value&foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'client.address': '127.0.0.1',
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.route': 'django_test_app/<int:item_id>/',
                    'http.status_code': 200,
                    'http.response.status_code': 200,
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
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.url': 'http://testserver/django_test_app/bad/?foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'client.address': '127.0.0.1',
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.route': 'django_test_app/bad/',
                    'http.status_code': 400,
                    'http.response.status_code': 400,
                    'http.target': '/django_test_app/bad/',
                    'logfire.level_num': 17,
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'django.core.exceptions.BadRequest',
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
                    'http.request.method': 'GET',
                    'http.server_name': 'testserver',
                    'http.scheme': 'http',
                    'url.scheme': 'http',
                    'net.host.port': 80,
                    'server.port': 80,
                    'http.url': 'http://testserver/django_test_app/nowhere/?foo=1',
                    'net.peer.ip': '127.0.0.1',
                    'client.address': '127.0.0.1',
                    'http.flavor': '1.1',
                    'network.protocol.version': '1.1',
                    'http.status_code': 404,
                    'http.response.status_code': 404,
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
