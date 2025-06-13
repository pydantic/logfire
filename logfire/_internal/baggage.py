from __future__ import annotations

import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import baggage, context
from opentelemetry.sdk.trace import Span, SpanProcessor

from .json_encoder import logfire_json_dumps

__all__ = (
    'get_baggage',
    'set_baggage',
)


get_baggage = baggage.get_all
"""Get all OpenTelemetry baggage for the current context as a mapping of key/value pairs."""


@contextmanager
def set_baggage(**values: str) -> Iterator[None]:
    """Context manager that attaches key/value pairs as OpenTelemetry baggage to the current context.

    See the [Baggage documentation](https://logfire.pydantic.dev/docs/reference/advanced/baggage/) for more details.

    Note: this function should always be used in a `with` statement; if you try to open and close it manually you may
    run into surprises because OpenTelemetry Baggage is stored in the same contextvar as the current span.

    Args:
        values: The key/value pairs to attach to baggage. These should not be large or sensitive.

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
    for key, value in values.items():
        if not isinstance(value, str):  # type: ignore
            warnings.warn(
                f'Baggage value for key "{key}" is a {type(value).__name__}. Converting to string.', stacklevel=3
            )
            value = logfire_json_dumps(value)
        current_context = baggage.set_baggage(key, value, current_context)
    token = context.attach(current_context)
    try:
        yield
    finally:
        context.detach(token)


class NoForceFlushSpanProcessor(SpanProcessor):
    # See https://github.com/open-telemetry/opentelemetry-python/issues/4631.
    # This base class just means there's nothing to flush.
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class DirectBaggageAttributesSpanProcessor(NoForceFlushSpanProcessor):
    def on_start(self, span: Span, parent_context: context.Context | None = None) -> None:
        existing_attrs = span.attributes or {}
        span.set_attributes({k: v for k, v in _get_baggage_attrs(parent_context).items() if k not in existing_attrs})


def _get_baggage_attrs(parent_context: context.Context | None = None) -> dict[str, str]:
    """Get baggage as a dict of strings to set as attributes on a span.

    The values are converted to strings because that's what happens when baggage is propagated
    to different services, e.g. through HTTP headers.
    This way the value will be consistent between services.
    """
    return {k: _safe_str(v) for k, v in baggage.get_all(parent_context).items()}


def _safe_str(obj: Any) -> str:
    try:
        return str(obj)
    except Exception:
        try:
            return f'<{type(obj).__name__} object>'
        except Exception:  # pragma: no cover
            return '<unknown (str failed)>'
