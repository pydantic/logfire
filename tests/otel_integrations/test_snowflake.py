from __future__ import annotations

from typing import Any

import pytest
from inline_snapshot import snapshot
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
