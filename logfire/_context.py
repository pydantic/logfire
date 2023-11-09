from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Sequence, cast

from opentelemetry.context import attach, detach, get_value, set_value

from ._constants import ATTRIBUTES_TAGS_KEY, CONTEXT_ATTRIBUTES_KEY


@contextmanager
def with_attributes(**attributes: Any) -> Iterator[None]:
    """Context manager that adds attributes to the current OTEL context.

    `LogFire.span` and `LogFire.log` will check this context for attributes to add to the span or log.
    """
    current = cast('dict[str, Any] | None', get_value(CONTEXT_ATTRIBUTES_KEY))
    new_context = set_value(CONTEXT_ATTRIBUTES_KEY, {**(current or {}), **attributes})
    previous_ctx = attach(new_context)
    try:
        yield
    finally:
        detach(previous_ctx)


def get_attributes_from_context() -> dict[str, Any] | None:
    """Get attributes from the current OTEL context."""
    return cast('dict[str, Any] | None', get_value(CONTEXT_ATTRIBUTES_KEY))


@contextmanager
def with_tags(*tags: Any) -> Iterator[None]:
    """Context manager that adds tags to the current OTEL context.

    `LogFire.span` and `LogFire.log` will check this context for tags to add to the span or log.
    """
    existing_tags = get_tags_from_context()
    new_tags = [*(existing_tags or ()), *tags]
    with with_attributes(**{ATTRIBUTES_TAGS_KEY: new_tags}):
        yield


def get_tags_from_context() -> Sequence[str] | None:
    """Get tags from the current OTEL context."""
    return (get_attributes_from_context() or {}).get(ATTRIBUTES_TAGS_KEY)
