from __future__ import annotations

import importlib
import sys
from unittest import mock

import mysql.connector
import pytest
from dirty_equals import IsInt
from inline_snapshot import snapshot
from opentelemetry.instrumentation.mysql import MySQLInstrumentor
from testcontainers.mysql import MySqlContainer

import logfire
import logfire._internal.integrations.mysql
from logfire.testing import TestExporter

pytestmark = pytest.mark.skipif(sys.version_info < (3, 9), reason='MySQL testcontainers has problems in 3.8')


@pytest.fixture(scope='module')
def mysql_container():
    with MySqlContainer() as mysql_container:
        yield mysql_container


def get_mysql_connection(mysql_container: MySqlContainer):
    host = mysql_container.get_container_host_ip()
    port = mysql_container.get_exposed_port(3306)
    connection = mysql.connector.connect(host=host, port=port, user='test', password='test', database='test')
    return connection


def test_mysql_instrumentation(exporter: TestExporter, mysql_container: MySqlContainer):
    logfire.instrument_mysql()

    with get_mysql_connection(mysql_container) as conn:
        with conn.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS test')
            cursor.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')

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
    MySQLInstrumentor().uninstrument()


def test_instrument_mysql_connection(exporter: TestExporter, mysql_container: MySqlContainer):
    with get_mysql_connection(mysql_container) as conn:
        with conn.cursor() as cursor:
            cursor.execute('DROP TABLE IF EXISTS test')
            cursor.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')

        assert exporter.exported_spans_as_dict() == []

        conn = logfire.instrument_mysql(conn)
        with conn.cursor() as cursor:
            cursor.execute('INSERT INTO test (id, name) VALUES (1, "test")')

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

        conn = MySQLInstrumentor().uninstrument_connection(conn)  # type: ignore
        with conn.cursor() as cursor:
            cursor.execute('INSERT INTO test (id, name) VALUES (2, "test-2")')

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
