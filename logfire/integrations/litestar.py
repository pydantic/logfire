"""Public types for the Litestar integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opentelemetry.trace import Span

ServerRequestHook = Callable[[Span, dict[str, Any]], None]
ClientRequestHook = Callable[[Span, dict[str, Any], dict[str, Any]], None]
ClientResponseHook = Callable[[Span, dict[str, Any], dict[str, Any]], None]
