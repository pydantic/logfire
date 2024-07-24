from pymongo.monitoring import CommandFailedEvent, CommandStartedEvent, CommandSucceededEvent
from typing import Any
from typing_extensions import Protocol, TypedDict, Unpack

class RequestHook(Protocol):
    def __call__(self, span: Any, event: CommandStartedEvent) -> None: ...

class ResponseHook(Protocol):
    def __call__(self, span: Any, event: CommandSucceededEvent) -> None: ...

class FailedHook(Protocol):
    def __call__(self, span: Any, event: CommandFailedEvent) -> None: ...

class PymongoInstrumentKwargs(TypedDict, total=False):
    request_hook: RequestHook | None
    response_hook: ResponseHook | None
    failed_hook: FailedHook | None
    capture_statement: bool | None
    skip_dep_check: bool

def instrument_pymongo(**kwargs: Unpack[PymongoInstrumentKwargs]) -> None:
    """Instrument the `pymongo` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_pymongo` method for details.
    """
