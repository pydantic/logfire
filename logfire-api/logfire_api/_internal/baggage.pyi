from collections.abc import Iterator, Mapping
from contextlib import contextmanager

__all__ = ['get_baggage', 'update_baggage']

def get_baggage() -> Mapping[str, object] | None:
    """Get all OpenTelemetry baggage for the current context as a mapping of key/value pairs."""
@contextmanager
def update_baggage(bag: dict[str, object]) -> Iterator[None]:
    '''Context manager that attaches key/value pairs as OpenTelemetry baggage to the current context.

    This is used for propagating arbitrary context (like user ids, task ids, etc) down to all spans opened under this scope.

    Note that baggage is not _automatically_ converted into attributes on descendant spans, but this is a common usage
    pattern. If you want baggage to be converted into attributes, use `logfire.configure(add_baggage_to_attributes=True)`.

    Args:
        bag: The key/value pairs to attach to baggage.

    Example usage:

    ```python
    from logfire import update_baggage

    with update_baggage({\'my_id\': \'123\'}):
        # All spans opened inside this block will have baggage \'{"my_id": "123"}\'
        with update_baggage({\'my_session\': \'abc\'}):
            # All spans opened inside this block will have baggage \'{"my_id": "123", "my_session": "abc"}\'
            ...
    ```
    '''
