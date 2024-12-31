from typing import Callable

from opentelemetry.trace import Span
from pymongo.monitoring import CommandFailedEvent, CommandStartedEvent, CommandSucceededEvent

RequestHook = Callable[[Span, CommandStartedEvent], None]
"""A hook that is called when a command is started."""

ResponseHook = Callable[[Span, CommandSucceededEvent], None]
"""A hook that is called when a command is succeeded."""

FailedHook = Callable[[Span, CommandFailedEvent], None]
"""A hook that is called when a command is failed."""
