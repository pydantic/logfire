from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import unquote, urljoin

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse

import logfire
from logfire._internal.exporters.otlp import DiskRetryer
from logfire.version import VERSION

__all__ = ('DEFAULT_FORWARD_TIMEOUT', 'ForwardExportRequestResponse', 'forward_export_request', 'logfire_proxy')

DEFAULT_FORWARD_TIMEOUT = 5.0
OTLP_PROTOBUF_HEADERS = {'Content-Type': 'application/x-protobuf'}

_forwarding_retryer: DiskRetryer | None = None
_FORWARDING_RETRYER_LOCK = Lock()


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
    body: bytes | None,
    logfire_instance: logfire.Logfire | None = None,
    timeout: float = DEFAULT_FORWARD_TIMEOUT,
) -> ForwardExportRequestResponse:
    """Queue an export request to be forwarded to the Logfire API.

    The request body is written to a local disk retry queue and forwarded by a background thread.
    This keeps Logfire network failures out of the caller's request path.

    Note: If the provided logfire instance is configured with multiple tokens,
    only the first token will be used for the proxy request.
    """
    if logfire_instance is None:
        logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE

    config = logfire_instance.config

    if not path.startswith('/'):
        path = '/' + path

    # Security: Normalize path to prevent directory traversal attacks (e.g. /v1/traces/../secret)
    # We unquote first to handle percent-encoded traversals (e.g. %2e%2e) that might bypass normalization
    path = posixpath.normpath(unquote(path))

    if path not in ('/v1/traces', '/v1/logs', '/v1/metrics'):
        return ForwardExportRequestResponse(
            status_code=400,
            headers={'Content-Type': 'text/plain'},
            content=b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics',
        )

    token = config.token
    if isinstance(token, list):
        # Proxying only supports the first configured project/token
        token = token[0] if token else None

    if not token:
        return ForwardExportRequestResponse(
            status_code=403,
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
        'cf-connecting-ip',
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

    data = body or b''
    if not data:
        return _otlp_success_response(path)

    accepted = _get_forwarding_retryer().add_task(
        data,
        {
            'url': url,
            'headers': new_headers,
            'stream': False,
            'timeout': timeout,
        },
    )
    if not accepted:
        return _otlp_partial_success_response(
            path,
            'Logfire proxy retry queue is full or unavailable; telemetry was dropped.',
        )

    return _otlp_success_response(path)


async def logfire_proxy(
    request: Any,
    *,
    logfire_instance: logfire.Logfire | None = None,
    max_body_size: int = 50 * 1024 * 1024,
    timeout: float = DEFAULT_FORWARD_TIMEOUT,
) -> Any:
    """A Starlette/FastAPI handler to proxy requests to Logfire.

    This is useful for proxying requests from a browser to Logfire,
    to avoid exposing your write token in the browser.

    Note: If the provided logfire instance is configured with multiple tokens,
    only the first token will be used for the proxy request.

    **Security Note**: This endpoint is unauthenticated unless you protect it.
    Any client capable of reaching this endpoint can send telemetry data to your Logfire project.
    In production, ensure you have appropriate protections in place (e.g. CORS policies,
    rate limiting, or upstream authentication/dependency injection).

    Args:
        request: The Starlette/FastAPI Request object.
        logfire_instance: The Logfire instance to use. If not provided, the default instance is used.
        max_body_size: The maximum allowed request body size in bytes. Defaults to 50MB.
        timeout: The timeout in seconds for each background forwarding attempt. Defaults to 5 seconds.

    Returns:
        A Starlette/FastAPI Response object.
    """
    from starlette.concurrency import run_in_threadpool
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

    # Security: Read the body in chunks so a single oversized request can be rejected
    # in cases where the Content-Length header is omitted or spoofed.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_body_size:
            return Response(status_code=413, content='Payload too large')

    path = request.path_params.get('path')
    if not path:
        return Response(status_code=400, content='Missing path parameter. Use {path:path} in the route definition.')

    # The request path only does local queue I/O. Network forwarding happens in the retryer's background thread.
    response = await run_in_threadpool(
        forward_export_request,
        path=path,
        headers=request.headers,
        body=bytes(body),
        logfire_instance=logfire_instance,
        timeout=timeout,
    )
    return Response(content=response.content, status_code=response.status_code, headers=dict(response.headers))


def _get_forwarding_retryer() -> DiskRetryer:
    global _forwarding_retryer
    if _forwarding_retryer is None or _forwarding_retryer.closed:
        with _FORWARDING_RETRYER_LOCK:
            if _forwarding_retryer is None or _forwarding_retryer.closed:
                _forwarding_retryer = DiskRetryer({}, initial_delay=0, success_delay=0)
    return _forwarding_retryer


def _otlp_success_response(path: str) -> ForwardExportRequestResponse:
    if path == '/v1/traces':
        content = ExportTraceServiceResponse().SerializeToString()
    elif path == '/v1/logs':
        content = ExportLogsServiceResponse().SerializeToString()
    else:
        content = ExportMetricsServiceResponse().SerializeToString()

    return ForwardExportRequestResponse(
        status_code=200,
        headers=OTLP_PROTOBUF_HEADERS,
        content=content,
    )


def _otlp_partial_success_response(path: str, error_message: str) -> ForwardExportRequestResponse:
    if path == '/v1/traces':
        response = ExportTraceServiceResponse()
    elif path == '/v1/logs':
        response = ExportLogsServiceResponse()
    else:
        response = ExportMetricsServiceResponse()
    response.partial_success.error_message = error_message
    return ForwardExportRequestResponse(
        status_code=200,
        headers=OTLP_PROTOBUF_HEADERS,
        content=response.SerializeToString(),
    )
