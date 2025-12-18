import inspect
import sys
from typing import TYPE_CHECKING

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter

try:
    from surrealdb import AsyncSurreal, Surreal

    from logfire._internal.integrations.surrealdb import get_all_surrealdb_classes

except Exception:
    assert not TYPE_CHECKING

pytestmark = [
    pytest.mark.skipif(sys.version_info < (3, 10), reason='surrealdb requires Python 3.10 or higher'),
]


def test_get_all_surrealdb_classes():
    # These can change, but importantly they should match possible return types of surrealdb.[Async]Surreal()
    assert sorted(cls.__name__ for cls in get_all_surrealdb_classes()) == snapshot(
        [
            'AsyncEmbeddedSurrealConnection',
            'AsyncHttpSurrealConnection',
            'AsyncWsSurrealConnection',
            'BlockingEmbeddedSurrealConnection',
            'BlockingHttpSurrealConnection',
            'BlockingWsSurrealConnection',
        ]
    )


def test_instrument_surrealdb(exporter: TestExporter) -> None:
    logfire.instrument_surrealdb()
    logfire.instrument_surrealdb()  # should be idempotent

    for cls in get_all_surrealdb_classes():
        templates: list[str] = []
        for _name, method in inspect.getmembers(cls):
            template = getattr(method, '_logfire_template', None)
            if template is not None:
                templates.append(template)
        # This list can change as surrealdb adds/removes methods.
        # It's a simple check that automatically instrumenting all methods of a class
        # and selecting simple parameters from the signature works as expected.
        assert sorted(templates) == snapshot(
            [
                'surrealdb authenticate',
                'surrealdb close',
                'surrealdb create {record}',
                'surrealdb delete {record}',
                'surrealdb info',
                'surrealdb insert {table}',
                'surrealdb insert_relation {table}',
                'surrealdb invalidate',
                'surrealdb kill {query_uuid}',
                'surrealdb let {key}',
                'surrealdb live table = {table}, diff = {diff}',
                'surrealdb merge {record}',
                'surrealdb patch {record}',
                'surrealdb query {query}',
                'surrealdb select {record}',
                'surrealdb signin',
                'surrealdb signup',
                'surrealdb subscribe_live {query_uuid}',
                'surrealdb unset {key}',
                'surrealdb update {record}',
                'surrealdb upsert {record}',
                'surrealdb use namespace = {namespace}, database = {database}',
            ]
        )

    with Surreal('mem://') as db:
        db.use('namepace_test', 'database_test')
        db.create(
            'person',
            {
                'user': 'me',
                'password': 'safe',
                'marketing': True,
                'tags': ['python', 'documentation'],
            },
        )
        db.select('person')
        db.update('person', {'user': 'you', 'password': 'very_safe', 'marketing': False, 'tags': ['Awesome']})
        db.delete('person')
        db.query('select * from person')

        # This creates a log instead of a span because it's a generator.
        # It doesn't work for async surreal connections so this is the only part not tested in the async test.
        # Everything else should match.
        db.subscribe_live('foo')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'surrealdb use',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'namespace': 'namepace_test',
                    'database': 'database_test',
                    'logfire.msg_template': 'surrealdb use namespace = {namespace}, database = {database}',
                    'logfire.msg': 'surrealdb use namespace = namepace_test, database = database_test',
                    'logfire.json_schema': '{"type":"object","properties":{"namespace":{},"database":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb create',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'record': 'person',
                    'data': '{"user": "me", "password": "[Scrubbed due to \'password\']", "marketing": true, "tags": ["python", "documentation"]}',
                    'logfire.msg_template': 'surrealdb create {record}',
                    'logfire.msg': 'surrealdb create person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{},"data":{"type":"object"}}}',
                    'logfire.span_type': 'span',
                    'logfire.scrubbed': '[{"path": ["attributes", "data", "password"], "matched_substring": "password"}]',
                },
            },
            {
                'name': 'surrealdb select',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'record': 'person',
                    'logfire.msg_template': 'surrealdb select {record}',
                    'logfire.msg': 'surrealdb select person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb update',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'record': 'person',
                    'data': '{"user": "you", "password": "[Scrubbed due to \'password\']", "marketing": false, "tags": ["Awesome"]}',
                    'logfire.msg_template': 'surrealdb update {record}',
                    'logfire.msg': 'surrealdb update person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{},"data":{"type":"object"}}}',
                    'logfire.span_type': 'span',
                    'logfire.scrubbed': '[{"path": ["attributes", "data", "password"], "matched_substring": "password"}]',
                },
            },
            {
                'name': 'surrealdb delete',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'record': 'person',
                    'logfire.msg_template': 'surrealdb delete {record}',
                    'logfire.msg': 'surrealdb delete person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb query',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'query': 'select * from person',
                    'logfire.msg_template': 'surrealdb query {query}',
                    'logfire.msg': 'surrealdb query select * from person',
                    'logfire.json_schema': '{"type":"object","properties":{"query":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb subscribe_live {query_uuid}',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 13000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'surrealdb subscribe_live {query_uuid}',
                    'logfire.msg': 'surrealdb subscribe_live foo',
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'query_uuid': 'foo',
                    'logfire.json_schema': '{"type":"object","properties":{"query_uuid":{}}}',
                },
            },
            {
                'name': 'surrealdb close',
                'context': {'trace_id': 8, 'span_id': 14, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 15000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb',
                    'code.lineno': 123,
                    'logfire.msg_template': 'surrealdb close',
                    'logfire.msg': 'surrealdb close',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_instrument_surrealdb_async(exporter: TestExporter) -> None:
    logfire.instrument_surrealdb()

    async with AsyncSurreal('mem://') as db:
        await db.use('namepace_test', 'database_test')
        await db.create(
            'person',
            {
                'user': 'me',
                'password': 'safe',
                'marketing': True,
                'tags': ['python', 'documentation'],
            },
        )
        await db.select('person')
        await db.update('person', {'user': 'you', 'password': 'very_safe', 'marketing': False, 'tags': ['Awesome']})
        await db.delete('person')
        await db.query('select * from person')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'surrealdb use',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'namespace': 'namepace_test',
                    'database': 'database_test',
                    'logfire.msg_template': 'surrealdb use namespace = {namespace}, database = {database}',
                    'logfire.msg': 'surrealdb use namespace = namepace_test, database = database_test',
                    'logfire.json_schema': '{"type":"object","properties":{"namespace":{},"database":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb create',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'record': 'person',
                    'data': '{"user": "me", "password": "[Scrubbed due to \'password\']", "marketing": true, "tags": ["python", "documentation"]}',
                    'logfire.msg_template': 'surrealdb create {record}',
                    'logfire.msg': 'surrealdb create person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{},"data":{"type":"object"}}}',
                    'logfire.span_type': 'span',
                    'logfire.scrubbed': '[{"path": ["attributes", "data", "password"], "matched_substring": "password"}]',
                },
            },
            {
                'name': 'surrealdb select',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'record': 'person',
                    'logfire.msg_template': 'surrealdb select {record}',
                    'logfire.msg': 'surrealdb select person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb update',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'record': 'person',
                    'data': '{"user": "you", "password": "[Scrubbed due to \'password\']", "marketing": false, "tags": ["Awesome"]}',
                    'logfire.msg_template': 'surrealdb update {record}',
                    'logfire.msg': 'surrealdb update person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{},"data":{"type":"object"}}}',
                    'logfire.span_type': 'span',
                    'logfire.scrubbed': '[{"path": ["attributes", "data", "password"], "matched_substring": "password"}]',
                },
            },
            {
                'name': 'surrealdb delete',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'record': 'person',
                    'logfire.msg_template': 'surrealdb delete {record}',
                    'logfire.msg': 'surrealdb delete person',
                    'logfire.json_schema': '{"type":"object","properties":{"record":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb query',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'query': 'select * from person',
                    'logfire.msg_template': 'surrealdb query {query}',
                    'logfire.msg': 'surrealdb query select * from person',
                    'logfire.json_schema': '{"type":"object","properties":{"query":{}}}',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'surrealdb close',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_surrealdb.py',
                    'code.function': 'test_instrument_surrealdb_async',
                    'code.lineno': 123,
                    'logfire.msg_template': 'surrealdb close',
                    'logfire.msg': 'surrealdb close',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
