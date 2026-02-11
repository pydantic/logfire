"""Tests for the PEP 249 DB API 2.0 interface (`logfire.db_api`)."""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

import logfire.db_api
from logfire.db_api import Connection, Cursor, ProgrammingError, connect

# ---------------------------------------------------------------------------
# Mock transport helpers
# ---------------------------------------------------------------------------

SAMPLE_COLUMNS = [
    {'name': 'kind', 'datatype': 'Utf8', 'nullable': False},
    {'name': 'message', 'datatype': 'Utf8', 'nullable': True},
    {'name': 'count', 'datatype': 'Int64', 'nullable': True},
]

SAMPLE_ROWS = [
    {'kind': 'log', 'message': 'hello', 'count': 1},
    {'kind': 'span', 'message': 'world', 'count': 2},
    {'kind': 'log', 'message': 'foo', 'count': 3},
]


def make_mock_transport(
    *,
    columns: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
    capture: dict[str, Any] | None = None,
) -> httpx.MockTransport:
    """Create a mock transport that returns the given columns/rows for /v1/query."""
    resp_columns = columns if columns is not None else SAMPLE_COLUMNS
    resp_rows = rows if rows is not None else SAMPLE_ROWS

    def handler(request: httpx.Request) -> httpx.Response:
        parsed = urlparse(str(request.url))
        if capture is not None:
            capture['path'] = parsed.path
            capture['params'] = parse_qs(parsed.query)
            capture['headers'] = dict(request.headers)
        if parsed.path == '/v1/query':
            body = {'columns': resp_columns, 'rows': resp_rows}
            return httpx.Response(200, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def make_connection(
    *,
    columns: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
    capture: dict[str, Any] | None = None,
    limit: int = logfire.db_api.DEFAULT_LIMIT,
    min_timestamp: datetime | timedelta | None = None,
    max_timestamp: datetime | None = None,
) -> Connection:
    """Create a Connection backed by a mock transport."""
    from logfire.experimental.query_client import LogfireQueryClient

    transport = make_mock_transport(columns=columns, rows=rows, capture=capture)
    client = LogfireQueryClient(
        read_token='fake-token',
        base_url='https://logfire-us.pydantic.dev',
        transport=transport,
    )
    return Connection(
        client,
        limit=limit,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
    )


# ---------------------------------------------------------------------------
# Tests: module-level attributes
# ---------------------------------------------------------------------------


def test_module_attributes():
    assert logfire.db_api.apilevel == '2.0'
    assert logfire.db_api.threadsafety == 1
    assert logfire.db_api.paramstyle == 'pyformat'


# ---------------------------------------------------------------------------
# Tests: connect()
# ---------------------------------------------------------------------------


def test_connect_creates_connection():
    transport = make_mock_transport()
    conn = connect(
        read_token='pylf_v1_us_fake',
        base_url='https://logfire-us.pydantic.dev',
        transport=transport,
    )
    assert isinstance(conn, Connection)
    assert not conn.closed
    conn.close()
    assert conn.closed


def test_connect_base_url_inferred():
    """connect() without base_url infers from token region."""
    transport = make_mock_transport()
    conn = connect(read_token='pylf_v1_us_fake', transport=transport)
    assert conn.client.base_url == 'https://logfire-us.pydantic.dev'
    conn.close()


# ---------------------------------------------------------------------------
# Tests: Connection
# ---------------------------------------------------------------------------


def test_connection_context_manager():
    conn = make_connection()
    with conn:
        cur = conn.cursor()
        assert isinstance(cur, Cursor)
    assert conn.closed


def test_connection_commit_rollback_noop():
    conn = make_connection()
    # Should not raise
    conn.commit()
    conn.rollback()
    conn.close()


def test_connection_cursor_after_close():
    conn = make_connection()
    conn.close()
    with pytest.raises(ProgrammingError, match='Connection is closed'):
        conn.cursor()


def test_multiple_cursors_share_client():
    conn = make_connection()
    cur1 = conn.cursor()
    cur2 = conn.cursor()
    # Both cursors should be backed by the same connection's client
    assert conn.client is not None
    # Verify both cursors work against the same connection
    cur1.execute('SELECT kind, message, count FROM records')
    cur2.execute('SELECT kind, message, count FROM records')
    assert cur1.fetchall() == cur2.fetchall()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: Cursor.execute()
# ---------------------------------------------------------------------------


def test_execute_basic():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute('SELECT kind, message, count FROM records LIMIT 3')

    assert capture['params']['sql'] == ['SELECT kind, message, count FROM records LIMIT 3']
    assert capture['params']['json_rows'] == ['true']
    assert cur.rowcount == 3
    assert cur.description is not None
    assert len(cur.description) == 3
    assert cur.description[0] == ('kind', 'Utf8', None, None, None, None, False)
    assert cur.description[1] == ('message', 'Utf8', None, None, None, None, True)
    assert cur.description[2] == ('count', 'Int64', None, None, None, None, True)
    conn.close()


def test_execute_sends_limit():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture, limit=500)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert capture['params']['limit'] == ['500']
    conn.close()


