from __future__ import annotations

import functools
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING, Any

from mcp.client.session import ClientSession
from mcp.server import Server
from mcp.shared.session import BaseSession, ReceiveRequestT, RequestResponder, SendResultT
from mcp.types import (
    CallToolRequest,
    ClientRequest,
    ClientResult,
    ErrorData,
    LoggingMessageNotification,
    ServerRequest,
    ServerResult,
)
from pydantic import TypeAdapter

from logfire._internal.utils import handle_internal_errors
from logfire.propagate import attach_context, get_context

if TYPE_CHECKING:
    from logfire import LevelName, Logfire


def instrument_mcp(logfire_instance: Logfire, propagate_otel_context: bool):
    logfire_instance = logfire_instance.with_settings(custom_scope_suffix='mcp')

    original_send_request = BaseSession.send_request  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @functools.wraps(original_send_request)  # pyright: ignore[reportUnknownArgumentType]
    async def send_request(self: Any, request: Any, *args: Any, **kwargs: Any):
        # Use getattr to handle both RootModel wrappers (e.g. ClientRequest) and bare request types.
        # fastmcp 3.x can send bare request types directly when OTel context propagation is active.
        root = getattr(request, 'root', request)
        attributes: dict[str, Any] = {
            'request': root,
            # https://opentelemetry.io/docs/specs/semconv/rpc/json-rpc/
            'rpc.system': 'jsonrpc',
            'rpc.jsonrpc.version': '2.0',
        }
        span_name = 'MCP request'

        # method should always exist, but it's had to verify because the request type is a RootModel
        # of a big union, instead of just using a base class with a method attribute.
        if method := getattr(root, 'method', None):  # pragma: no branch
            span_name += f': {method}'
            attributes['rpc.method'] = method
            if isinstance(root, CallToolRequest):
                span_name += f' {root.params.name}'

        with logfire_instance.span(span_name, **attributes) as span:
            _attach_context_to_request(root)
            result = await original_send_request(self, request, *args, **kwargs)
            span.set_attribute('response', result)
            return result

    BaseSession.send_request = send_request

    original_send_notification = BaseSession.send_notification  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]

    @functools.wraps(original_send_notification)  # pyright: ignore[reportUnknownArgumentType]
    async def send_notification(self: Any, notification: Any, *args: Any, **kwargs: Any):
        _attach_context_to_request(getattr(notification, 'root', notification))
        return await original_send_notification(self, notification, *args, **kwargs)

    BaseSession.send_notification = send_notification

    original_received_notification = ClientSession._received_notification  # pyright: ignore[reportPrivateUsage]

    @functools.wraps(original_received_notification)
    async def _received_notification(self: Any, notification: Any, *args: Any, **kwargs: Any):
        with handle_internal_errors:
            # Use getattr to handle both RootModel wrappers and bare notification types,
            # consistent with the pattern used in send_request, send_notification, and _received_request_client.
            root = getattr(notification, 'root', notification)
            if isinstance(root, LoggingMessageNotification):  # pragma: no branch
                params = root.params
                level: LevelName
                if params.level in ('critical', 'alert', 'emergency'):
                    level = 'fatal'
                else:
                    level = params.level
                span_name = 'MCP server log'
                if params.logger:
                    span_name += f' from {params.logger}'
                with _request_context(root):
                    logfire_instance.log(level, span_name, attributes=dict(data=params.data))
        await original_received_notification(self, notification, *args, **kwargs)

    ClientSession._received_notification = _received_notification  # pyright: ignore[reportPrivateUsage]

    original_handle_client_request = ClientSession._received_request  # pyright: ignore[reportPrivateUsage]

    @functools.wraps(original_handle_client_request)
    async def _received_request_client(self: Any, responder: RequestResponder[ServerRequest, ClientResult]) -> None:
        request = getattr(responder.request, 'root', responder.request)
        span_name = 'MCP client handle request'
        with _handle_request_with_context(request, responder, span_name):
            await original_handle_client_request(self, responder)

    ClientSession._received_request = _received_request_client  # pyright: ignore[reportPrivateUsage]

    original_handle_server_request = Server._handle_request  # pyright: ignore[reportPrivateUsage]

    @functools.wraps(original_handle_server_request)
    async def _handle_request(
        self: Any, message: RequestResponder[ClientRequest, ServerResult], request: Any, *args: Any, **kwargs: Any
    ) -> Any:
        span_name = 'MCP server handle request'
        with _handle_request_with_context(request, message, span_name):
            return await original_handle_server_request(self, message, request, *args, **kwargs)

    Server._handle_request = _handle_request  # pyright: ignore[reportPrivateUsage, reportAttributeAccessIssue]

    @contextmanager
    def _handle_request_with_context(
        request: Any, responder: RequestResponder[ReceiveRequestT, SendResultT], span_name: str
    ):
        with _request_context(request):
            if method := getattr(request, 'method', None):  # pragma: no branch
                span_name += f': {method}'
            with logfire_instance.span(span_name, request=request) as span:
                with handle_internal_errors:
                    original_respond = responder.respond

                    def _respond_with_logging(
                        response: SendResultT | ErrorData, *respond_args: Any, **respond_kwargs: Any
                    ) -> Any:
                        span.set_attribute('response', response)
                        return original_respond(response, *respond_args, **respond_kwargs)

                    responder.respond = _respond_with_logging

                yield

    @contextmanager
    def _request_context(request: Any):
        with ExitStack() as exit_stack:
            with handle_internal_errors:
                if (  # pragma: no branch
                    propagate_otel_context
                    and (params := getattr(request, 'params', None))
                    and (meta := getattr(params, 'meta', None))
                ):
                    exit_stack.enter_context(attach_context(meta.model_dump()))
            yield

    def _attach_context_to_request(root: Any):
        if not propagate_otel_context:  # pragma: no cover
            return
        carrier = get_context()
        if params := getattr(root, 'params', None):
            if meta := getattr(params, 'meta', None):
                if isinstance(meta, dict):
                    dumped_meta = meta  # pyright: ignore[reportUnknownVariableType]
                else:
                    dumped_meta = meta.model_dump()
            else:
                dumped_meta = {}
            # Prioritise existing values in meta over the context carrier.
            # RequestParams.Meta should allow basically anything, we're being extra careful here.
            params.meta = type(params).Meta.model_validate({**carrier, **dumped_meta})  # pyright: ignore[reportUnknownMemberType]
        else:
            root.params = _request_params_type_adapter(type(root)).validate_python({'_meta': carrier})  # pyright: ignore[reportUnknownArgumentType]


@functools.lru_cache
def _request_params_type_adapter(root_type: Any):
    params_type = root_type.model_fields['params'].annotation
    return TypeAdapter(params_type)
