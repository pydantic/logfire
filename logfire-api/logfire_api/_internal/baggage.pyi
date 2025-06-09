from _typeshed import Incomplete
from collections.abc import Iterator
from contextlib import contextmanager

__all__ = ['get_baggage', 'set_baggage']

get_baggage: Incomplete

@contextmanager
def set_baggage(**bag: str) -> Iterator[None]:
    '''Context manager that attaches key/value pairs as OpenTelemetry baggage to the current context.

    Note that all values in `bag` must be strings, as OpenTelemetry baggage only supports string values.

    This is used for propagating arbitrary context (like user ids, task ids, etc) down to all spans opened under this scope.

    Note that baggage is not _automatically_ converted into attributes on descendant spans, but this is a common usage
    pattern. If you want baggage to be converted into attributes, use `logfire.configure(add_baggage_to_attributes=True)`.

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
