from __future__ import annotations

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from ...version import VERSION

if TYPE_CHECKING:
    from ..config import LogfireConfig


@dataclass
class ForwardRequestResponse:
    status_code: int
    headers: Mapping[str, str]
    content: bytes


def forward_request(
    config: LogfireConfig,
    method: str,
    path: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> ForwardRequestResponse:
    import requests

    if not path.startswith('/'):
        path = '/' + path

    # Security: Normalize path to prevent directory traversal attacks (e.g. /v1/traces/../secret)
    path = posixpath.normpath(path)

    allowed_prefixes = ('/v1/traces', '/v1/logs', '/v1/metrics')
    if not any(path.startswith(prefix) for prefix in allowed_prefixes):
        return ForwardRequestResponse(
            status_code=400,
            headers={'Content-Type': 'text/plain'},
            content=b'Invalid path: must start with /v1/traces, /v1/logs, or /v1/metrics',
        )

    token = config.token
    if isinstance(token, list):
        token = token[0] if token else None

    if not token:
        return ForwardRequestResponse(
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
        'trailers',
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

    new_headers['Authorization'] = f'Bearer {token}'

    try:
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
        return ForwardRequestResponse(
            status_code=502,
            headers={'Content-Type': 'text/plain'},
            content=b'Upstream service error',
        )

    response_headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in ('content-encoding', 'content-length', 'transfer-encoding', 'connection')
    }

    return ForwardRequestResponse(
        status_code=response.status_code,
        headers=response_headers,
        content=response.content,
    )
