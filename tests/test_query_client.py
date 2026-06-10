from __future__ import annotations

import inspect
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from inline_snapshot import snapshot

from logfire.query_client import AsyncLogfireQueryClient, LogfireQueryClient

# This file is intended to be updated by the Logfire developers, with the development platform running locally.
# To update, set the `CLIENT_BASE_URL` and `CLIENT_READ_TOKEN` values to match the local development environment,
# and run the tests with `--record-mode=rewrite --inline-snapshot=fix` to update the cassettes and snapshots.
#
# The snapshots expect 37 non-exception logs and 1 exception. The two rows surfaced by the
# `ORDER BY is_exception, message LIMIT 2` query are `about to raise an error` (no tags) and
# `aha 0` (tags `['tag1', 'tag2']`). To populate the local instance with matching data:
#
# ```python
# import logfire
#
# logfire.configure()
#
# logfire.info('about to raise an error')
#
# try:
#     raise ValueError('oops')
# except Exception:
#     logfire.exception('oh no')
#
# for i in range(36):
#     logfire.with_tags('tag1', 'tag2').info('aha {n}', n=i)
# ```
CLIENT_BASE_URL = 'http://localhost:3000'
CLIENT_READ_TOKEN = 'pylf_v1_local_ZQHXp1vFjkR0dWxyQ8jCB4DPDlpd4752XWjpcNtdsPB6'
# Disable compression so cassettes record human-readable response bodies:
CLIENT_KWARGS: dict[str, Any] = {'headers': {'accept-encoding': 'identity'}}
pytestmark = pytest.mark.vcr()


@pytest.mark.parametrize('client_class', [AsyncLogfireQueryClient, LogfireQueryClient])
@pytest.mark.parametrize(
    ['token', 'expected'],
    [
        ('pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-us.pydantic.dev'),
        ('pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-eu.pydantic.dev'),
        ('0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-us.pydantic.dev'),
    ],
)
def test_infers_base_url_from_token(
    client_class: type[AsyncLogfireQueryClient | LogfireQueryClient], token: str, expected: str
):
    client = client_class(read_token=token)
    assert client.base_url == expected


def test_info_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        info = client.info()
        assert info == snapshot(
            {
                'organization_name': 'viicos',
                'project_name': 'logfire-sdk-cassettes',
            }
        )


@pytest.mark.anyio
async def test_info_async():
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        info = await client.info()
        assert info == snapshot(
            {
                'organization_name': 'viicos',
                'project_name': 'logfire-sdk-cassettes',
            }
        )


def test_query_json_read_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning) as warnings_record:
            result = client.query_json(sql)  # type: ignore[reportDeprecated]

        assert any('query_json() is deprecated' in str(w.message) for w in warnings_record)
        assert result == snapshot(
            {
                'columns': [
                    {
                        'name': 'kind',
                        'datatype': 'Utf8',
                        'nullable': False,
                        'values': ['log', 'log'],
                    },
                    {
                        'name': 'message',
                        'datatype': 'Utf8',
                        'nullable': False,
                        'values': ['about to raise an error', 'aha 0'],
                    },
                    {
                        'name': 'is_exception',
                        'datatype': 'Boolean',
                        'nullable': True,
                        'values': [False, False],
                    },
                    {
                        'name': 'tags',
                        'datatype': {'List': {'name': 'item', 'nullable': True, 'datatype': 'Utf8'}},
                        'nullable': True,
                        'values': [
                            [],
                            ['tag1', 'tag2'],
                        ],
                    },
                ]
            }
        )


def test_query_json_rows_read_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            rows_result = client.query_json_rows(sql)  # type: ignore[reportDeprecated]

        assert rows_result == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'message', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'is_exception', 'nullable': True, 'datatype': 'Boolean'},
                    {
                        'name': 'tags',
                        'nullable': True,
                        'datatype': {'List': {'name': 'item', 'nullable': True, 'datatype': 'Utf8'}},
                    },
                ],
                'rows': [
                    {
                        'kind': 'log',
                        'message': 'about to raise an error',
                        'is_exception': False,
                        'tags': [],
                    },
                    {
                        'kind': 'log',
                        'message': 'aha 0',
                        'is_exception': False,
                        'tags': ['tag1', 'tag2'],
                    },
                ],
            }
        )


def test_query_csv_read_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            csv_result = client.query_csv(sql, min_timestamp=None)  # type: ignore[reportDeprecated]
        assert csv_result == snapshot("""\
kind,message,is_exception,tags
log,about to raise an error,false,[]
log,aha 0,false,"[""tag1"",""tag2""]"
""")


def test_query_arrow_read_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            arrow_result = client.query_arrow(sql, min_timestamp=None)  # type: ignore[reportDeprecated]
        assert arrow_result.to_pylist() == snapshot(  # type: ignore
            [
                {
                    'kind': 'log',
                    'message': 'about to raise an error',
                    'is_exception': False,
                    'tags': [],
                },
                {
                    'kind': 'log',
                    'message': 'aha 0',
                    'is_exception': False,
                    'tags': ['tag1', 'tag2'],
                },
            ]
        )


@pytest.mark.anyio
async def test_query_json_read_async():
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning) as warnings_record:
            result = await client.query_json(sql)  # type: ignore[reportDeprecated]

        assert any('query_json() is deprecated' in str(w.message) for w in warnings_record)
        assert result == snapshot(
            {
                'columns': [
                    {
                        'name': 'kind',
                        'datatype': 'Utf8',
                        'nullable': False,
                        'values': ['log', 'log'],
                    },
                    {
                        'name': 'message',
                        'datatype': 'Utf8',
                        'nullable': False,
                        'values': ['about to raise an error', 'aha 0'],
                    },
                    {
                        'name': 'is_exception',
                        'datatype': 'Boolean',
                        'nullable': True,
                        'values': [False, False],
                    },
                    {
                        'name': 'tags',
                        'datatype': {'List': {'name': 'item', 'nullable': True, 'datatype': 'Utf8'}},
                        'nullable': True,
                        'values': [
                            [],
                            ['tag1', 'tag2'],
                        ],
                    },
                ]
            }
        )


