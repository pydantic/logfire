import sys
from datetime import datetime, timezone

import pytest
from inline_snapshot import snapshot

from logfire.experimental.query_client import AsyncLogfireQueryClient, LogfireQueryClient

# This file is intended to be updated by the Logfire developers, with the development platform running locally.
# To update, set the `CLIENT_BASE_URL` and `CLIENT_READ_TOKEN` values to match the local development environment,
# and run the tests with `--record-mode=rewrite --inline-snapshot=fix` to update the cassettes and snapshots.
CLIENT_BASE_URL = 'http://localhost:8000/'
CLIENT_READ_TOKEN = '6qdcmMdvHhyqy6sjhmSW08q1J5VCMRfLl23yNbdz3YGn'
pytestmark = [
    pytest.mark.vcr(),
    pytest.mark.skipif(
        sys.version_info < (3, 10),
        reason='vcr is not compatible with latest urllib3 on python<3.10, '
        'see https://github.com/kevin1024/vcrpy/issues/688.',
    ),
]


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
                        'datatype': 'String',
                        'bit_settings': '',
                        'values': ['log', 'log'],
                    },
                    {
                        'name': 'message',
                        'datatype': 'String',
                        'bit_settings': '',
                        'values': ['about to raise an error', 'aha 0'],
                    },
                    {
                        'name': 'is_exception',
                        'datatype': 'Boolean',
                        'bit_settings': '',
                        'values': [False, False],
                    },
                    {
                        'name': 'tags',
                        'datatype': {'List': 'String'},
                        'bit_settings': '',
                        'values': [
                            {'name': '', 'datatype': 'String', 'bit_settings': '', 'values': []},
                            {
                                'name': '',
                                'datatype': 'String',
                                'bit_settings': '',
                                'values': ['tag1', 'tag2'],
                            },
                        ],
                    },
                ]
            }
        )
        assert client.query_json_rows(sql) == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'datatype': 'String', 'bit_settings': ''},
                    {'name': 'message', 'datatype': 'String', 'bit_settings': ''},
                    {'name': 'is_exception', 'datatype': 'Boolean', 'bit_settings': ''},
                    {'name': 'tags', 'datatype': {'List': 'String'}, 'bit_settings': ''},
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
                        'datatype': 'String',
                        'bit_settings': '',
                        'values': ['log', 'log'],
                    },
                    {
                        'name': 'message',
                        'datatype': 'String',
                        'bit_settings': '',
                        'values': ['about to raise an error', 'aha 0'],
                    },
                    {
                        'name': 'is_exception',
                        'datatype': 'Boolean',
                        'bit_settings': '',
                        'values': [False, False],
                    },
                    {
                        'name': 'tags',
                        'datatype': {'List': 'String'},
                        'bit_settings': '',
                        'values': [
                            {'name': '', 'datatype': 'String', 'bit_settings': '', 'values': []},
                            {
                                'name': '',
                                'datatype': 'String',
                                'bit_settings': '',
                                'values': ['tag1', 'tag2'],
                            },
                        ],
                    },
                ]
            }
        )
        assert await client.query_json_rows(sql) == snapshot(
            {
                'columns': [
                    {'name': 'kind', 'datatype': 'String', 'bit_settings': ''},
                    {'name': 'message', 'datatype': 'String', 'bit_settings': ''},
                    {'name': 'is_exception', 'datatype': 'Boolean', 'bit_settings': ''},
                    {'name': 'tags', 'datatype': {'List': 'String'}, 'bit_settings': ''},
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
