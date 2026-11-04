from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator
from typing import Any
from unittest import mock

import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.valkey import uninstrument_valkey
from logfire.integrations.valkey import RequestHookContext, ResponseHookContext
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
                    'logfire.msg': 'SET ? ?',
                    'db.system': 'valkey',
                    'db.statement': 'SET ? ?',
                    'db.valkey.command': 'SET my-key 123',
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


def test_instrument_valkey_compound_command_redacted(valkey_behavior: dict[str, Any], exporter: TestExporter):
    """`execute_command('AUTH secret')` is valid — credentials must not leak with capture off."""
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'AUTH secret123') == 'OK'

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'AUTH',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'AUTH ?',
                    'db.system': 'valkey',
                    'db.statement': 'AUTH ?',
                    'db.valkey.args_length': 2,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


def test_instrument_valkey_whitespace_command(valkey_behavior: dict[str, Any], exporter: TestExporter):
    """Whitespace-only first arg has no verb — must not leak and must not crash."""
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, '   ') == 'OK'

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
                    'logfire.msg': '?',
                    'db.system': 'valkey',
                    'db.statement': '?',
                    'db.valkey.args_length': 1,
                    'db.valkey.database_index': 0,
                    'server.address': 'localhost',
                    'server.port': 6379,
                },
            }
        ]
    )


def test_instrument_valkey_bytes_command(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, b'SET', b'my-key', b'123') == 'OK'

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans[0]['name'] == 'SET'
    assert spans[0]['attributes']['db.statement'] == 'SET ? ?'
    assert spans[0]['attributes']['db.valkey.args_length'] == 3


def test_instrument_valkey_no_connection_attributes(
    monkeypatch: pytest.MonkeyPatch, valkey_behavior: dict[str, Any], exporter: TestExporter
):
    from valkey import ConnectionPool, Valkey

    pool = ConnectionPool(host='localhost', port=6379, db=0)
    client = Valkey(connection_pool=pool)
    monkeypatch.setattr(pool, 'connection_kwargs', {})
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


def test_valkey_server_error_does_not_capture_arguments(
    valkey_behavior: dict[str, Any], exporter: TestExporter
) -> None:
    from valkey import Valkey
    from valkey.exceptions import ResponseError

    error = ResponseError("unknown command 'GTE', with args beginning with: 'private-key-123'")
    valkey_behavior['error'] = error
    with pytest.raises(ResponseError) as exc_info:
        _sync_execute(Valkey(), 'GTE', 'private-key-123')

    assert exc_info.value is error
    (span,) = exporter.exported_spans_as_dict()
    assert 'private-key-123' not in str(span)
    (event,) = span['events']
    assert event['attributes'] == {'exception.type': 'ResponseError'}
    assert exporter.exported_spans[-1].status.status_code.name == 'ERROR'


def test_instrument_valkey_with_hooks(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    def request_hook(context: RequestHookContext) -> None:
        context.span.set_attribute('potato', 'tomato')

    def response_hook(context: ResponseHookContext) -> None:
        context.span.set_attribute('response', str(context.response))

    uninstrument_valkey()
    logfire.instrument_valkey(request_hook=request_hook, response_hook=response_hook)

    client = Valkey(host='localhost', port=6379, db=0)
    assert _sync_execute(client, 'GET', 'my-key') == 'OK'

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans[0]['attributes']['potato'] == 'tomato'
    assert spans[0]['attributes']['response'] == 'OK'


def test_instrument_valkey_hook_error(valkey_behavior: dict[str, Any], exporter: TestExporter):
    from valkey import Valkey

    def bad_hook(context: RequestHookContext | ResponseHookContext) -> None:
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
    with mock.patch.dict('sys.modules', {'valkey': None}):
        # Evict cached integration modules so the missing `valkey` dependency is actually exercised.
        sys.modules.pop('logfire._internal.integrations.valkey', None)
        with pytest.raises(RuntimeError) as exc_info:
            importlib.import_module('logfire._internal.integrations.valkey')
        assert str(exc_info.value) == snapshot(
            """\
`logfire.instrument_valkey()` requires the `valkey` package.
You can install this with:
    pip install 'logfire[valkey]'\
"""
        )


def test_unrelated_import_error_reraised() -> None:
    """Unrelated ModuleNotFoundError must not be masked as missing valkey."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'valkey':
            raise ModuleNotFoundError("No module named 'other_dep'", name='other_dep')
        return real_import(name, *args, **kwargs)

    with mock.patch.dict(sys.modules), mock.patch('builtins.__import__', side_effect=fake_import):
        sys.modules.pop('logfire._internal.integrations.valkey', None)
        with pytest.raises(ModuleNotFoundError) as exc_info:
            importlib.import_module('logfire._internal.integrations.valkey')
        assert exc_info.value.name == 'other_dep'


def test_internal_exception_does_not_block_valkey_command(valkey_behavior: dict[str, Any]) -> None:
    from valkey import Valkey

    class Unprintable:
        def __str__(self) -> str:
            raise ValueError('cannot format telemetry')

    uninstrument_valkey()
    logfire.instrument_valkey(capture_statement=True)
    assert _sync_execute(Valkey(), 'SET', 'key', Unprintable()) == 'OK'


def test_valkey_capture_scrubs_secrets(valkey_behavior: dict[str, Any], exporter: TestExporter) -> None:
    from valkey import Valkey

    uninstrument_valkey()
    logfire.instrument_valkey(capture_statement=True)
    client = Valkey()
    _sync_execute(client, 'AUTH', 'opaque-credential-123')
    _sync_execute(client, 'SET', 'password', 'another-credential-456')
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert 'db.valkey.command' not in spans[0]['attributes']
    assert 'Scrubbed' in spans[1]['attributes']['db.valkey.command']
    assert 'opaque-credential-123' not in str(spans)
    assert 'another-credential-456' not in str(spans)


@pytest.mark.anyio
async def test_valkey_context_and_suppression(valkey_behavior: dict[str, Any], exporter: TestExporter) -> None:
    from opentelemetry.trace import get_current_span
    from valkey.asyncio import Valkey

    client = Valkey()
    with logfire.span('parent') as parent:
        assert await _async_execute(client, 'PING') == 'OK'
        assert get_current_span().get_span_context() == parent.context
        with logfire.suppress_instrumentation():
            assert await _async_execute(client, 'PING') == 'OK'
    command, parent_span = exporter.exported_spans_as_dict(include_instrumentation_scope=True)
    assert command['parent'] == parent_span['context']
    assert command['instrumentation_scope'] == 'logfire.valkey'


def test_valkey_instruments_existing_client_at_transport_boundary(
    monkeypatch: pytest.MonkeyPatch, exporter: TestExporter
) -> None:
    from valkey import Connection, ConnectionPool, Valkey

    pool = ConnectionPool()
    client = Valkey(connection_pool=pool)
    connection = Connection()
    send = mock.Mock()
    monkeypatch.setattr(pool, 'get_connection', mock.Mock(return_value=connection))
    monkeypatch.setattr(pool, 'release', mock.Mock())
    monkeypatch.setattr(connection, 'send_command', send)
    monkeypatch.setattr(connection, 'read_response', mock.Mock(return_value=b'PONG'))

    logfire.instrument_valkey()
    try:
        assert client.ping() is True  # pyright: ignore[reportUnknownMemberType]
    finally:
        uninstrument_valkey()

    assert send.call_args.args == ('PING',)
    assert len(exporter.exported_spans_as_dict()) == 1
    span = exporter.exported_spans[-1]
    assert span.name == 'PING'
    assert span.kind.name == 'CLIENT'
