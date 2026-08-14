from ..main import Logfire as Logfire, LogfireSpan as LogfireSpan
from ..utils import handle_internal_errors as handle_internal_errors
from _typeshed import Incomplete
from dataclasses import dataclass
from dramatiq import Broker
from dramatiq.broker import MessageProxy
from dramatiq.middleware import Middleware
from typing import Any

@dataclass
class _ActiveDelivery:
    proxy: MessageProxy
    span: LogfireSpan
    thread_id: int

class LogfireDramatiqMiddleware(Middleware):
    """Create producer and consumer spans for a Dramatiq broker."""
    logfire_instance: Incomplete
    broker: Incomplete
    def __init__(self, logfire_instance: Logfire, broker: Broker) -> None: ...
    def before_process_message(self, broker: Broker, message: MessageProxy) -> None: ...
    def after_process_message(self, broker: Broker, message: MessageProxy, *, result: Any = None, exception: BaseException | None = None) -> None: ...
    def after_skip_message(self, broker: Broker, message: MessageProxy) -> None: ...
    def after_nack(self, broker: Broker, message: MessageProxy) -> None: ...
    def after_worker_shutdown(self, broker: Broker, worker: Any) -> None: ...
    def close(self) -> None:
        """Finish deliveries left open by worker cancellation or shutdown."""
    def uninstrument(self) -> None:
        """Remove this middleware, restore the broker enqueue method, and finish active deliveries."""

def instrument_dramatiq(logfire_instance: Logfire, broker: Broker | None = None) -> LogfireDramatiqMiddleware:
    """Instrument a Dramatiq broker, returning the installed middleware."""
