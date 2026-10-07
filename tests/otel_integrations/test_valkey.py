from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.trace import Span

import logfire
import logfire._internal.integrations.valkey
from logfire._internal.integrations.valkey import uninstrument_valkey
from logfire.testing import TestExporter


def _sync_execute(client: Any, *args: Any) -> Any:
    return client.execute_command(*args)


async def _async_execute(client: Any, *args: Any) -> Any:
    return await client.execute_command(*args)


@pytest.fixture
def valkey_behavior(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Patch both Valkey clients with fakes so no server is needed, then instrument."""
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey

    behavior: dict[str, Any] = {'error': None}

    def fake_sync(self: Any, *args: Any, **kwargs: Any) -> Any:
        if behavior['error'] is not None:
            raise behavior['error']
        return 'OK'

    async def fake_async(self: Any, *args: Any, **kwargs: Any) -> Any:
        if behavior['error'] is not None:
            raise behavior['error']
        return 'OK'

    monkeypatch.setattr(Valkey, 'execute_command', fake_sync)
    monkeypatch.setattr(AsyncValkey, 'execute_command', fake_async)
    logfire.instrument_valkey()
    try:
        yield behavior
    finally:
        uninstrument_valkey()


def test_instrument_valkey(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'SET', 'my-key', 123) == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET ? ?',
                    'db.system': 'valkey',
                    'db.statement': 'SET ? ?',
                    'db.valkey.args_length': 3,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


def test_instrument_valkey_capture_statement(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    uninstrument_valkey()
    logfire.instrument_valkey(capture_statement=True)

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'SET', 'my-key', 123) == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET my-key 123',
                    'db.system': 'valkey',
                    'db.statement': 'SET my-key 123',
                    'db.valkey.args_length': 3,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


def test_instrument_valkey_empty_args(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client) == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'valkey',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': '',
                    'db.system': 'valkey',
                    'db.statement': '',
                    'db.valkey.args_length': 0,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


def test_instrument_valkey_no_connection_attributes(
    monkeypatch: pytest.MonkeyPatch, valkey_behavior: dict[str, Any], exporter: TestExporter
):
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    monkeypatch.setattr(client.connection_pool, 'connection_kwargs', {})
    assert _sync_execute(client, 'GET', 'my-key') == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'GET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'GET ?',
                    'db.system': 'valkey',
                    'db.statement': 'GET ?',
                    'db.valkey.args_length': 2,
                },
            }
        ]
    )


def test_instrument_valkey_error(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    valkey_behavior['error'] = ValueError('boom')

    client = Valkey(host='localhost', port=6379, db=0)
    with pytest.raises(ValueError, match='boom'):
        _sync_execute(client, 'GET', 'my-key')

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert spans[0]['name'] == 'GET'
    assert spans[0]['attributes']['db.system'] == 'valkey'
    assert [e['name'] for e in spans[0]['events']] == ['exception']


def test_instrument_valkey_with_hooks(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    def request_hook(span: Span, instance: Any, *args: Any, **kwargs: Any) -> None:
        span.set_attribute('potato', 'tomato')

    def response_hook(span: Span, instance: Any, response: Any) -> None:
        span.set_attribute('response', str(response))

    uninstrument_valkey()
    logfire.instrument_valkey(request_hook=request_hook, response_hook=response_hook)

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'GET', 'my-key') == 'OK'

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans[0]['attributes']['potato'] == 'tomato'
    assert spans[0]['attributes']['response'] == 'OK'


def test_instrument_valkey_hook_error(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    def bad_hook(span: Span, instance: Any, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError('hook failure')

    uninstrument_valkey()
    logfire.instrument_valkey(request_hook=bad_hook, response_hook=bad_hook)

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'GET', 'my-key') == 'OK'

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert spans[0]['name'] == 'GET'


@pytest.mark.anyio
async def test_instrument_valkey_async(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey.asyncio import Valkey as AsyncValkey

    client = AsyncValkey(host='localhost', port=6379, db=0)
    assert await _async_execute(client, 'SET', 'my-key', 123) == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'SET',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SET ? ?',
                    'db.system': 'valkey',
                    'db.statement': 'SET ? ?',
                    'db.valkey.args_length': 3,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_instrument_valkey_async_error(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey.asyncio import Valkey as AsyncValkey

    valkey_behavior['error'] = ConnectionError('lost')

    client = AsyncValkey(host='localhost', port=6379, db=0)
    with pytest.raises(ConnectionError, match='lost'):
        await _async_execute(client, 'GET', 'my-key')

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    assert [e['name'] for e in spans[0]['events']] == ['exception']


def test_instrument_valkey_idempotent(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    logfire.instrument_valkey()
    logfire.instrument_valkey()

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'PING') == 'OK'

    assert len(exporter.exported_spans_as_dict()) == 1


def test_uninstrument_valkey_without_instrument():
    uninstrument_valkey()
    uninstrument_valkey()


def test_missing_valkey_dependency() -> None:
    with mock.patch.dict(
        'sys.modules',
        {'valkey': None, 'logfire.integrations.valkey': None},
    ):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.valkey)
        assert str(exc_info.value) == snapshot(
            """\
`logfire.instrument_valkey()` requires the `valkey` package.
You can install this with:
    pip install 'logfire[valkey]'\
"""
        )
