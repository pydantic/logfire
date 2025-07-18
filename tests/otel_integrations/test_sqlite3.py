import importlib
import sqlite3
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor

import logfire
import logfire._internal.integrations.sqlite3
from logfire.testing import TestExporter


def test_sqlite3_instrumentation(exporter: TestExporter):
    logfire.instrument_sqlite3()

    with sqlite3.connect(':memory:') as conn:
        cur = conn.cursor()
        cur.execute('DROP TABLE IF EXISTS test')
        cur.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')
        cur.execute('INSERT INTO test (id, name) VALUES (1, "test")')
        values = cur.execute('SELECT * FROM test').fetchall()
        assert values == [(1, 'test')]

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
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'DROP TABLE IF EXISTS test',
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
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))',
                    },
                },
                {
                    'name': 'INSERT',
                    'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                    'parent': None,
                    'start_time': 5000000000,
                    'end_time': 6000000000,
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'INSERT INTO test (id, name) VALUES (1, "test")',
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'INSERT INTO test (id, name) VALUES (1, "test")',
                    },
                },
                {
                    'name': 'SELECT',
                    'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                    'parent': None,
                    'start_time': 7000000000,
                    'end_time': 8000000000,
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'SELECT * FROM test',
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'SELECT * FROM test',
                    },
                },
            ]
        )

    conn.close()
    SQLite3Instrumentor().uninstrument()


def test_instrument_sqlite3_connection(exporter: TestExporter):
    with sqlite3.connect(':memory:') as conn:
        cur = conn.cursor()
        cur.execute('DROP TABLE IF EXISTS test')
        cur.execute('CREATE TABLE test (id INT PRIMARY KEY, name VARCHAR(255))')

        conn = logfire.instrument_sqlite3(conn)
        cur = conn.cursor()
        cur.execute('INSERT INTO test (id, name) VALUES (1, "test")')
        values = cur.execute('SELECT * FROM test').fetchall()
        assert values == [(1, 'test')]

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
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'INSERT INTO test (id, name) VALUES (1, "test")',
                    },
                },
                {
                    'name': 'SELECT',
                    'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                    'parent': None,
                    'start_time': 3000000000,
                    'end_time': 4000000000,
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'SELECT * FROM test',
                        'db.system': 'sqlite',
                        'db.name': '',
                        'db.statement': 'SELECT * FROM test',
                    },
                },
            ]
        )
        spans_before_uninstrument = len(exporter.exported_spans_as_dict())
        conn: sqlite3.Connection = SQLite3Instrumentor().uninstrument_connection(conn)
        cur = conn.cursor()
        cur.execute('INSERT INTO test (id, name) VALUES (2, "test-2")')
        assert len(exporter.exported_spans_as_dict()) == spans_before_uninstrument
        values = cur.execute('SELECT * FROM test').fetchall()
        assert values == [(1, 'test'), (2, 'test-2')]
    conn.close()


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.sqlite3': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.sqlite3)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_sqlite3()` requires the `opentelemetry-instrumentation-sqlite3` package.
You can install this with:
    pip install 'logfire[sqlite3]'\
""")
