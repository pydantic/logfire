import logfire
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ['ForwardExportRequestResponse', 'forward_export_request', 'logfire_proxy']

@dataclass
class ForwardExportRequestResponse:
    """Response returned from a forwarded export request to Logfire."""
    status_code: int
    headers: Mapping[str, str]
    content: bytes

def forward_export_request(*, path: str, headers: Mapping[str, str], body: bytes | None, logfire_instance: logfire.Logfire | None = None) -> ForwardExportRequestResponse:
    """Forward an export request to the Logfire API.

    Note: If the provided logfire instance is configured with multiple tokens,
    only the first token will be used for the proxy request.
    """
async def logfire_proxy(request: Any, *, logfire_instance: logfire.Logfire | None = None, max_body_size: int = ...) -> Any:
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

    Returns:
        A Starlette/FastAPI Response object.
    """
