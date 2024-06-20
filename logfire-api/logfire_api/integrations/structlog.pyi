from .._internal.constants import ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY
from _typeshed import Incomplete
from structlog.types import EventDict as EventDict, WrappedLogger as WrappedLogger

RESERVED_ATTRS: Incomplete

class LogfireProcessor:
    """Logfire processor for structlog."""
    console_log: Incomplete
    def __init__(self, *, console_log: bool = False) -> None: ...
    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> EventDict:
        """A middleware to process structlog event, and send it to **Logfire**."""
