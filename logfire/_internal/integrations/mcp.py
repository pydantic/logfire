from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from mcp.shared.session import BaseSession, SendRequestT
from mcp.types import CallToolRequest

if TYPE_CHECKING:
    from logfire import Logfire


def instrument_mcp(logfire_instance: Logfire):
    original = BaseSession.send_request  # type: ignore

    @functools.wraps(original)  # type: ignore
    async def send_request(self, request: SendRequestT, *args, **kwargs: Any):  # type: ignore
        attributes: dict[str, Any] = {
            'request': request,
            # https://opentelemetry.io/docs/specs/semconv/rpc/json-rpc/
            'rpc.system': 'jsonrpc',
            'rpc.jsonrpc.version': '2.0',
        }
        span_name = 'MCP request'

        root = request.root
        if method := getattr(root, 'method', None):
            span_name += f': {method}'
            attributes['rpc.method'] = method
            if isinstance(root, CallToolRequest):
                span_name += f' {root.params.name}'

        with logfire_instance.span(span_name, **attributes) as span:
            result = await original(self, request, *args, **kwargs)  # type: ignore
            span.set_attribute('response', result)
            return result  # type: ignore

    BaseSession.send_request = send_request
