from django.test import Client

from logfire.testing import TestExporter


def test_good_route(client: Client, exporter: TestExporter):
    response = client.get('/django_test_app/123/')
    assert response.status_code == 200
    assert response.content == b'item_id: 123'

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'GET django_test_app/<int:item_id>/',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'logfire.msg': 'GET django_test_app/<int:item_id>/',
                'http.method': 'GET',
                'http.server_name': 'testserver',
                'http.scheme': 'http',
                'net.host.port': 80,
                'http.url': 'http://testserver/django_test_app/123/',
                'net.peer.ip': '127.0.0.1',
                'http.flavor': '1.1',
                'http.route': 'django_test_app/<int:item_id>/',
                'http.status_code': 200,
            },
        }
    ]


def test_error_route(client: Client, exporter: TestExporter):
    response = client.get('/django_test_app/bad/')
    assert response.status_code == 400

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'GET django_test_app/bad/',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 3000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'logfire.msg': 'GET django_test_app/bad/',
                'http.method': 'GET',
                'http.server_name': 'testserver',
                'http.scheme': 'http',
                'net.host.port': 80,
                'http.url': 'http://testserver/django_test_app/bad/',
                'net.peer.ip': '127.0.0.1',
                'http.flavor': '1.1',
                'http.route': 'django_test_app/bad/',
                'http.status_code': 400,
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


def test_no_matching_route(client: Client, exporter: TestExporter):
    response = client.get('/django_test_app/nowhere/')
    assert response.status_code == 404

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            # TODO: This should be more helpful, e.g. 'GET django_test_app/nowhere/' or 'GET <not found>'
            'name': 'GET',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'logfire.msg': 'GET',
                'http.method': 'GET',
                'http.server_name': 'testserver',
                'http.scheme': 'http',
                'net.host.port': 80,
                'http.url': 'http://testserver/django_test_app/nowhere/',
                'net.peer.ip': '127.0.0.1',
                'http.flavor': '1.1',
                'http.status_code': 404,
            },
        }
    ]
