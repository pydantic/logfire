from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.trace import Span
    from valkey import Valkey
    from valkey.asyncio import Valkey as AsyncValkey


@dataclass(frozen=True)
class RequestHookContext:
    """The span, client, and command arguments passed to a Valkey request hook."""

    span: Span
    instance: Valkey | AsyncValkey
    args: tuple[Any, ...]
    kwargs: Mapping[str, Any]


@dataclass(frozen=True)
class ResponseHookContext:
    """The span, client, and successful result passed to a Valkey response hook."""

    span: Span
    instance: Valkey | AsyncValkey
    response: Any


RequestHook = Callable[[RequestHookContext], None]
ResponseHook = Callable[[ResponseHookContext], None]
