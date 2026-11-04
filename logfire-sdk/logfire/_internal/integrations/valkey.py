from __future__ import annotations

import logging
from collections.abc import Callable, Generator
from contextlib import contextmanager
from threading import Event, Lock
from typing import Any, TypeVar

from logfire.integrations.valkey import RequestHook, RequestHookContext, ResponseHook, ResponseHookContext

try:
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey
    from valkey.exceptions import ResponseError
except ModuleNotFoundError as exc:
    if exc.name != 'valkey':
        raise
    raise RuntimeError(
        '`logfire.instrument_valkey()` requires the `valkey` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[valkey]'"
    ) from exc

from opentelemetry.trace import Span, SpanKind, StatusCode, Tracer
from wrapt import FunctionWrapper

from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.utils import is_instrumentation_suppressed, log_internal_error

_logger = logging.getLogger(__name__)

_METHOD = 'execute_command'

_lock = Lock()
_active_installation: Event | None = None
_originals: list[tuple[type[Valkey] | type[AsyncValkey], Any, Any]] = []


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
    global _active_installation
    with _lock:
        if _active_installation is not None:
            return

        installation = Event()
        patches: list[tuple[type[Valkey] | type[AsyncValkey], Any, Any]] = []
        for cls, wrapper in (
            (Valkey, _traced_sync_wrapper(tracer, capture_statement, request_hook, response_hook)),
            (AsyncValkey, _traced_async_wrapper(tracer, capture_statement, request_hook, response_hook)),
        ):
            original = vars(cls)[_METHOD]
            patched = FunctionWrapper(original, wrapper, enabled=installation.is_set)
            patches.append((cls, original, patched))

        for cls, _, patched in patches:
            setattr(cls, _METHOD, patched)
        _originals.extend(patches)
        installation.set()
        _active_installation = installation


def uninstrument_valkey() -> None:
    """Remove Valkey instrumentation applied by `instrument_valkey`."""
    global _active_installation
    with _lock:
        if _active_installation is None:
            return
        _active_installation.clear()
        while _originals:
            cls, original, patched = _originals.pop()
            if vars(cls).get(_METHOD) is patched:
                setattr(cls, _METHOD, original)
        _active_installation = None


def _arg_to_str(arg: Any) -> str:
    if isinstance(arg, (bytes, bytearray)):
        return bytes(arg).decode('utf-8', errors='replace')
    return str(arg)


def _command_tokens(args: tuple[Any, ...]) -> list[str]:
    if not args:
        return []
    first = args[0]
    if isinstance(first, bytes):
        first = bytes.decode(first, errors='replace')
    elif isinstance(first, bytearray):
        first = bytearray.decode(first, errors='replace')
    return str.split(first) if isinstance(first, str) else []


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


@contextmanager
def _command_span(tracer: Tracer, command: str) -> Generator[Span, None, None]:
    with tracer.start_as_current_span(
        command, kind=SpanKind.CLIENT, record_exception=False, set_status_on_exception=False
    ) as span:
        try:
            yield span
        except ResponseError as exc:
            # Valkey can include raw command arguments in server error messages.
            span.set_status(StatusCode.ERROR)
            span.add_event('exception', {'exception.type': type(exc).__qualname__})
            raise
        except Exception as exc:
            span.set_status(StatusCode.ERROR)
            span.record_exception(exc, escaped=True)
            raise


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
        with _command_span(tracer, command) as span:
            _set_attributes(span, instance, args, tokens, command, capture_statement)
            if request_hook is not None:
                _execute_hook(request_hook, RequestHookContext(span, instance, args, kwargs.copy()))
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
        with _command_span(tracer, command) as span:
            _set_attributes(span, instance, args, tokens, command, capture_statement)
            if request_hook is not None:
                _execute_hook(request_hook, RequestHookContext(span, instance, args, kwargs.copy()))
            response = await wrapped(*args, **kwargs)
            if response_hook is not None:
                _execute_hook(response_hook, ResponseHookContext(span, instance, response))
            return response

    return wrapper
