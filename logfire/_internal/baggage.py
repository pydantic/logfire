from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry import baggage, context
from opentelemetry.sdk.trace import Span, SpanProcessor

__all__ = (
    'get_baggage',
    'set_baggage',
)


get_baggage = baggage.get_all
"""Get all OpenTelemetry baggage for the current context as a mapping of key/value pairs."""


@contextmanager
def set_baggage(**bag: str) -> Iterator[None]:
    """Context manager that attaches key/value pairs as OpenTelemetry baggage to the current context.

    All values in `bag` must be strings, as OpenTelemetry baggage only supports string values.

    OpenTelemetry baggage is a way to propagate metadata across service boundaries in a distributed system, and is
    included in headers of outgoing requests for which context propagation is configured.
    This is intended to be used to propagate arbitrary context (like user ids, task ids, etc.) down to all nested spans.

    Baggage is not _automatically_ converted into attributes on descendant spans, but this is a common usage pattern.
    If you want baggage to be converted into attributes, use `logfire.configure(add_baggage_to_attributes=True)`.

    Note: this function should always be used as a context manager; if you try to open and close it manually you may
    run into surprises because OpenTelemetry Baggage is stored in the same contextvar as the current span.

    Args:
        bag: The key/value pairs to attach to baggage.

    Example usage:

    ```python
    from logfire import set_baggage

    with set_baggage(my_id='123'):
        # All spans opened inside this block will have baggage '{"my_id": "123"}'
        with set_baggage(my_session='abc'):
            # All spans opened inside this block will have baggage '{"my_id": "123", "my_session": "abc"}'
            ...
    ```
    """
    current_context = context.get_current()
    for key, value in bag.items():
        current_context = baggage.set_baggage(key, value, current_context)
    token = context.attach(current_context)
    try:
        yield
    finally:
        context.detach(token)


class NoForceFlushSpanProcessor(SpanProcessor):
    # The default SpanProcessor.force_flush returns None,
    # which gets interpreted as False by the OTel SDK, meaning that the spans did not export successfully.
    # Then SynchronousMultiSpanProcessor stops looping through processors and doesn't force flush the next one.
    # OTel is dumb.
    # This base class just means there's nothing to flush.
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class DirectBaggageAttributesSpanProcessor(NoForceFlushSpanProcessor):
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        span.set_attributes(baggage.get_all(parent_context))  # type: ignore


class JsonBaggageAttributesSpanProcessor(NoForceFlushSpanProcessor):
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        attrs = baggage.get_all(parent_context)
        if attrs:
            span.set_attribute('logfire.baggage', json.dumps(dict(attrs)))