def test_execute_cursor_limit_override():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture, limit=500)
    cur = conn.cursor()
    cur.limit = 100
    cur.execute('SELECT 1')
    assert capture['params']['limit'] == ['100']
    conn.close()


def test_execute_on_closed_cursor():
    conn = make_connection()
    cur = conn.cursor()
    cur.close()
    with pytest.raises(ProgrammingError, match='Cursor is closed'):
        cur.execute('SELECT 1')
    conn.close()


def test_execute_on_closed_connection():
    conn = make_connection()
    cur = conn.cursor()
    conn.close()
    with pytest.raises(ProgrammingError, match='Connection is closed'):
        cur.execute('SELECT 1')


# ---------------------------------------------------------------------------
# Tests: fetch methods
# ---------------------------------------------------------------------------


def test_fetchone():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT kind, message, count FROM records')

    row1 = cur.fetchone()
    assert row1 == ('log', 'hello', 1)
    row2 = cur.fetchone()
    assert row2 == ('span', 'world', 2)
    row3 = cur.fetchone()
    assert row3 == ('log', 'foo', 3)
    row4 = cur.fetchone()
    assert row4 is None
    conn.close()


def test_fetchmany():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT kind, message, count FROM records')

    rows = cur.fetchmany(2)
    assert rows == [('log', 'hello', 1), ('span', 'world', 2)]
    rows = cur.fetchmany(2)
    assert rows == [('log', 'foo', 3)]
    rows = cur.fetchmany(2)
    assert rows == []
    conn.close()


def test_fetchmany_default_arraysize():
    conn = make_connection()
    cur = conn.cursor()
    cur.arraysize = 2
    cur.execute('SELECT kind, message, count FROM records')

    rows = cur.fetchmany()
    assert len(rows) == 2
    conn.close()


def test_fetchall():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT kind, message, count FROM records')

    rows = cur.fetchall()
    assert rows == [('log', 'hello', 1), ('span', 'world', 2), ('log', 'foo', 3)]
    # Second call returns empty
    assert cur.fetchall() == []
    conn.close()


def test_fetchone_on_closed_cursor():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.close()
    with pytest.raises(ProgrammingError, match='Cursor is closed'):
        cur.fetchone()
    conn.close()


def test_fetchmany_on_closed_cursor():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.close()
    with pytest.raises(ProgrammingError, match='Cursor is closed'):
        cur.fetchmany()
    conn.close()


def test_fetchall_on_closed_cursor():
    conn = make_connection()
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.close()
    with pytest.raises(ProgrammingError, match='Cursor is closed'):
        cur.fetchall()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: parameter substitution
# ---------------------------------------------------------------------------


def test_params_dict():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE kind = %(kind)s AND count > %(count)s',
        {'kind': 'log', 'count': 5},
    )
    sql = capture['params']['sql'][0]
    assert "kind = 'log'" in sql
    assert 'count > 5' in sql
    conn.close()


def test_params_string_escaping():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE message = %(msg)s',
        {'msg': "it's a test"},
    )
    sql = capture['params']['sql'][0]
    assert "message = 'it''s a test'" in sql
    conn.close()


def test_params_none():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE message = %(msg)s',
        {'msg': None},
    )
    sql = capture['params']['sql'][0]
    assert 'message = NULL' in sql
    conn.close()


def test_params_bool():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE is_exception = %(flag)s',
        {'flag': True},
    )
    sql = capture['params']['sql'][0]
    assert 'is_exception = TRUE' in sql
    conn.close()


def test_params_float():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE score > %(val)s',
        {'val': 3.14},
    )
    sql = capture['params']['sql'][0]
    assert 'score > 3.14' in sql
    conn.close()


