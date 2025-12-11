import inspect

from inline_snapshot import snapshot
from surrealdb import BlockingHttpSurrealConnection

import logfire


def test_instrument_surrealdb():
    logfire.instrument_surrealdb()
    templates: list[str] = []
    for _name, method in inspect.getmembers(BlockingHttpSurrealConnection):
        template = getattr(method, '_logfire_template', None)
        if template is not None:
            templates.append(template)
    assert sorted(templates) == snapshot(
        [
            'surrealdb authenticate {token}',
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
