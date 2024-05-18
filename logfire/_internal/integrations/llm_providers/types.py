from __future__ import annotations

from typing import Any, Callable, NamedTuple

from typing_extensions import LiteralString


class EndpointConfig(NamedTuple):
    """The configuration for the endpoint of a provider based on request url."""

    message_template: LiteralString
    span_data: dict[str, Any]
    content_from_stream: Callable[[Any], str | None] | None
