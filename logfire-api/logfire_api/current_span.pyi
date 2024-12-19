from __future__ import annotations as _annotations

from opentelemetry.trace import get_current_span

from logfire import LogfireSpan

__all__ = ('current_span', 'current_logfire_span')


current_span = get_current_span


def current_logfire_span() -> LogfireSpan:
    """Return the LogfireSpan corresponding to the current otel span.

    If the current otel span was not created as a LogfireSpan, we warn and return
    something API-compatible which delegates to the otel span as much as possible.

    Note: If we eventually rework the SDK so `opentelemetry.trace.get_current_span` returns a `LogfireSpan`, we should
    make this an alias for `current_span` and deprecate this method. There are some good reasons to do that, but there
    are also some good reasons not to, such as reducing overhead in calls made by third-party instrumentations.
    """
    ...
