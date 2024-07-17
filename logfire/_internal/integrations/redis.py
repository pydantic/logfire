from __future__ import annotations

from typing import TYPE_CHECKING, Any

from opentelemetry.instrumentation.redis import RedisInstrumentor

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


def instrument_redis(**kwargs: Unpack[RedisInstrumentKwargs]) -> None:
    """Instrument the `redis` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_redis` method for details.
    """
    RedisInstrumentor().instrument(**kwargs)  # type: ignore[reportUnknownMemberType]
