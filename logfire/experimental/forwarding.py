from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import logfire
from logfire._internal.forwarding import (
    OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
    ForwardingErrorResponse,
    build_forwarding_request,
    build_partial_success_response,
    build_success_response,
)

__all__ = ('ForwardExportRequestResponse', 'forward_export_request', 'logfire_proxy')


@dataclass
class ForwardExportRequestResponse:
    """Response returned from a forwarded export request to Logfire."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


def forward_export_request(
    *,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    logfire_instance: logfire.Logfire | None = None,
    max_body_size: int = OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
) -> ForwardExportRequestResponse:
    """Forward an export request to the Logfire API.

    Note: If the provided logfire instance is configured with multiple Logfire destinations,
    the request is admitted for forwarding to all of them.
    """
    if logfire_instance is None:
        logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    config = logfire_instance.config

    forwarding_request = build_forwarding_request(
        path=path,
        headers=headers,
        body=body,
        max_body_size=max_body_size,
    )
    if isinstance(forwarding_request, ForwardingErrorResponse):
        return ForwardExportRequestResponse(
            status_code=forwarding_request.status_code,
            headers={'Content-Type': 'text/plain'},
            content=forwarding_request.content,
        )

    manager = config._otlp_forwarding  # pyright: ignore[reportPrivateUsage]
    if not manager.has_destinations():
        return ForwardExportRequestResponse(
            status_code=403,
            headers={'Content-Type': 'text/plain'},
            content=b'Logfire is not configured with an active forwarding destination',
        )

    admission_result = manager.submit(forwarding_request)
    if admission_result.response == 'success':
        return build_success_response(forwarding_request)
    return build_partial_success_response(forwarding_request, message=admission_result.message or '')


async def logfire_proxy(
    request: Any,
    *,
    logfire_instance: logfire.Logfire | None = None,
    max_body_size: int = 50 * 1024 * 1024,
) -> Any:
    """A Starlette/FastAPI handler to proxy requests to Logfire.

    This is useful for proxying requests from a browser to Logfire,
    to avoid exposing your write token in the browser.

    Note: If the provided logfire instance is configured with multiple Logfire destinations,
    accepted requests are admitted for forwarding to all of them.

    **Security Note**: This endpoint is unauthenticated unless you protect it.
    Any client capable of reaching this endpoint can send telemetry data to your Logfire project.
    In production, ensure you have appropriate protections in place (e.g. CORS policies,
    rate limiting, or upstream authentication/dependency injection).

    Args:
        request: The Starlette/FastAPI Request object.
        logfire_instance: The Logfire instance to use. If not provided, the default instance is used.
        max_body_size: The maximum allowed request body size in bytes. Defaults to 50MB.

    Returns:
        A Starlette/FastAPI Response object.
    """
    from starlette.responses import Response

    if request.method.upper() != 'POST':
        return Response(status_code=405, content='Method Not Allowed')

    # Optimization: Fast-fail overtly large honest requests by checking Content-Length.
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > max_body_size:
                return Response(status_code=413, content='Payload too large')
        except ValueError:
            return Response(status_code=400, content='Invalid Content-Length header')

    # Security: Read the body in chunks to prevent memory exhaustion DoS attacks
    # in cases where the Content-Length header is omitted or spoofed.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_body_size:
            return Response(status_code=413, content='Payload too large')

    path = request.path_params.get('path')
    if not path:
        return Response(status_code=400, content='Missing path parameter. Use {path:path} in the route definition.')

    response = forward_export_request(
        path=path,
        headers=request.headers,
        body=bytes(body),
        logfire_instance=logfire_instance,
        max_body_size=max_body_size,
    )
    return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))
