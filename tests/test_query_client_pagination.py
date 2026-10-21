from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from logfire.query_client import (
    AsyncLogfireQueryClient,
    LogfireQueryClient,
    QueryRateLimitedError,
    UnexpectedResponseError,
)

MIN_TIMESTAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)
MAX_TIMESTAMP = MIN_TIMESTAMP + timedelta(days=1)
pytestmark = pytest.mark.anyio


@pytest.fixture(params=[False, True], ids=['sync', 'async'])
def use_async(request: pytest.FixtureRequest) -> bool:
    return request.param


@asynccontextmanager
async def records_iterator(
    use_async: bool, handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any
) -> AsyncGenerator[AsyncIterator[dict[str, Any]], None]:
    options: dict[str, Any] = {'min_timestamp': MIN_TIMESTAMP, 'max_timestamp': MAX_TIMESTAMP, **kwargs}
    transport = httpx.MockTransport(handler)
    if use_async:
        async with AsyncLogfireQueryClient(read_token='test', transport=transport) as client:
            yield client.iter_records(**options)
    else:
        with LogfireQueryClient(read_token='test', transport=transport) as client:
            iterator = client.iter_records(**options)

            async def iterate() -> AsyncIterator[dict[str, Any]]:
                for row in iterator:
                    yield row

            yield iterate()


@pytest.fixture
def database() -> Iterator[sqlite3.Connection]:
    with sqlite3.connect(':memory:') as connection:
        connection.row_factory = sqlite3.Row

        # SQLite executes the pagination SQL; timestamps use a common UTC representation.
        # DataFusion's to_timestamp converts the cursor literal to the column's timestamp type.
        def to_timestamp(value: str) -> str:
            return value

        connection.create_function('to_timestamp', 1, to_timestamp)
        connection.execute(
            'CREATE TABLE records (start_timestamp TEXT, trace_id TEXT, span_id TEXT, kind TEXT, message TEXT)'
        )
        # Insert in reverse order so iteration must sort, including ties at each cursor field.
        connection.executemany(
            'INSERT INTO records VALUES (?, ?, ?, ?, ?)',
            [
                (
                    f'2026-01-01T00:00:00.{i // 8:09d}Z',
                    f'{i // 4:032x}',
                    f'{i // 2:016x}',
                    'span' if i % 2 else 'log',
                    f'row {i}',
                )
                for i in reversed(range(25))
            ],
        )
        yield connection
    connection.close()


def sql_transport(
    database: sqlite3.Connection, requests: list[dict[str, Any]]
) -> Callable[[httpx.Request], httpx.Response]:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == 'POST'
        assert request.url.path == '/v2/query'
        body = json.loads(request.content)
        requests.append(body)
        # Fail instead of hanging if a broken cursor repeatedly selects an earlier page.
        assert len(requests) < 100
        rows = database.execute(body['sql'] + ' LIMIT ?', (body['limit'],)).fetchall()
        return response([dict(row) for row in rows])

    return handle


