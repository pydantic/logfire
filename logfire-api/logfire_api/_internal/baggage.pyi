from _typeshed import Incomplete
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = ['get_baggage', 'set_baggage']

get_baggage: Incomplete

@contextmanager
def set_baggage(**bag: str) -> Iterator[None]:
    '''Context manager that attaches key/value pairs as OpenTelemetry baggage to the current context.

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

    with set_baggage(my_id=\'123\'):
        # All spans opened inside this block will have baggage \'{"my_id": "123"}\'
        with set_baggage(my_session=\'abc\'):
            # All spans opened inside this block will have baggage \'{"my_id": "123", "my_session": "abc"}\'
            ...
    ```
    '''
