from logfire._internal.constants import ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY
from logfire._internal.utils import truncate_string as truncate_string
from opentelemetry.trace import Span
from redis import Connection
from typing import Any
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
