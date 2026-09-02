from __future__ import annotations

from typing import Any

import pytest
from inline_snapshot import snapshot
from snowflake.connector import connection as sf_connection

import logfire
from logfire._internal.exporters.test import TestExporter


class FakeConnection:
    def __init__(self, **kwargs: Any) -> None:
        self.account = kwargs.get('account')
        self.warehouse = kwargs.get('warehouse')
        self.database = kwargs.get('database')
        self.schema = kwargs.get('schema')
        self.role = kwargs.get('role')


@pytest.fixture(autouse=True)
def fake_snowflake_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_connect(**kwargs: Any) -> FakeConnection:
        return FakeConnection(**kwargs)

    monkeypatch.setattr('snowflake.connector.connect', fake_connect)


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
