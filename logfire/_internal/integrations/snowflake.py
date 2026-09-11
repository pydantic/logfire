from __future__ import annotations

import functools
import types
from types import ModuleType
from typing import Any

from logfire import Logfire
from logfire._internal.utils import handle_internal_errors

try:
    import snowflake.connector as sf_connector
    from snowflake.connector.connection import SnowflakeConnection
    from snowflake.connector.cursor import SnowflakeCursor
except ModuleNotFoundError as e:
    if e.name not in {'snowflake', 'snowflake.connector'}:
        raise
    raise ImportError('Run `pip install snowflake-connector-python` to use `logfire.instrument_snowflake()`.') from e

CONNECTION_ATTRS = ('account', 'warehouse', 'database', 'schema', 'role')


def _connection_attributes(conn: Any) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for name in CONNECTION_ATTRS:
        value = getattr(conn, name, None)
        if value is not None:
            attributes[name] = value
    return attributes


def _query_span_attributes(command: str, cursor: SnowflakeCursor) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        'command': command,
        'db.system': 'snowflake',
        'db.statement': command,
    }
    with handle_internal_errors:
        attributes.update(_connection_attributes(cursor.connection))
    return attributes


def _unpatched(method: Any) -> Any:
    while getattr(method, '_logfire_patched', False):
        wrapped = getattr(method, '__wrapped__', None)
        if wrapped is None:  # pragma: no cover
            break
        method = wrapped
    return method


def instrument_snowflake(
    logfire_instance: Logfire,
    conn_or_module: ModuleType | SnowflakeConnection | None,
    capture_parameters: bool,
) -> None:
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='snowflake')
    if conn_or_module is None or conn_or_module is sf_connector:
        _instrument_module(logfire_instance, capture_parameters)
    elif isinstance(conn_or_module, SnowflakeConnection):
        _instrument_connection(logfire_instance, conn_or_module, capture_parameters)
    else:
        raise ValueError(f"Don't know how to instrument {conn_or_module!r}")


def _instrument_module(logfire_instance: Logfire, capture_parameters: bool) -> None:
    original_connect: Any = sf_connector.connect  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not getattr(original_connect, '_logfire_patched', False):

        @functools.wraps(original_connect)
        def wrapped_connect(*args: Any, **kwargs: Any) -> SnowflakeConnection:
            with logfire_instance.span('snowflake connect', _span_name='snowflake connect') as span:
                conn = original_connect(*args, **kwargs)
                with handle_internal_errors:
                    for key, value in _connection_attributes(conn).items():
                        span.set_attribute(key, value)
                return conn

        wrapped_connect._logfire_patched = True  # type: ignore[attr-defined]
        sf_connector.connect = wrapped_connect

    _patch_cursor_class(logfire_instance, capture_parameters)


def _patch_cursor_class(logfire_instance: Logfire, capture_parameters: bool) -> None:
    original_execute = SnowflakeCursor.__dict__.get('execute', SnowflakeCursor.execute)
    if not getattr(original_execute, '_logfire_patched', False):
        SnowflakeCursor.execute = _wrap_execute(logfire_instance, original_execute, capture_parameters)

    original_executemany = SnowflakeCursor.__dict__.get('executemany', SnowflakeCursor.executemany)
    if not getattr(original_executemany, '_logfire_patched', False):
        SnowflakeCursor.executemany = _wrap_executemany(logfire_instance, original_executemany, capture_parameters)


def _instrument_connection(logfire_instance: Logfire, conn: SnowflakeConnection, capture_parameters: bool) -> None:
    original_cursor_factory = conn.cursor
    if getattr(original_cursor_factory, '_logfire_patched', False):
        return

    def wrapped_cursor_factory(*args: Any, **kwargs: Any) -> SnowflakeCursor:
        cursor = original_cursor_factory(*args, **kwargs)
        # Always wrap this connection's cursors with this call's capture_parameters,
        # using the unpatched methods so a later module-level patch cannot override
        # them or double-wrap.
        execute = _unpatched(SnowflakeCursor.execute)
        cursor.execute = types.MethodType(_wrap_execute(logfire_instance, execute, capture_parameters), cursor)
        executemany = _unpatched(SnowflakeCursor.executemany)
        cursor.executemany = types.MethodType(
            _wrap_executemany(logfire_instance, executemany, capture_parameters), cursor
        )
        return cursor

    wrapped_cursor_factory._logfire_patched = True  # type: ignore[attr-defined]
    conn.cursor = wrapped_cursor_factory


def _wrap_execute(logfire_instance: Logfire, original: Any, capture_parameters: bool) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        attributes = _query_span_attributes(command, self)
        if capture_parameters:
            attributes['params'] = params
        with logfire_instance.span('snowflake execute {command}', _span_name='snowflake execute', **attributes) as span:
            result = original(self, command, params, *args, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped


def _wrap_executemany(logfire_instance: Logfire, original: Any, capture_parameters: bool) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any) -> Any:
        attributes = _query_span_attributes(command, self)
        if capture_parameters:
            attributes['seqparams'] = seqparams
        with logfire_instance.span(
            'snowflake executemany {command}', _span_name='snowflake executemany', **attributes
        ) as span:
            result = original(self, command, seqparams, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped
