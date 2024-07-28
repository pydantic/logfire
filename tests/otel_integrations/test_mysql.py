from unittest import mock

import mysql.connector
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter


def connect_and_execute_query():
    cnx = mysql.connector.connect(database='test')
    cursor = cnx.cursor()
    query = 'SELECT * FROM test'
    cursor.execute(query)
    return cnx, query


def test_mysql_instrumentation(exporter: TestExporter):
    with mock.patch('mysql.connector.connect') as mock_connect:
        mock_cursor = mock.MagicMock()
        mock_connect.return_value.cursor.return_value = mock_cursor
        mock_connect.return_value.user = 'test_user'
        logfire.instrument_mysql()
        connect_and_execute_query()
        assert exporter.exported_spans_as_dict() == snapshot(
            [
                {
                    'name': 'SELECT',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 2000000000,
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'SELECT * FROM test',
                        'db.system': 'mysql',
                        'db.statement': 'SELECT * FROM test',
                        'db.user': 'test_user',
                    },
                }
            ]
        )