@pytest.mark.anyio
async def test_query_json_rows_read_async():
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            rows_result = await client.query_json_rows(sql)  # type: ignore[reportDeprecated]
        assert rows_result == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'message', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'is_exception', 'nullable': True, 'datatype': 'Boolean'},
                    {
                        'name': 'tags',
                        'nullable': True,
                        'datatype': {'List': {'name': 'item', 'nullable': True, 'datatype': 'Utf8'}},
                    },
                ],
                'rows': [
                    {
                        'kind': 'log',
                        'message': 'about to raise an error',
                        'is_exception': False,
                        'tags': [],
                    },
                    {
                        'kind': 'log',
                        'message': 'aha 0',
                        'is_exception': False,
                        'tags': ['tag1', 'tag2'],
                    },
                ],
            }
        )


@pytest.mark.anyio
async def test_query_csv_read_async():
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            csv_result = await client.query_csv(sql, min_timestamp=None)  # type: ignore[reportDeprecated]
        assert csv_result == snapshot("""\
kind,message,is_exception,tags
log,about to raise an error,false,[]
log,aha 0,false,"[""tag1"",""tag2""]"
""")


@pytest.mark.anyio
async def test_query_arrow_read_async():
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        with pytest.warns(DeprecationWarning, match='without a min_timestamp'):
            arrow_result = await client.query_arrow(sql, min_timestamp=None)  # type: ignore[reportDeprecated]
        assert arrow_result.to_pylist() == snapshot(  # type: ignore
            [
                {
                    'kind': 'log',
                    'message': 'about to raise an error',
                    'is_exception': False,
                    'tags': [],
                },
                {
                    'kind': 'log',
                    'message': 'aha 0',
                    'is_exception': False,
                    'tags': ['tag1', 'tag2'],
                },
            ]
        )


def test_query_params_sync():
    # `_MIN_DATETIME` matches the SDK's default min_timestamp, so the request body
    # (and the recorded cassette) is identical to omitting `min_timestamp`.
    min_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        sql = """
        SELECT is_exception, count(*)
        FROM records
        GROUP BY is_exception
        ORDER BY is_exception
        """
        assert client.query_csv(sql, min_timestamp=min_ts) == snapshot("""\
is_exception,count(*)
false,37
true,1
""")
        assert client.query_csv(sql, min_timestamp=datetime(2030, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert client.query_csv(sql, min_timestamp=min_ts, max_timestamp=min_ts) == snapshot("""\
is_exception,count(*)
""")
        assert client.query_csv(sql, min_timestamp=min_ts, limit=1) == snapshot("""\
is_exception,count(*)
false,37
""")


@pytest.mark.anyio
async def test_query_params_async():
    # `_MIN_DATETIME` matches the SDK's default min_timestamp, so the request body
    # (and the recorded cassette) is identical to omitting `min_timestamp`.
    min_ts = datetime(2020, 1, 1, tzinfo=timezone.utc)
    async with AsyncLogfireQueryClient(
        read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS
    ) as client:
        sql = """
        SELECT is_exception, count(*)
        FROM records
        GROUP BY is_exception
        ORDER BY is_exception
        """
        assert await client.query_csv(sql, min_timestamp=min_ts) == snapshot("""\
is_exception,count(*)
false,37
true,1
""")
        assert await client.query_csv(sql, min_timestamp=datetime(2030, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert await client.query_csv(sql, min_timestamp=min_ts, max_timestamp=min_ts) == snapshot("""\
is_exception,count(*)
""")
        assert await client.query_csv(sql, min_timestamp=min_ts, limit=1) == snapshot("""\
is_exception,count(*)
false,37
""")


def test_query_body_params_sync():
    """Exercise every optional body parameter (naive timestamps, timezone, environment) on `/v2/query`."""
    sql = 'SELECT count(*) AS n FROM records'
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL, **CLIENT_KWARGS) as client:
        result = client.query_json_rows(
            sql,
            min_timestamp=datetime(2020, 1, 1),
            max_timestamp=datetime(2099, 1, 1),
            timezone='UTC',
            environment='production',
        )
        assert result == snapshot(
            {'columns': [{'name': 'n', 'datatype': 'Int64', 'nullable': False}], 'rows': [{'n': 0}]}
        )


def test_query_methods_share_docstring():
    # All query methods (on both clients) document the same arguments, so the `Args:` section of
    # their docstrings should be identical. Use the first method as the reference.
    query_methods = [
        getattr(client_class, name)
        for client_class in (LogfireQueryClient, AsyncLogfireQueryClient)
        for name in ('query_arrow', 'query_csv', 'query_json_rows')
    ]
    reference, *others = query_methods
    reference_doc = inspect.cleandoc(reference.__doc__)
    doc = reference_doc[reference_doc.index('Args:') :]
    for method in others:
        assert doc in inspect.cleandoc(method.__doc__)


def test_query_json_rows_methods_share_returns_docstring():
    # The `query_json_rows()` methods on both clients document the same return value, so the
    # `Returns:` section of their docstrings should be identical. Use the sync method as the reference.
    reference_doc = inspect.cleandoc(cast(str, LogfireQueryClient.query_json_rows.__doc__))
    returns = reference_doc[reference_doc.index('Returns:') :]
    assert returns in inspect.cleandoc(cast(str, AsyncLogfireQueryClient.query_json_rows.__doc__))
