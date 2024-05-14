from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, NamedTuple

if TYPE_CHECKING:
    from typing_extensions import LiteralString


__all__ = ('EndpointConfig',)


class EndpointConfig(NamedTuple):
    """The configuration for the endpoint of a provider based on request url."""

    message_template: LiteralString
    span_data: dict[str, Any]
    content_from_stream: Callable[[Any], str | None] | None
