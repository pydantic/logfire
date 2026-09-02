from __future__ import annotations

import functools
import types
from types import ModuleType
from typing import Any

import snowflake.connector as sf_connector
from snowflake.connector.connection import SnowflakeConnection
from snowflake.connector.cursor import SnowflakeCursor

from logfire import Logfire
from logfire._internal.utils import handle_internal_errors

CONNECTION_ATTRS = ('account', 'warehouse', 'database', 'schema', 'role')


def _connection_attributes(conn: Any) -> dict[str, Any]:
    return {name: getattr(conn, name, None) for name in CONNECTION_ATTRS}


def instrument_snowflake(
    logfire_instance: Logfire,
    conn_or_module: ModuleType | SnowflakeConnection | None,
) -> None:
    if conn_or_module is None or conn_or_module is sf_connector:
        _instrument_module(logfire_instance)
    elif isinstance(conn_or_module, SnowflakeConnection):
        _instrument_connection(logfire_instance, conn_or_module)
    else:
        raise ValueError(f"Don't know how to instrument {conn_or_module!r}")


def _instrument_module(logfire_instance: Logfire) -> None:
    # The connect-patch guard and the cursor-patch guard are independent: even when connect()
    # is already patched, _patch_cursor_class still runs and makes its own idempotency check,
    # so re-instrumenting after something else resets SnowflakeCursor.execute (Task 5) still works.
    original_connect = sf_connector.connect
    if not getattr(original_connect, '_logfire_patched', False):

        @functools.wraps(original_connect)
        def wrapped_connect(**kwargs: Any) -> SnowflakeConnection:
            with logfire_instance.span('snowflake connect', _span_name='snowflake connect') as span:
                conn = original_connect(**kwargs)
                with handle_internal_errors:
                    for key, value in _connection_attributes(conn).items():
                        span.set_attribute(key, value)
                return conn

        wrapped_connect._logfire_patched = True  # type: ignore[attr-defined]
        sf_connector.connect = wrapped_connect

    _patch_cursor_class(logfire_instance)


def _patch_cursor_class(logfire_instance: Logfire) -> None:
    original_execute = SnowflakeCursor.__dict__.get('execute', SnowflakeCursor.execute)
    if not getattr(original_execute, '_logfire_patched', False):
        SnowflakeCursor.execute = _wrap_execute(logfire_instance, original_execute)  # type: ignore[method-assign]

    original_executemany = SnowflakeCursor.__dict__.get('executemany', SnowflakeCursor.executemany)
    if not getattr(original_executemany, '_logfire_patched', False):
        SnowflakeCursor.executemany = _wrap_executemany(logfire_instance, original_executemany)  # type: ignore[method-assign]


def _instrument_connection(logfire_instance: Logfire, conn: SnowflakeConnection) -> None:
    original_cursor_factory = conn.cursor
    if getattr(original_cursor_factory, '_logfire_patched', False):
        return

    def wrapped_cursor_factory(*args: Any, **kwargs: Any) -> SnowflakeCursor:
        cursor = original_cursor_factory(*args, **kwargs)
        cursor.execute = types.MethodType(_wrap_execute(logfire_instance, SnowflakeCursor.execute), cursor)
        cursor.executemany = types.MethodType(_wrap_executemany(logfire_instance, SnowflakeCursor.executemany), cursor)
        return cursor

    wrapped_cursor_factory._logfire_patched = True  # type: ignore[attr-defined]
    conn.cursor = wrapped_cursor_factory  # type: ignore[method-assign]


def _wrap_execute(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        attributes: dict[str, Any] = {'command': command, 'params': params}
        with handle_internal_errors:
            attributes.update(_connection_attributes(self.connection))
        with logfire_instance.span('snowflake execute {command}', _span_name='snowflake execute', **attributes) as span:
            result = original(self, command, params, *args, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped


def _wrap_executemany(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any) -> Any:
        attributes: dict[str, Any] = {'command': command, 'seqparams': seqparams}
        with handle_internal_errors:
            attributes.update(_connection_attributes(self.connection))
        with logfire_instance.span('snowflake executemany {command}', _span_name='snowflake executemany', **attributes) as span:
            result = original(self, command, seqparams, **kwargs)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped
