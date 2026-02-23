from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urljoin

import logfire
from logfire.version import VERSION

if TYPE_CHECKING:
    from logfire._internal.config import LogfireConfig

__all__ = ('ForwardExportRequestResponse', 'forward_export_request', 'logfire_proxy')


@dataclass
class ForwardExportRequestResponse:
    """Response returned from a forwarded export request to Logfire."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes


def forward_export_request(
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes | None,
    *,
    config: LogfireConfig | None = None,
) -> ForwardExportRequestResponse:
    """Forward an export request to the Logfire API."""
    import requests

    if method.upper() != 'POST':
        return ForwardExportRequestResponse(
            status_code=405,
            headers={'Content-Type': 'text/plain'},
            content=b'Method Not Allowed',
        )

    if config is None:
        config = logfire.DEFAULT_LOGFIRE_INSTANCE.config

    if not path.startswith('/'):
        path = '/' + path

    # Security: Normalize path to prevent directory traversal attacks (e.g. /v1/traces/../secret)
    # We unquote first to handle percent-encoded traversals (e.g. %2e%2e) that might bypass normalization
    path = posixpath.normpath(unquote(path))

    allowed_prefixes = ('/v1/traces', '/v1/logs', '/v1/metrics')
    if not any(path == prefix or path.startswith(prefix + '/') for prefix in allowed_prefixes):
        return ForwardExportRequestResponse(
            status_code=400,
            headers={'Content-Type': 'text/plain'},
            content=b'Invalid path: must start with /v1/traces, /v1/logs, or /v1/metrics',
        )

    token = config.token
    if isinstance(token, list):
        # Proxying only supports the first configured project/token
        token = token[0] if token else None

    if not token:
        return ForwardExportRequestResponse(
            status_code=500,
            headers={'Content-Type': 'text/plain'},
            content=b'Logfire is not configured with a token',
        )

    base_url = config.advanced.generate_base_url(token)
    url = urljoin(base_url, path)

    headers_to_remove = {
        'host',
        'content-length',
        'authorization',
        'connection',
        'transfer-encoding',
        'keep-alive',
        'proxy-authenticate',
        'proxy-authorization',
        'te',
        'trailer',
        'upgrade',
        'cookie',
    }

    new_headers = {k: v for k, v in headers.items() if k.lower() not in headers_to_remove}

    # Case-insensitive lookup to preserve original User-Agent
    user_agent_key = next((k for k in new_headers if k.lower() == 'user-agent'), None)
    if user_agent_key:
        original_ua = new_headers.pop(user_agent_key)
        new_headers['User-Agent'] = f'logfire-proxy/{VERSION} {original_ua}'
    else:
        new_headers['User-Agent'] = f'logfire-proxy/{VERSION}'

    new_headers['Authorization'] = token

    try:
        # Wrap with suppress_instrumentation so we don't infinitely trace proxy telemetry
        with logfire.suppress_instrumentation():
            response = requests.request(
                method=method,
                url=url,
                headers=new_headers,
                data=body,
                stream=False,
                timeout=30,
            )
    except requests.RequestException:
        # Security: Return a generic error to avoid leaking internal URL/configuration details
        return ForwardExportRequestResponse(
            status_code=502,
            headers={'Content-Type': 'text/plain'},
            content=b'Upstream service error',
        )

    response_headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding', 'connection', 'set-cookie')
    }

    return ForwardExportRequestResponse(
        status_code=response.status_code,
        headers=response_headers,
        content=response.content,
    )


async def logfire_proxy(request: Any, *, max_body_size: int = 50 * 1024 * 1024) -> Any:
    """A Starlette/FastAPI handler to proxy requests to Logfire.

    This is useful for proxying requests from a browser to Logfire,
    to avoid exposing your write token in the browser.

    **Security Note**: This endpoint is unauthenticated unless you protect it.
    Any client capable of reaching this endpoint can send telemetry data to your Logfire project.
    In production, ensure you have appropriate protections in place (e.g. CORS policies,
    rate limiting, or upstream authentication/dependency injection).

    Args:
        request: The Starlette/FastAPI Request object.
        max_body_size: The maximum allowed request body size in bytes. Defaults to 50MB.

    Returns:
        A Starlette/FastAPI Response object.
    """
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response

    if request.method.upper() != 'POST':
        return Response(status_code=405, content='Method Not Allowed')

    # DoS Prevention: Check Content-Length before reading body
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > max_body_size:
                return Response(status_code=413, content='Payload too large')
        except ValueError:
            return Response(status_code=400, content='Invalid Content-Length header')

    body = await request.body()
    if len(body) > max_body_size:
        return Response(status_code=413, content='Payload too large')

    path = request.path_params.get('path')
    if not path:
        return Response(status_code=400, content='Missing path parameter. Use {path:path} in the route definition.')

    # Performance: Run synchronous requests call in a thread pool to avoid blocking the event loop
    response = await run_in_threadpool(
        forward_export_request,
        method=request.method,
        path=path,
        headers=request.headers,
        body=body,
    )
    return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))
