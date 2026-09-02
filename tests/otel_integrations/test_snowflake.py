from __future__ import annotations

from typing import Any

import pytest
from inline_snapshot import snapshot
from snowflake.connector.connection import SnowflakeConnection
from snowflake.connector.cursor import SnowflakeCursor

import logfire
from logfire._internal.exporters.test import TestExporter


class FakeConnection:
    def __init__(self, **kwargs: Any) -> None:
        self.account = kwargs.get('account')
        self.warehouse = kwargs.get('warehouse')
        self.database = kwargs.get('database')
        self.schema = kwargs.get('schema')
        self.role = kwargs.get('role')
        self.log_max_query_length = 10000
        self._reuse_results = False

    def cursor(self) -> SnowflakeCursor:
        return SnowflakeCursor(self)  # type: ignore[arg-type]


class FakeSnowflakeConnection(SnowflakeConnection):
    def __init__(self, **kwargs: Any) -> None:
        # Deliberately skip SnowflakeConnection.__init__, which opens a real network
        # connection. Set only the private attributes its account/warehouse/database/
        # schema/role properties read (confirmed to be plain `self._account`-style reads).
        self._account = kwargs.get('account')
        self._warehouse = kwargs.get('warehouse')
        self._database = kwargs.get('database')
        self._schema = kwargs.get('schema')
        self._role = kwargs.get('role')
        self._log_max_query_length = 10000
        self._reuse_results = False

    def cursor(self, cursor_class: type = SnowflakeCursor) -> SnowflakeCursor:
        # Override rather than inherit: the real cursor() checks internal connection
        # state that __init__ never set up here.
        return cursor_class(self)


@pytest.fixture(autouse=True)
def fake_snowflake_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(**kwargs: Any) -> FakeConnection:
        return FakeConnection(**kwargs)

    monkeypatch.setattr('snowflake.connector.connect', fake_connect)


@pytest.fixture(autouse=True)
def fake_snowflake_execute(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_execute(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any):
        self._sfqid = 'fake-sfqid-1'
        self._total_rowcount = 3
        return self

    def fake_executemany(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any):
        self._sfqid = 'fake-sfqid-2'
        self._total_rowcount = len(seqparams)
        return self

    monkeypatch.setattr(SnowflakeCursor, 'execute', fake_execute)
    monkeypatch.setattr(SnowflakeCursor, 'executemany', fake_executemany)


def test_instrument_connect(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    import snowflake.connector

    conn = snowflake.connector.connect(
        account='my_account',
        warehouse='my_wh',
        database='my_db',
        schema='my_schema',
        role='my_role',
        password='super-secret',
    )
    assert conn.account == 'my_account'

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'snowflake connect',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_snowflake.py',
                    'code.function': 'test_instrument_connect',
                    'code.lineno': 123,
                    'logfire.msg_template': 'snowflake connect',
                    'logfire.msg': 'snowflake connect',
                    'logfire.span_type': 'span',
                    'account': 'my_account',
                    'warehouse': 'my_wh',
                    'database': 'my_db',
                    'schema': 'my_schema',
                    'role': 'my_role',
                    'logfire.json_schema': '{"type":"object","properties":{"account":{},"warehouse":{},"database":{},"schema":{},"role":{}}}',
                },
            }
        ]
    )


def test_instrument_execute(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role')
    cursor = conn.cursor()
    cursor.execute('select * from my_table where id = %s', (1,))

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'snowflake execute',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_snowflake.py',
                    'code.function': 'test_instrument_execute',
                    'code.lineno': 123,
                    'command': 'select * from my_table where id = %s',
                    'params': '[1]',
                    'account': 'my_account',
                    'warehouse': 'my_wh',
                    'database': 'my_db',
                    'schema': 'my_schema',
                    'role': 'my_role',
                    'logfire.msg_template': 'snowflake execute {command}',
                    'logfire.msg': 'snowflake execute select * from my_table where id = %s',
                    'logfire.span_type': 'span',
                    'sfqid': 'fake-sfqid-1',
                    'rowcount': 3,
                    'logfire.json_schema': '{"type":"object","properties":{"command":{},"params":{"type":"array","x-python-datatype":"tuple"},"account":{},"warehouse":{},"database":{},"schema":{},"role":{},"sfqid":{},"rowcount":{}}}',
                },
            }
        ]
    )


