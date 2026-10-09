from __future__ import annotations

import functools
from contextvars import ContextVar
from threading import Lock
from types import ModuleType
from typing import Any
from weakref import WeakKeyDictionary

from logfire import Logfire
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors

try:
    import snowflake.connector as sf_connector
    from snowflake.connector.connection import SnowflakeConnection
    from snowflake.connector.cursor import SnowflakeCursor, SnowflakeCursorBase
except ModuleNotFoundError as e:
    if e.name not in {'snowflake', 'snowflake.connector'}:
        raise
    raise ImportError('Run `pip install snowflake-connector-python` to use `logfire.instrument_snowflake()`.') from e

# Each entry is the `Logfire` instance to record spans with and its `capture_parameters` setting.
# `None` means the module is not instrumented, so only connections registered below produce spans.
_module_settings: tuple[Logfire, bool] | None = None
_connection_settings: WeakKeyDictionary[SnowflakeConnection, tuple[Logfire, bool]] = WeakKeyDictionary()
_inside_executemany: ContextVar[bool] = ContextVar('logfire_snowflake_inside_executemany', default=False)
_inside_execute: ContextVar[bool] = ContextVar('logfire_snowflake_inside_execute', default=False)
_instrument_lock = Lock()


def instrument_snowflake(
    logfire_instance: Logfire,
    conn_or_module: ModuleType | SnowflakeConnection | None,
    capture_parameters: bool,
) -> None:
    global _module_settings

    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='snowflake')
    with _instrument_lock:
        if conn_or_module is None or conn_or_module is sf_connector:
            if _module_settings is None:
                _module_settings = (logfire_instance, capture_parameters)
                _patch_connect(logfire_instance)
            elif _module_settings[1] != capture_parameters:
                _warn_capture_parameters_ignored(_module_settings[1])
        elif isinstance(conn_or_module, SnowflakeConnection):
            existing = _connection_settings.get(conn_or_module)
            if existing is None:
                _connection_settings[conn_or_module] = (logfire_instance, capture_parameters)
            elif existing[1] != capture_parameters:
                _warn_capture_parameters_ignored(existing[1])
        else:
            raise ValueError(f"Don't know how to instrument {conn_or_module!r}")
        _patch_cursor_class()
        _patch_cursor_factory()


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


def _patch_cursor_class() -> None:
    original_execute = SnowflakeCursorBase.__dict__['execute']
    if not getattr(original_execute, '_logfire_patched', False):
        SnowflakeCursorBase.execute = _wrap_execute(original_execute)

    original_executemany = SnowflakeCursorBase.__dict__['executemany']
    if not getattr(original_executemany, '_logfire_patched', False):
        SnowflakeCursorBase.executemany = _wrap_executemany(original_executemany)


def _patch_cursor_factory() -> None:
    original_cursor: Any = SnowflakeConnection.__dict__['cursor']
    if getattr(original_cursor, '_logfire_patched', False):
        return

    @functools.wraps(original_cursor)
    def wrapped_cursor(self: SnowflakeConnection, *args: Any, **kwargs: Any) -> SnowflakeCursorBase[Any]:
        cursor: SnowflakeCursorBase[Any] = original_cursor(self, *args, **kwargs)
        with _instrument_lock:
            _patch_custom_cursor_class(type(cursor))
        return cursor

    wrapped_cursor._logfire_patched = True  # type: ignore[attr-defined]
    SnowflakeConnection.cursor = wrapped_cursor


def _patch_custom_cursor_class(cursor_class: type[SnowflakeCursorBase[Any]]) -> None:
    for name, wrap in (('execute', _wrap_execute), ('executemany', _wrap_executemany)):
        original = cursor_class.__dict__.get(name)
        if original is not None and not getattr(original, '_logfire_patched', False):
            setattr(cursor_class, name, wrap(original))


def _settings(cursor: SnowflakeCursor) -> tuple[Logfire, bool] | None:
    """Return the settings this cursor was instrumented with, or `None` if it isn't instrumented."""
    settings = None
    with handle_internal_errors:
        settings = _connection_settings.get(cursor.connection)
    return _module_settings if settings is None else settings


def _wrap_execute(original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, params: Any = None, *args: Any, **kwargs: Any) -> Any:
        if _inside_executemany.get() or _inside_execute.get():
            return original(self, command, params, *args, **kwargs)
        settings = _settings(self)
        if settings is None:
            return original(self, command, params, *args, **kwargs)
        logfire_instance, capture_parameters = settings
        attributes = _query_span_attributes(command, self, logfire_instance)
        if capture_parameters and params is not None:
            attributes['params'] = params
        if kwargs.get('_exec_async') or (len(args) > 2 and args[2]):
            template = 'snowflake execute async {command}'
            span_name = 'snowflake execute async'
        else:
            template = 'snowflake execute {command}'
            span_name = 'snowflake execute'
        with logfire_instance.span(template, _span_name=span_name, **attributes) as span:
            token = _inside_execute.set(True)
            try:
                result = original(self, command, params, *args, **kwargs)
            finally:
                _inside_execute.reset(token)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped


def _wrap_executemany(original: Any) -> Any:
    @functools.wraps(original)
    def wrapped(self: SnowflakeCursor, command: str, seqparams: Any, **kwargs: Any) -> Any:
        if _inside_executemany.get():
            return original(self, command, seqparams, **kwargs)
        settings = _settings(self)
        if settings is None:
            return original(self, command, seqparams, **kwargs)
        logfire_instance, capture_parameters = settings
        attributes = _query_span_attributes(command, self, logfire_instance)
        if capture_parameters:
            attributes['seqparams'] = seqparams
        with logfire_instance.span(
            'snowflake executemany {command}', _span_name='snowflake executemany', **attributes
        ) as span:
            token = _inside_executemany.set(True)
            try:
                result = original(self, command, seqparams, **kwargs)
            finally:
                _inside_executemany.reset(token)
            with handle_internal_errors:
                span.set_attribute('sfqid', self.sfqid)
                span.set_attribute('rowcount', self.rowcount)
            return result

    wrapped._logfire_patched = True  # type: ignore[attr-defined]
    return wrapped


def _query_span_attributes(command: str, cursor: SnowflakeCursor, logfire_instance: Logfire) -> dict[str, Any]:
    scrubbed_command = '[Scrubbed]'
    with handle_internal_errors:
        scrubbed_command, _ = logfire_instance.config.scrubber.scrub_value(('attributes', 'command'), command)
    attributes: dict[str, Any] = {
        'command': command,
        'db.system': 'snowflake',
        'db.statement': scrubbed_command,
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
