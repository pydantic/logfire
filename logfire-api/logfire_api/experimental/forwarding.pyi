import logfire
from collections.abc import Mapping
from dataclasses import dataclass
from starlette.requests import Request
from starlette.responses import Response

__all__ = ['ForwardExportRequestResponse', 'forward_export_request', 'logfire_proxy']

@dataclass
class ForwardExportRequestResponse:
    """Response returned from a forwarded export request to Logfire."""
    status_code: int
    headers: Mapping[str, str]
    content: bytes

def forward_export_request(*, path: str, headers: Mapping[str, str], body: bytes, logfire_instance: logfire.Logfire | None = None, max_body_size: int = ...) -> ForwardExportRequestResponse:
    """Forward an export request to the Logfire API.

    See the Logfire.forward_export_request method for more details.
    """
async def logfire_proxy(request: Request, *, logfire_instance: logfire.Logfire | None = None, max_body_size: int = ...) -> Response:
    """A Starlette/FastAPI handler to proxy requests to Logfire.

    See the Logfire.forward_export_request_starlette method for more details.
    """