def test_params_non_string_fallback():
    """Cover the fallback branch in _escape_value for types that aren't str/int/float/bool/None."""
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    ts = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
    cur.execute(
        'SELECT * FROM records WHERE start_timestamp > %(ts)s',
        {'ts': ts},
    )
    sql = capture['params']['sql'][0]
    assert "start_timestamp > '2024-01-15 12:30:00+00:00'" in sql
    conn.close()


def test_params_non_string_fallback_with_quotes():
    """Cover the quote-escaping in the fallback branch of _escape_value."""
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()

    class HasQuotes:
        def __str__(self) -> str:
            return "it's tricky"

    cur.execute(
        'SELECT * FROM records WHERE label = %(val)s',
        {'val': HasQuotes()},
    )
    sql = capture['params']['sql'][0]
    assert "label = 'it''s tricky'" in sql
    conn.close()


def test_params_sequence():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute(
        'SELECT * FROM records WHERE kind = %s AND count > %s',
        ['log', 5],
    )
    sql = capture['params']['sql'][0]
    assert "kind = 'log'" in sql
    assert 'count > 5' in sql
    conn.close()


def test_params_empty_dict():
    """Empty dict should still trigger substitution (converts %% to %)."""
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.execute("SELECT '100%%' AS pct", {})
    sql = capture['params']['sql'][0]
    assert "SELECT '100%' AS pct" == sql
    conn.close()


# ---------------------------------------------------------------------------
# Tests: timestamps
# ---------------------------------------------------------------------------


def test_connection_timestamps():
    capture: dict[str, Any] = {}
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    conn = make_connection(capture=capture, min_timestamp=ts, max_timestamp=ts)
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert capture['params']['min_timestamp'] == [ts.isoformat()]
    assert capture['params']['max_timestamp'] == [ts.isoformat()]
    conn.close()


def test_cursor_timestamp_override():
    capture: dict[str, Any] = {}
    conn_ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    cur_ts = datetime(2024, 6, 1, tzinfo=timezone.utc)
    conn = make_connection(capture=capture, min_timestamp=conn_ts)
    cur = conn.cursor()
    cur.min_timestamp = cur_ts
    cur.execute('SELECT 1')
    assert capture['params']['min_timestamp'] == [cur_ts.isoformat()]
    conn.close()


# ---------------------------------------------------------------------------
# Tests: truncation warning
# ---------------------------------------------------------------------------


def test_truncation_warning():
    # Create exactly `limit` rows so the warning triggers
    rows = [{'kind': 'log', 'message': f'msg{i}', 'count': i} for i in range(5)]
    conn = make_connection(rows=rows, limit=5)
    cur = conn.cursor()

    with pytest.warns(UserWarning, match='returned 5 rows which is the limit'):
        cur.execute('SELECT kind, message, count FROM records')
    conn.close()


def test_no_truncation_warning_when_below_limit():
    conn = make_connection(limit=100)  # 3 rows < 100
    cur = conn.cursor()

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        cur.execute('SELECT kind, message, count FROM records')

    assert len(w) == 0
    conn.close()


# ---------------------------------------------------------------------------
# Tests: cursor context manager
# ---------------------------------------------------------------------------


def test_cursor_context_manager():
    conn = make_connection()
    with conn.cursor() as cur:
        cur.execute('SELECT kind, message, count FROM records')
        rows = cur.fetchall()
        assert len(rows) == 3
    # Verify cursor is closed by trying to fetch
    with pytest.raises(ProgrammingError, match='Cursor is closed'):
        cur.fetchone()
    conn.close()


# ---------------------------------------------------------------------------
# Tests: executemany
# ---------------------------------------------------------------------------


def test_executemany():
    capture: dict[str, Any] = {}
    conn = make_connection(capture=capture)
    cur = conn.cursor()
    cur.executemany(
        'SELECT * FROM records WHERE kind = %(kind)s',
        [{'kind': 'log'}, {'kind': 'span'}],
    )
    # Last execution's SQL should be the span one
    sql = capture['params']['sql'][0]
    assert "kind = 'span'" in sql
    # rowcount reflects the last execution
    assert cur.rowcount == 3
    conn.close()


# ---------------------------------------------------------------------------
# Tests: empty result set
# ---------------------------------------------------------------------------


def test_empty_result_set():
    conn = make_connection(rows=[])
    cur = conn.cursor()
    cur.execute('SELECT kind FROM records WHERE 1=0')
    assert cur.rowcount == 0
    assert cur.fetchone() is None
    assert cur.fetchall() == []
    assert cur.description is not None
    conn.close()


