from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from mcp.shared.session import (
    BaseSession,
    SendRequestT,
)

if TYPE_CHECKING:
    from logfire import Logfire


def instrument_mcp(logfire_instance: Logfire):
    original = BaseSession.send_request  # type: ignore

    @functools.wraps(original)  # type: ignore
    async def send_request(self, request: SendRequestT, *args, **kwargs: Any):  # type: ignore
        with logfire_instance.span('MCP request', request=request) as span:
            result = await original(self, request, *args, **kwargs)  # type: ignore
            span.set_attribute('response', result)
            return result  # type: ignore

    BaseSession.send_request = send_request
