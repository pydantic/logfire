from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from mcp.client.session import ClientSession
from mcp.shared.session import BaseSession
from mcp.types import CallToolRequest, LoggingMessageNotification

from logfire._internal.utils import handle_internal_errors

if TYPE_CHECKING:
    from logfire import LevelName, Logfire


def instrument_mcp(logfire_instance: Logfire):
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='mcp')

    original_send_request = BaseSession.send_request  # type: ignore

    @functools.wraps(original_send_request)  # type: ignore
    async def send_request(self: Any, request: Any, *args: Any, **kwargs: Any):
        attributes: dict[str, Any] = {
            'request': request,
            # https://opentelemetry.io/docs/specs/semconv/rpc/json-rpc/
            'rpc.system': 'jsonrpc',
            'rpc.jsonrpc.version': '2.0',
        }
        span_name = 'MCP request'

        root = request.root
        # method should always exist, but it's had to verify because the request type is a RootModel
        # of a big union, instead of just using a base class with a method attribute.
        if method := getattr(root, 'method', None):  # pragma: no branch
            span_name += f': {method}'
            attributes['rpc.method'] = method
            if isinstance(root, CallToolRequest):
                span_name += f' {root.params.name}'

        with logfire_instance.span(span_name, **attributes) as span:
            result = await original_send_request(self, request, *args, **kwargs)
            span.set_attribute('response', result)
            return result

    BaseSession.send_request = send_request

    original_received_notification = ClientSession._received_notification  # type: ignore

    @functools.wraps(original_received_notification)
    async def _received_notification(self: Any, notification: Any, *args: Any, **kwargs: Any):
        with handle_internal_errors:
            if isinstance(notification.root, LoggingMessageNotification):  # pragma: no branch
                params = notification.root.params
                level: LevelName
                if params.level in ('critical', 'alert', 'emergency'):
                    level = 'fatal'
                else:
                    level = params.level
                span_name = 'MCP server log'
                if params.logger:
                    span_name += f' from {params.logger}'
                logfire_instance.log(level, span_name, attributes=dict(data=params.data))
        await original_received_notification(self, notification, *args, **kwargs)

    ClientSession._received_notification = _received_notification  # type: ignore
