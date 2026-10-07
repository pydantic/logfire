from __future__ import annotations

import functools
import logging
from typing import Any

try:
    from logfire.integrations.valkey import RequestHook, ResponseHook
except ModuleNotFoundError as exc:
    if exc.name != 'valkey':
        raise
    raise RuntimeError(
        '`logfire.instrument_valkey()` requires the `valkey` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[valkey]'"
    ) from exc

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from wrapt import wrap_function_wrapper

from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.utils import truncate_string

_logger = logging.getLogger(__name__)

_CLASS = 'Valkey'
_METHOD = 'execute_command'

_originals: list[tuple[Any, str, Any]] = []
_is_instrumented = False


def instrument_valkey(
    *,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
    tracer_provider: Any | None = None,
    **kwargs: Any,
) -> None:
    """Instrument the `valkey` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_valkey` method for details.
    """
    global _is_instrumented
    if _is_instrumented:
        return

    tracer = trace.get_tracer(__name__, tracer_provider=tracer_provider)
    sync_wrapper = _traced_sync_wrapper(tracer, capture_statement, request_hook, response_hook)
    async_wrapper = _traced_async_wrapper(tracer, capture_statement, request_hook, response_hook)

    import valkey.asyncio.client
    import valkey.client

    for module, wrapper in (
        (valkey.client, sync_wrapper),
        (valkey.asyncio.client, async_wrapper),
    ):
        cls = getattr(module, _CLASS)
        _originals.append((cls, _METHOD, getattr(cls, _METHOD)))
        wrap_function_wrapper(module.__name__, f'{_CLASS}.{_METHOD}', wrapper)

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


def _first_arg_tokens(args: tuple[Any, ...]) -> list[str]:
    if not args:
        return []
    return _arg_to_str(args[0]).split()


def _span_name(args: tuple[Any, ...]) -> str:
    tokens = _first_arg_tokens(args)
    if not tokens:
        return 'valkey'
    return tokens[0].upper()


def _expanded_args_length(args: tuple[Any, ...]) -> int:
    tokens = _first_arg_tokens(args)
    if not args:
        return 0
    if not tokens:
        return len(args)
    return len(tokens) + len(args) - 1


def _sanitized_statement(args: tuple[Any, ...]) -> str:
    if not args:
        return ''
    tokens = _first_arg_tokens(args)
    if not tokens:
        return ' '.join(['?'] * len(args))
    return ' '.join([tokens[0]] + ['?'] * (len(tokens) + len(args) - 2))


def _display_statement(args: tuple[Any, ...], *, capture_statement: bool) -> tuple[str, str]:
    if capture_statement:
        full = ' '.join(map(_arg_to_str, args))
        truncate_value = functools.partial(truncate_string, max_length=20, middle='...')
        return full, ' '.join(map(truncate_value, map(_arg_to_str, args)))
    sanitized = _sanitized_statement(args)
    return sanitized, sanitized


def _set_attributes(span: Any, instance: Any, args: tuple[Any, ...], statement: str, display: str) -> None:
    span.set_attribute('db.system', 'valkey')
    span.set_attribute('db.statement', statement)
    span.set_attribute('db.valkey.args_length', _expanded_args_length(args))
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


def _execute_hook(hook: Any | None, *args: Any) -> None:
    if hook is None:
        return
    try:
        hook(*args)
    except Exception:
        _logger.warning('Exception raised by hook %r', hook, exc_info=True)


def _traced_sync_wrapper(
    tracer: Any,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
):
    def wrapper(wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        statement, display = _display_statement(args, capture_statement=capture_statement)
        with tracer.start_as_current_span(_span_name(args), kind=SpanKind.CLIENT) as span:
            _set_attributes(span, instance, args, statement, display)
            _execute_hook(request_hook, span, instance, *args, **kwargs)
            # Exceptions propagate through the span, which records them automatically.
            response = wrapped(*args, **kwargs)
            _execute_hook(response_hook, span, instance, response)
            return response

    return wrapper


def _traced_async_wrapper(
    tracer: Any,
    capture_statement: bool,
    request_hook: RequestHook | None,
    response_hook: ResponseHook | None,
):
    async def wrapper(wrapped: Any, instance: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        statement, display = _display_statement(args, capture_statement=capture_statement)
        with tracer.start_as_current_span(_span_name(args), kind=SpanKind.CLIENT) as span:
            _set_attributes(span, instance, args, statement, display)
            _execute_hook(request_hook, span, instance, *args, **kwargs)
            # Exceptions propagate through the span, which records them automatically.
            response = await wrapped(*args, **kwargs)
            _execute_hook(response_hook, span, instance, response)
            return response

    return wrapper
