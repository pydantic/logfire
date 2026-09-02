from __future__ import annotations

import functools
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
    original_connect = sf_connector.connect
    if getattr(original_connect, '_logfire_patched', False):
        return

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
