from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from logfire.integrations.valkey import RequestHook, RequestHookContext, ResponseHook, ResponseHookContext

try:
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey
except ModuleNotFoundError as exc:
    if exc.name != 'valkey':
        raise
    raise RuntimeError(
        '`logfire.instrument_valkey()` requires the `valkey` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[valkey]'"
    ) from exc

from opentelemetry.trace import Span, SpanKind, Tracer
from wrapt import wrap_function_wrapper

from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.utils import is_instrumentation_suppressed, log_internal_error

_logger = logging.getLogger(__name__)

_METHOD = 'execute_command'

_originals: list[tuple[Any, str, Any]] = []
_is_instrumented = False


def instrument_valkey(
    *,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
    tracer: Tracer,
) -> None:
    """Instrument the `valkey` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_valkey` method for details.
    """
    global _is_instrumented
    if _is_instrumented:
        return

    sync_wrapper = _traced_sync_wrapper(tracer, capture_statement, request_hook, response_hook)
    async_wrapper = _traced_async_wrapper(tracer, capture_statement, request_hook, response_hook)

    for cls, wrapper in (
        (Valkey, sync_wrapper),
        (AsyncValkey, async_wrapper),
    ):
        _originals.append((cls, _METHOD, getattr(cls, _METHOD)))
        wrap_function_wrapper(cls, _METHOD, wrapper)

    _is_instrumented = True


def uninstrument_valkey() -> None:
    """Remove Valkey instrumentation applied by `instrument_valkey`."""
    global _is_instrumented
    if not _is_instrumented:
        return
    while _originals:
        cls, method, original = _originals.pop()
        setattr(cls, method, original)
    _is_instrumented = False


def _arg_to_str(arg: Any) -> str:
    if isinstance(arg, (bytes, bytearray)):
        return bytes(arg).decode('utf-8', errors='replace')
    return str(arg)


def _command_tokens(args: tuple[Any, ...]) -> list[str]:
    if not args:
        return []
    first = args[0]
    if not isinstance(first, (str, bytes, bytearray)):
        return []
    return _arg_to_str(first).split()


def _span_name(tokens: list[str]) -> str:
    if tokens and len(tokens[0]) <= 32 and tokens[0].isascii() and tokens[0].isprintable():
        return tokens[0].upper()
    return 'valkey'


def _set_attributes(
    span: Span,
    instance: Valkey | AsyncValkey,
    args: tuple[Any, ...],
    tokens: list[str],
    command: str,
    capture_statement: bool,
) -> None:
    if not span.is_recording():
        return
    try:
        _record_attributes(span, instance, args, tokens, command, capture_statement)
    except Exception:
        log_internal_error()


def _record_attributes(
    span: Span,
    instance: Valkey | AsyncValkey,
    args: tuple[Any, ...],
    tokens: list[str],
    command: str,
    capture_statement: bool,
) -> None:
    arg_count = len(args) + max(0, len(tokens) - 1)
    display = (
        ' '.join([command] + ['?'] * (arg_count - 1)) if tokens and command != 'valkey' else ' '.join(['?'] * arg_count)
    )
    span.set_attribute('db.system', 'valkey')
    span.set_attribute('db.statement', display)
    # These commands can carry credentials without recognizable secret names.
    if capture_statement and command not in {'ACL', 'AUTH', 'CONFIG', 'HELLO', 'MIGRATE', 'valkey'}:
        span.set_attribute('db.valkey.command', ' '.join(map(_arg_to_str, args)))
    span.set_attribute('db.valkey.args_length', arg_count)
    span.set_attribute(ATTRIBUTES_MESSAGE_KEY, display)
    pool = getattr(instance, 'connection_pool', None)
    connection_kwargs: dict[str, Any] = getattr(pool, 'connection_kwargs', {})
    host = connection_kwargs.get('host')
    if host is not None:
        span.set_attribute('server.address', host)
    port = connection_kwargs.get('port')
    if port is not None:
        span.set_attribute('server.port', port)
    db = connection_kwargs.get('db')
    if db is not None:
        span.set_attribute('db.valkey.database_index', db)


T = TypeVar('T')


def _execute_hook(hook: Callable[[T], None], context: T) -> None:
    try:
        hook(context)
    except Exception:
        _logger.warning('Exception raised by hook %r', hook, exc_info=True)


def _traced_sync_wrapper(
    tracer: Tracer,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
):
    def wrapper(wrapped: Any, instance: Valkey, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if is_instrumentation_suppressed():
            return wrapped(*args, **kwargs)
        tokens = _command_tokens(args)
        command = _span_name(tokens)
        with tracer.start_as_current_span(command, kind=SpanKind.CLIENT) as span:
            _set_attributes(span, instance, args, tokens, command, capture_statement)
            if request_hook is not None:
                _execute_hook(request_hook, RequestHookContext(span, instance, args, kwargs.copy()))
            # Exceptions propagate through the span, which records them automatically.
            response = wrapped(*args, **kwargs)
            if response_hook is not None:
                _execute_hook(response_hook, ResponseHookContext(span, instance, response))
            return response

    return wrapper


def _traced_async_wrapper(
    tracer: Tracer,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
):
    async def wrapper(wrapped: Any, instance: AsyncValkey, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        if is_instrumentation_suppressed():
            return await wrapped(*args, **kwargs)
        tokens = _command_tokens(args)
        command = _span_name(tokens)
        with tracer.start_as_current_span(command, kind=SpanKind.CLIENT) as span:
            _set_attributes(span, instance, args, tokens, command, capture_statement)
            if request_hook is not None:
                _execute_hook(request_hook, RequestHookContext(span, instance, args, kwargs.copy()))
            # Exceptions propagate through the span, which records them automatically.
            response = await wrapped(*args, **kwargs)
            if response_hook is not None:
                _execute_hook(response_hook, ResponseHookContext(span, instance, response))
            return response

    return wrapper
