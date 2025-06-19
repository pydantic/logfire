from __future__ import annotations

import importlib
from unittest import mock

import pytest
from dirty_equals import IsInt
from inline_snapshot import snapshot
from opentelemetry.instrumentation.mysql import MySQLInstrumentor

import logfire
import logfire._internal.integrations.mysql
from logfire.testing import TestExporter


@pytest.fixture
def mock_mysql_connection():
    mock_conn = mock.MagicMock()
    mock_conn.user = 'test'
    mock_conn.database = 'test'
    mock_conn.server_host = 'localhost'
    mock_conn.server_port = 3306
    mock_cursor = mock.MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


def test_mysql_instrumentation(exporter: TestExporter, mock_mysql_connection):  # type: ignore
    mock_instrumented_conn = logfire.instrument_mysql(mock_mysql_connection)  # type: ignore

    with mock_instrumented_conn.cursor() as cursor:  # type: ignore
        cursor.execute('DROP TABLE IF EXISTS test')  # type: ignore
        cursor.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')  # type: ignore

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'DROP',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'DROP TABLE IF EXISTS test',
                    'db.system': 'mysql',
                    'db.name': 'test',
                    'db.statement': 'DROP TABLE IF EXISTS test',
                    'db.user': 'test',
                    'net.peer.name': 'localhost',
                    'net.peer.port': IsInt(),
                },
            },
            {
                'name': 'CREATE',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))',
                    'db.system': 'mysql',
                    'db.name': 'test',
                    'db.statement': 'CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))',
                    'db.user': 'test',
                    'net.peer.name': 'localhost',
                    'net.peer.port': IsInt(),
                },
            },
        ]
    )
    MySQLInstrumentor().uninstrument_connection(mock_instrumented_conn)  # type: ignore


def test_instrument_mysql_connection(exporter: TestExporter, mock_mysql_connection):  # type: ignore
    with mock_mysql_connection.cursor() as cursor:  # type: ignore
        cursor.execute('DROP TABLE IF EXISTS test')  # type: ignore
        cursor.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')  # type: ignore

    assert exporter.exported_spans_as_dict() == []

    mock_instrumented_conn = logfire.instrument_mysql(mock_mysql_connection)  # type: ignore
    with mock_instrumented_conn.cursor() as cursor:  # type: ignore
        cursor.execute('INSERT INTO test (id, name) VALUES (1, "test")')  # type: ignore

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'INSERT',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'INSERT INTO test (id, name) VALUES (1, "test")',
                    'db.system': 'mysql',
                    'db.name': 'test',
                    'db.statement': 'INSERT INTO test (id, name) VALUES (1, "test")',
                    'db.user': 'test',
                    'net.peer.name': 'localhost',
                    'net.peer.port': IsInt(),
                },
            }
        ]
    )

    mock_uninstrumented_conn = MySQLInstrumentor().uninstrument_connection(mock_instrumented_conn)  # type: ignore
    with mock_uninstrumented_conn.cursor() as cursor:  # type: ignore
        cursor.execute('INSERT INTO test (id, name) VALUES (2, "test-2")')  # type: ignore

    assert len(exporter.exported_spans_as_dict()) == 1


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.mysql': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.mysql)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_mysql()` requires the `opentelemetry-instrumentation-mysql` package.
You can install this with:
    pip install 'logfire[mysql]'\
""")
