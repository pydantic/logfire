from __future__ import annotations as _annotations

import warnings

from opentelemetry.trace import get_current_span
from opentelemetry.trace.span import Span

from logfire._internal.config import OPEN_LOGFIRE_SPANS_BY_ID
from logfire._internal.main import LogfireSpan, NoopSpan

__all__ = ('current_span', 'current_logfire_span')


class _BestEffortSpan:
    def __init__(self, span: Span):
        self.__span = span
        self.__noop_span = NoopSpan()

    def __getattr__(self, name: str):
        try:
            return getattr(self.__span, name)
        except AttributeError:
            value = getattr(self.__noop_span, name)
            # Emit the warning _after_ grabbing the value so we don't emit a warning if an AttributeError will be raised
            warnings.warn(
                'A logfire-specific attribute is being accessed on a non-logfire span,'
                ' the value is not meaningful and method calls will not do anything.',
                stacklevel=2,
            )
            return value


current_span = get_current_span


def current_logfire_span() -> LogfireSpan:
    """Return the LogfireSpan corresponding to the current otel span.

    If the current otel span was not created as a LogfireSpan, we warn and return
    something API-compatible which delegates to the otel span as much as possible.

    Note: If we eventually rework the SDK so `opentelemetry.trace.get_current_span` returns a `LogfireSpan`, we should
    make this an alias for `current_span` and deprecate this method. There are some good reasons to do that, but there
    are also some good reasons not to, such as reducing overhead in calls made by third-party instrumentations.
    """
    otel_span = get_current_span()
    span_context = otel_span.get_span_context()
    logfire_span = OPEN_LOGFIRE_SPANS_BY_ID.get((span_context.trace_id, span_context.span_id))
    if isinstance(logfire_span, LogfireSpan):
        return logfire_span
    return _BestEffortSpan(otel_span)  # type: ignore