def test_instrument_executemany(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role')
    cursor = conn.cursor()
    cursor.executemany('insert into my_table values (%s)', [(1,), (2,), (3,)])

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'snowflake executemany',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_snowflake.py',
                    'code.function': 'test_instrument_executemany',
                    'code.lineno': 123,
                    'command': 'insert into my_table values (%s)',
                    'seqparams': '[[1],[2],[3]]',
                    'account': 'my_account',
                    'warehouse': 'my_wh',
                    'database': 'my_db',
                    'schema': 'my_schema',
                    'role': 'my_role',
                    'logfire.msg_template': 'snowflake executemany {command}',
                    'logfire.msg': 'snowflake executemany insert into my_table values (%s)',
                    'logfire.span_type': 'span',
                    'sfqid': 'fake-sfqid-2',
                    'rowcount': 3,
                    'logfire.json_schema': '{"type":"object","properties":{"command":{},"seqparams":{"type":"array","items":{"type":"array","x-python-datatype":"tuple"}},"account":{},"warehouse":{},"database":{},"schema":{},"role":{},"sfqid":{},"rowcount":{}}}',
                },
            }
        ]
    )


def test_instrument_single_connection(exporter: TestExporter) -> None:
    conn = FakeSnowflakeConnection(
        account='my_account', warehouse='my_wh', database='my_db', schema='my_schema', role='my_role'
    )
    logfire.instrument_snowflake(conn)

    cursor = conn.cursor()
    cursor.execute('select 1')

    # A second, uninstrumented connection must not produce spans.
    other_conn = FakeSnowflakeConnection(account='other_account')
    other_conn.cursor().execute('select 2')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'snowflake execute',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_snowflake.py',
                    'code.function': 'test_instrument_single_connection',
                    'code.lineno': 123,
                    'command': 'select 1',
                    'params': 'null',
                    'account': 'my_account',
                    'warehouse': 'my_wh',
                    'database': 'my_db',
                    'schema': 'my_schema',
                    'role': 'my_role',
                    'logfire.msg_template': 'snowflake execute {command}',
                    'logfire.msg': 'snowflake execute select 1',
                    'logfire.span_type': 'span',
                    'sfqid': 'fake-sfqid-1',
                    'rowcount': 3,
                    'logfire.json_schema': '{"type":"object","properties":{"command":{},"params":{"type":"null"},"account":{},"warehouse":{},"database":{},"schema":{},"role":{},"sfqid":{},"rowcount":{}}}',
                },
            }
        ]
    )


def test_instrument_snowflake_idempotent(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()
    logfire.instrument_snowflake()  # should not double-wrap

    import snowflake.connector

    conn = snowflake.connector.connect(account='my_account')
    cursor = conn.cursor()
    cursor.execute('select 1')

    # Exactly one `snowflake connect` span and one `snowflake execute` span — not two of each.
    names = [s['name'] for s in exporter.exported_spans_as_dict()]
    assert names.count('snowflake connect') == 1
    assert names.count('snowflake execute') == 1


class SnowflakeQueryError(Exception):
    pass


def test_instrument_execute_error(exporter: TestExporter) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account')
    cursor = conn.cursor()

    def broken_execute(self: SnowflakeCursor, command: str, params: Any = None, *a: Any, **k: Any):
        raise SnowflakeQueryError('syntax error')

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(SnowflakeCursor, 'execute', broken_execute)
        # Re-instrument so our wrapper picks up broken_execute as the new "original" to wrap.
        logfire.instrument_snowflake()
        with pytest.raises(SnowflakeQueryError):
            cursor.execute('select * from does_not_exist')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'snowflake execute',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_snowflake.py',
                    'code.function': 'test_instrument_execute_error',
                    'code.lineno': 123,
                    'command': 'select * from does_not_exist',
                    'params': 'null',
                    'account': 'my_account',
                    'warehouse': 'null',
                    'database': 'null',
                    'schema': 'null',
                    'role': 'null',
                    'logfire.msg_template': 'snowflake execute {command}',
                    'logfire.msg': 'snowflake execute select * from does_not_exist',
                    'logfire.json_schema': '{"type":"object","properties":{"command":{},"params":{"type":"null"},"account":{},"warehouse":{"type":"null"},"database":{"type":"null"},"schema":{"type":"null"},"role":{"type":"null"}}}',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.exception.fingerprint': '0000000000000000000000000000000000000000000000000000000000000000',
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': 2000000000,
                        'attributes': {
                            'exception.type': 'tests.otel_integrations.test_snowflake.SnowflakeQueryError',
                            'exception.message': 'syntax error',
                            'exception.stacktrace': 'tests.otel_integrations.test_snowflake.SnowflakeQueryError: syntax error',
                            'exception.escaped': 'True',
                        },
                    }
                ],
            }
        ]
    )


def test_internal_exception_error_does_not_break_query(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch) -> None:
    logfire.instrument_snowflake()

    conn = FakeConnection(account='my_account')
    cursor = conn.cursor()

    # Simulate a bug in our own attribute-reading code: `connection` raises instead of
    # returning the real connection.
    monkeypatch.setattr(
        SnowflakeCursor, 'connection', property(lambda self: (_ for _ in ()).throw(RuntimeError('boom')))
    )

    result = cursor.execute('select 1')  # must not raise, despite the broken `connection` property
    assert result is cursor