# ---------------------------------------------------------------------------
# Tests: exception hierarchy
# ---------------------------------------------------------------------------


def test_exception_hierarchy():
    assert issubclass(logfire.db_api.InterfaceError, logfire.db_api.Error)
    assert issubclass(logfire.db_api.DatabaseError, logfire.db_api.Error)
    assert issubclass(logfire.db_api.OperationalError, logfire.db_api.DatabaseError)
    assert issubclass(logfire.db_api.ProgrammingError, logfire.db_api.DatabaseError)
    assert issubclass(logfire.db_api.NotSupportedError, logfire.db_api.DatabaseError)


# ---------------------------------------------------------------------------
# Tests: setinputsizes / setoutputsize no-ops
# ---------------------------------------------------------------------------


def test_setinputsizes_noop():
    conn = make_connection()
    cur = conn.cursor()
    cur.setinputsizes([])  # should not raise
    conn.close()


def test_setoutputsize_noop():
    conn = make_connection()
    cur = conn.cursor()
    cur.setoutputsize(1000)  # should not raise
    cur.setoutputsize(1000, 0)  # should not raise
    conn.close()


# ---------------------------------------------------------------------------
# Tests: custom limit on connect
# ---------------------------------------------------------------------------


def test_connect_custom_limit():
    capture: dict[str, Any] = {}
    transport = make_mock_transport(capture=capture)
    conn = connect(
        read_token='pylf_v1_us_fake',
        base_url='https://logfire-us.pydantic.dev',
        limit=200,
        transport=transport,
    )
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert capture['params']['limit'] == ['200']
    conn.close()


# ---------------------------------------------------------------------------
# Tests: default min_timestamp
# ---------------------------------------------------------------------------


def test_connect_default_min_timestamp():
    """connect() without min_timestamp defaults to ~1 day ago."""
    capture: dict[str, Any] = {}
    transport = make_mock_transport(capture=capture)
    conn = connect(
        read_token='pylf_v1_us_fake',
        base_url='https://logfire-us.pydantic.dev',
        transport=transport,
    )
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert 'min_timestamp' in capture['params']
    # The default should be approximately 1 day ago
    assert conn.min_timestamp is not None
    age = datetime.now(timezone.utc) - conn.min_timestamp
    assert timedelta(hours=23) < age < timedelta(hours=25)
    conn.close()


def test_connect_min_timestamp_none_disables_filter():
    """Passing min_timestamp=None disables the timestamp filter."""
    capture: dict[str, Any] = {}
    transport = make_mock_transport(capture=capture)
    conn = connect(
        read_token='pylf_v1_us_fake',
        base_url='https://logfire-us.pydantic.dev',
        min_timestamp=None,
        transport=transport,
    )
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert 'min_timestamp' not in capture['params']
    conn.close()


def test_connect_min_timestamp_timedelta():
    """Passing a timedelta computes min_timestamp relative to now."""
    capture: dict[str, Any] = {}
    transport = make_mock_transport(capture=capture)
    conn = connect(
        read_token='pylf_v1_us_fake',
        base_url='https://logfire-us.pydantic.dev',
        min_timestamp=timedelta(days=7),
        transport=transport,
    )
    cur = conn.cursor()
    cur.execute('SELECT 1')
    assert 'min_timestamp' in capture['params']
    assert conn.min_timestamp is not None
    age = datetime.now(timezone.utc) - conn.min_timestamp
    assert timedelta(days=6) < age < timedelta(days=8)
    conn.close()


# ---------------------------------------------------------------------------
# Tests: string/bytes parameter rejection
# ---------------------------------------------------------------------------


def test_params_string_rejected():
    """Passing a string as parameters should raise ProgrammingError."""
    conn = make_connection()
    cur = conn.cursor()
    with pytest.raises(ProgrammingError, match='parameters must be a sequence'):
        cur.execute('SELECT * FROM records WHERE kind = %s', 'log')
    conn.close()


def test_params_bytes_rejected():
    """Passing bytes as parameters should raise ProgrammingError."""
    conn = make_connection()
    cur = conn.cursor()
    with pytest.raises(ProgrammingError, match='parameters must be a sequence'):
        cur.execute('SELECT * FROM records WHERE kind = %s', b'log')
    conn.close()
