"""Logfire processor for structlog."""

from structlog.types import EventDict, WrappedLogger

import logfire
from logfire.integrations.logging import RESERVED_ATTRS

_STRUCTLOG_CALL_OFFSET = 5
"""The offset to the stack to find the caller of the structlog event."""

_STRIP_FROM_EVENT = ('level', 'event', 'timestamp')
"""Attributes to strip from the event before sending to Logfire."""


class LogfireProcessor:
    """Logfire processor for structlog."""

    def __init__(self, *, console_log: bool = False) -> None:
        self.console_log = console_log

    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> EventDict:
        """A middleware to process structlog event, and send it to **Logfire**."""
        attributes = {k: v for k, v in event_dict.items() if k not in RESERVED_ATTRS + _STRIP_FROM_EVENT}
        level = event_dict.get('level', 'info').lower()
        # NOTE: An event can be `None` in structlog. We may want to create a default msg in those cases.
        msg_template = event_dict.get('event') or 'structlog event'
        logfire.log(
            level=level,  # type: ignore
            msg_template=msg_template,
            attributes=attributes,
            stack_offset=_STRUCTLOG_CALL_OFFSET,
            console_log=self.console_log,
            custom_scope_suffix='structlog',
        )
        return event_dict