def response(rows: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(200, json={'schema': {'fields': []}, 'data': rows})


@pytest.mark.parametrize('page_size', [1, 2, 7, 25, 26, 10_000])
async def test_records_across_page_boundaries(use_async: bool, database: sqlite3.Connection, page_size: int):
    requests: list[dict[str, Any]] = []
    async with records_iterator(use_async, sql_transport(database, requests), page_size=page_size) as iterator:
        rows = [row async for row in iterator]
    assert [row['message'] for row in rows] == [f'row {i}' for i in range(25)]
    assert len(requests) == 25 // page_size + 1
    for request in requests:
        assert request['min_timestamp'] == MIN_TIMESTAMP.isoformat()
        assert request['max_timestamp'] == MAX_TIMESTAMP.isoformat()
        assert request['limit'] == page_size
    if page_size < 25:
        # The timestamp is passed back verbatim, including nanoseconds.
        assert f"to_timestamp('{rows[page_size - 1]['start_timestamp']}')" in requests[1]['sql']


async def test_export_more_than_api_limit(use_async: bool, database: sqlite3.Connection):
    database.execute('DELETE FROM records')
    database.executemany(
        'INSERT INTO records VALUES (?, ?, ?, ?, ?)',
        [('2026-01-01T00:00:00.000000000Z', f'{i:032x}', f'{i:016x}', 'log', f'row {i}') for i in range(10_005)],
    )
    requests: list[dict[str, Any]] = []
    async with records_iterator(use_async, sql_transport(database, requests), page_size=10_000) as iterator:
        rows = [row async for row in iterator]
    assert [row['message'] for row in rows] == [f'row {i}' for i in range(10_005)]
    assert len(requests) == 2


async def test_filter_and_query_options(use_async: bool, database: sqlite3.Connection):
    requests: list[dict[str, Any]] = []
    async with records_iterator(
        use_async,
        sql_transport(database, requests),
        where="message = 'row 1' OR message = 'row 24' -- trailing comment",
        page_size=1,
        timezone='Europe/London',
        environment=['production', 'staging'],
    ) as iterator:
        assert [row['message'] async for row in iterator] == ['row 1', 'row 24']
    assert len(requests) == 3
    assert all(request['timezone'] == 'Europe/London' for request in requests)
    assert all(request['deployment_environment'] == ['production', 'staging'] for request in requests)


async def test_cursor_escapes_sql_literals(use_async: bool, database: sqlite3.Connection):
    database.execute('DELETE FROM records')
    database.executemany(
        'INSERT INTO records VALUES (?, ?, ?, ?, ?)',
        [('2026-01-01T00:00:00.000000000Z', "trace'quote", 'span', kind, kind) for kind in ['a', "b'quote", 'c']],
    )
    requests: list[dict[str, Any]] = []
    async with records_iterator(use_async, sql_transport(database, requests), page_size=1) as iterator:
        assert [row['message'] async for row in iterator] == ['a', "b'quote", 'c']


async def test_empty_result(use_async: bool, database: sqlite3.Connection):
    requests: list[dict[str, Any]] = []
    async with records_iterator(use_async, sql_transport(database, requests), where='false') as iterator:
        assert [row async for row in iterator] == []
    assert len(requests) == 1


async def test_lazy_fetch_and_caller_mutation(use_async: bool, database: sqlite3.Connection):
    requests: list[dict[str, Any]] = []
    async with records_iterator(use_async, sql_transport(database, requests), page_size=2) as iterator:
        assert not requests
        assert (await anext(iterator))['message'] == 'row 0'
        last_row = await anext(iterator)
        last_row['trace_id'] = 'changed by caller'
        assert len(requests) == 1
        assert (await anext(iterator))['message'] == 'row 2'
        assert len(requests) == 2
    assert len(requests) == 2


@pytest.mark.parametrize('page_size', [0, -1, 10_001])
async def test_invalid_page_size(use_async: bool, page_size: int):
    async with records_iterator(
        use_async, lambda _: pytest.fail('Unexpected request'), page_size=page_size
    ) as iterator:
        with pytest.raises(ValueError, match='page_size must be between'):
            await anext(iterator)


async def test_reversed_window(use_async: bool):
    async with records_iterator(
        use_async, lambda _: pytest.fail('Unexpected request'), min_timestamp=MAX_TIMESTAMP, max_timestamp=MIN_TIMESTAMP
    ) as iterator:
        with pytest.raises(ValueError, match='min_timestamp must not be after'):
            await anext(iterator)


@pytest.mark.parametrize('naive', [True, False])
async def test_window_timezones(use_async: bool, naive: bool):
    requests: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return response([])

    minimum = MIN_TIMESTAMP.replace(tzinfo=None) if naive else MIN_TIMESTAMP.astimezone(timezone(timedelta(hours=5)))
    maximum = MAX_TIMESTAMP.replace(tzinfo=None) if naive else MAX_TIMESTAMP
    async with records_iterator(use_async, handle, min_timestamp=minimum, max_timestamp=maximum) as iterator:
        assert [row async for row in iterator] == []
    assert datetime.fromisoformat(requests[0]['min_timestamp']) == MIN_TIMESTAMP


@pytest.mark.parametrize('bad_value', [None, '', 123])
async def test_invalid_cursor(use_async: bool, bad_value: Any):
    row = {'start_timestamp': '2026-01-01T00:00:00Z', 'trace_id': bad_value, 'span_id': 'a', 'kind': 'log'}
    async with records_iterator(use_async, lambda _: response([row])) as iterator:
        with pytest.raises(UnexpectedResponseError, match='Records pagination requires non-empty'):
            await anext(iterator)


async def test_non_advancing_cursor(use_async: bool):
    row = {'start_timestamp': '2026-01-01T00:00:00Z', 'trace_id': 'a', 'span_id': 'b', 'kind': 'log'}
    async with records_iterator(use_async, lambda _: response([row]), page_size=1) as iterator:
        assert await anext(iterator) == row
        with pytest.raises(UnexpectedResponseError, match='cursor did not advance'):
            await anext(iterator)


@pytest.mark.parametrize('network_error', [False, True])
async def test_later_page_error(use_async: bool, network_error: bool):
    calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return response(
                [{'start_timestamp': '2026-01-01T00:00:00Z', 'trace_id': 'a', 'span_id': 'b', 'kind': 'log'}]
            )
        if network_error:
            raise httpx.ReadTimeout('timed out', request=request)
        return httpx.Response(429, text='Slow down', headers={'retry-after': '30'})

    async with records_iterator(use_async, handle, page_size=1) as iterator:
        assert (await anext(iterator))['span_id'] == 'b'
        if network_error:
            with pytest.raises(httpx.ReadTimeout):
                await anext(iterator)
        else:
            with pytest.raises(QueryRateLimitedError) as exc:
                await anext(iterator)
            assert exc.value.retry_after == 30
    assert calls == 2
