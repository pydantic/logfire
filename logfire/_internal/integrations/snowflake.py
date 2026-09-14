from __future__ import annotations

import functools
from types import ModuleType
from typing import Any
from weakref import WeakKeyDictionary

from logfire import Logfire
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors

try:
    import snowflake.connector as sf_connector
    from snowflake.connector.connection import SnowflakeConnection
    from snowflake.connector.cursor import SnowflakeCursor
except ModuleNotFoundError as e:
    if e.name not in {'snowflake', 'snowflake.connector'}:
        raise
    raise ImportError('Run `pip install snowflake-connector-python` to use `logfire.instrument_snowflake()`.') from e

# `None` means the module is not instrumented, so only connections registered below produce spans.
_module_capture_parameters: bool | None = None
_connection_capture_parameters: WeakKeyDictionary[SnowflakeConnection, bool] = WeakKeyDictionary()


def instrument_snowflake(
    logfire_instance: Logfire,
    conn_or_module: ModuleType | SnowflakeConnection | None,
    capture_parameters: bool,
) -> None:
    global _module_capture_parameters

    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='snowflake')
    if conn_or_module is None or conn_or_module is sf_connector:
        if _module_capture_parameters is None:
            _module_capture_parameters = capture_parameters
            _patch_connect(logfire_instance)
        elif _module_capture_parameters != capture_parameters:
            _warn_capture_parameters_ignored(_module_capture_parameters)
    elif isinstance(conn_or_module, SnowflakeConnection):
        existing = _connection_capture_parameters.get(conn_or_module)
        if existing is None:
            _connection_capture_parameters[conn_or_module] = capture_parameters
        elif existing != capture_parameters:
            _warn_capture_parameters_ignored(existing)
    else:
        raise ValueError(f"Don't know how to instrument {conn_or_module!r}")
    _patch_cursor_class(logfire_instance)


def _warn_capture_parameters_ignored(existing: bool) -> None:
    warn_at_user_stacklevel(
        f'Snowflake is already instrumented with `capture_parameters={existing}`, the new value is ignored.',
        UserWarning,
    )


def _patch_connect(logfire_instance: Logfire) -> None:
    original_connect: Any = sf_connector.connect  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @functools.wraps(original_connect)
    def wrapped_connect(*args: Any, **kwargs: Any) -> SnowflakeConnection:
        with logfire_instance.span('snowflake connect', _span_name='snowflake connect') as span:
            conn = original_connect(*args, **kwargs)
            with handle_internal_errors:
                for key, value in _connection_attributes(conn).items():
                    span.set_attribute(key, value)
            return conn

    sf_connector.connect = wrapped_connect


def _patch_cursor_class(logfire_instance: Logfire) -> None:
    original_execute = SnowflakeCursor.__dict__.get('execute', SnowflakeCursor.execute)
    if not getattr(original_execute, '_logfire_patched', False):
        SnowflakeCursor.execute = _wrap_execute(logfire_instance, original_execute)

    original_executemany = SnowflakeCursor.__dict__.get('executemany', SnowflakeCursor.executemany)
    if not getattr(original_executemany, '_logfire_patched', False):
        SnowflakeCursor.executemany = _wrap_executemany(logfire_instance, original_executemany)


def _capture_parameters(cursor: SnowflakeCursor) -> bool | None:
    """Return the effective `capture_parameters` for this cursor, or `None` if it isn't instrumented."""
    capture_parameters = None
    with handle_internal_errors:
        capture_parameters = _connection_capture_parameters.get(cursor.connection)
    return _module_capture_parameters if capture_parameters is None else capture_parameters


def _wrap_execute(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        capture_parameters = _capture_parameters(self)
        if capture_parameters is None:
            return original(self, command, params, *args, **kwargs)
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


def _wrap_executemany(logfire_instance: Logfire, original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any) -> Any:
        capture_parameters = _capture_parameters(self)
        if capture_parameters is None:
            return original(self, command, seqparams, **kwargs)
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


def _query_span_attributes(command: str, cursor: SnowflakeCursor) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        'command': command,
        'db.system': 'snowflake',
        'db.statement': command,
    }
    with handle_internal_errors:
        attributes.update(_connection_attributes(cursor.connection))
    return attributes


def _connection_attributes(conn: Any) -> dict[str, Any]:
    attributes: dict[str, Any] = {}
    for name in ('account', 'warehouse', 'database', 'schema', 'role'):
        value = getattr(conn, name, None)
        if value is not None:
            attributes[name] = value
    return attributes
