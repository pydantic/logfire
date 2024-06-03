"""Logfire processor for structlog."""

from __future__ import annotations

from typing import TYPE_CHECKING

import logfire

from .._internal.constants import ATTRIBUTES_MESSAGE_KEY
from .logging import RESERVED_ATTRS as LOGGING_RESERVED_ATTRS

# This file is currently imported eagerly from __init__.py, so it shouldn't import structlog directly
# since that's not a required dependency.
if TYPE_CHECKING:
    from structlog.types import EventDict, WrappedLogger

RESERVED_ATTRS = LOGGING_RESERVED_ATTRS | {'level', 'event', 'timestamp'}
"""Attributes to strip from the event before sending to Logfire."""


class LogfireProcessor:
    """Logfire processor for structlog."""

    def __init__(self, *, console_log: bool = False) -> None:
        self.console_log = console_log

    def __call__(self, logger: WrappedLogger, name: str, event_dict: EventDict) -> EventDict:
        """A middleware to process structlog event, and send it to **Logfire**."""
        attributes = {k: v for k, v in event_dict.items() if k not in RESERVED_ATTRS}
        level = event_dict.get('level', 'info').lower()
        # NOTE: An event can be `None` in structlog. We may want to create a default msg in those cases.
        attributes[ATTRIBUTES_MESSAGE_KEY] = message = event_dict.get('event') or 'structlog event'
        logfire.log(
            level=level,  # type: ignore
            msg_template=message,
            attributes=attributes,
            console_log=self.console_log,
            custom_scope_suffix='structlog',
        )
        return event_dict
