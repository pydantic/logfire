from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest
from inline_snapshot import snapshot

from logfire.experimental.query_client import AsyncLogfireQueryClient, LogfireQueryClient

# This file is intended to be updated by the Logfire developers, with the development platform running locally.
# To update, set the `CLIENT_BASE_URL` and `CLIENT_READ_TOKEN` values to match the local development environment,
# and run the tests with `--record-mode=rewrite --inline-snapshot=fix` to update the cassettes and snapshots.
CLIENT_BASE_URL = 'http://localhost:8000/'
CLIENT_READ_TOKEN = '06KJCLLch8TCYx1FX4N1VGbr2mHrR760Z87zWjpb0TPm'
pytestmark = [
    pytest.mark.vcr(),
    pytest.mark.skipif(
        sys.version_info < (3, 10),
        reason='vcr is not compatible with latest urllib3 on python<3.10, '
        'see https://github.com/kevin1024/vcrpy/issues/688.',
    ),
]


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


def test_read_sync():
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        assert client.query_json(sql) == snapshot(
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
                        'nullable': True,
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
        assert client.query_json_rows(sql) == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'message', 'nullable': True, 'datatype': 'Utf8'},
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
        assert client.query_csv(sql) == snapshot("""\
kind,message,is_exception,tags
log,about to raise an error,false,[]
log,aha 0,false,"[""tag1"",""tag2""]"
""")
        assert client.query_arrow(sql).to_pylist() == snapshot(  # type: ignore
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
async def test_read_async():
    async with AsyncLogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL) as client:
        sql = """
        SELECT kind, message, is_exception, tags
        FROM records
        ORDER BY is_exception, message
        LIMIT 2
        """
        assert await client.query_json(sql) == snapshot(
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
                        'nullable': True,
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
        assert await client.query_json_rows(sql) == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'nullable': False, 'datatype': 'Utf8'},
                    {'name': 'message', 'nullable': True, 'datatype': 'Utf8'},
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
        assert await client.query_csv(sql) == snapshot("""\
kind,message,is_exception,tags
log,about to raise an error,false,[]
log,aha 0,false,"[""tag1"",""tag2""]"
""")
        assert (await client.query_arrow(sql)).to_pylist() == snapshot(  # type: ignore
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
    with LogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL) as client:
        sql = """
        SELECT is_exception, count(*)
        FROM records
        GROUP BY is_exception
        ORDER BY is_exception
        """
        assert client.query_csv(sql) == snapshot("""\
is_exception,count(*)
false,37
true,1
""")
        assert client.query_csv(sql, min_timestamp=datetime(2030, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert client.query_csv(sql, max_timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert client.query_csv(sql, limit=1) == snapshot("""\
is_exception,count(*)
false,37
""")


@pytest.mark.anyio
async def test_query_params_async():
    async with AsyncLogfireQueryClient(read_token=CLIENT_READ_TOKEN, base_url=CLIENT_BASE_URL) as client:
        sql = """
        SELECT is_exception, count(*)
        FROM records
        GROUP BY is_exception
        ORDER BY is_exception
        """
        assert await client.query_csv(sql) == snapshot("""\
is_exception,count(*)
false,37
true,1
""")
        assert await client.query_csv(sql, min_timestamp=datetime(2030, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert await client.query_csv(sql, max_timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc)) == snapshot("""\
is_exception,count(*)
""")
        assert await client.query_csv(sql, limit=1) == snapshot("""\
is_exception,count(*)
false,37
""")
