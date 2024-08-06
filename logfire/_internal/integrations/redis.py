from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation.redis import RedisInstrumentor

from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY
from logfire._internal.utils import truncate_string

if TYPE_CHECKING:
    from opentelemetry.trace import Span
    from redis import Connection
    from typing_extensions import Protocol, TypedDict, Unpack

    class RequestHook(Protocol):
        def __call__(self, span: Span, instance: Connection, *args: Any, **kwargs: Any) -> None: ...

    class ResponseHook(Protocol):
        def __call__(self, span: Span, instance: Connection, response: Any) -> None: ...

    class RedisInstrumentKwargs(TypedDict, total=False):
        request_hook: RequestHook | None
        response_hook: ResponseHook | None
        skip_dep_check: bool


def instrument_redis(capture_statement: bool = False, **kwargs: Unpack[RedisInstrumentKwargs]) -> None:
    """Instrument the `redis` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_redis` method for details.

    Args:
        capture_statement: Whether to capture the statement being executed. Defaults to False.
        **kwargs: Additional keyword arguments to pass to the `RedisInstrumentor.instrument` method.
    """
    request_hook = kwargs.pop('request_hook', None)
    if capture_statement:
        request_hook = _capture_statement_hook(request_hook)

    RedisInstrumentor().instrument(request_hook=request_hook, **kwargs)  # type: ignore[reportUnknownMemberType]


def _capture_statement_hook(request_hook: RequestHook | None = None) -> RequestHook:
    truncate_value = functools.partial(truncate_string, max_length=20, middle='...')

    def _capture_statement(
        span: Span, instance: Connection, command: tuple[object, ...], *args: Any, **kwargs: Any
    ) -> None:
        str_command = list(map(str, command))
        span.set_attribute('db.statement', ' '.join(str_command))
        span.set_attribute(ATTRIBUTES_MESSAGE_KEY, ' '.join(map(truncate_value, str_command)))
        if request_hook is not None:
            request_hook(span, instance, command, *args, **kwargs)

    return _capture_statement
