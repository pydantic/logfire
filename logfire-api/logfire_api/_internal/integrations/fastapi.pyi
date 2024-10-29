from ..main import Logfire as Logfire, set_user_attributes_on_raw_span as set_user_attributes_on_raw_span
from ..stack_info import StackInfo as StackInfo, get_code_object_info as get_code_object_info
from ..utils import handle_internal_errors as handle_internal_errors, maybe_capture_server_headers as maybe_capture_server_headers
from .asgi import tweak_asgi_spans_tracer_provider as tweak_asgi_spans_tracer_provider
from _typeshed import Incomplete
from fastapi import FastAPI
from starlette.requests import Request
from starlette.websockets import WebSocket
from typing import Any, Awaitable, Callable, ContextManager, Iterable

def find_mounted_apps(app: FastAPI) -> list[FastAPI]:
    """Fetch all sub-apps mounted to a FastAPI app, including nested sub-apps."""
def instrument_fastapi(logfire_instance: Logfire, app: FastAPI, *, capture_headers: bool = False, request_attributes_mapper: Callable[[Request | WebSocket, dict[str, Any]], dict[str, Any] | None] | None = None, excluded_urls: str | Iterable[str] | None = None, record_send_receive: bool = False, **opentelemetry_kwargs: Any) -> ContextManager[None]:
    """Instrument a FastAPI app so that spans and logs are automatically created for each request.

    See `Logfire.instrument_fastapi` for more details.
    """
def patch_fastapi():
    """Globally monkeypatch fastapi functions and return a dictionary for recording instrumentation config per app."""

class FastAPIInstrumentation:
    logfire_instance: Incomplete
    request_attributes_mapper: Incomplete
    def __init__(self, logfire_instance: Logfire, request_attributes_mapper: Callable[[Request | WebSocket, dict[str, Any]], dict[str, Any] | None]) -> None: ...
    async def solve_dependencies(self, request: Request | WebSocket, original: Awaitable[Any]) -> Any: ...
    async def run_endpoint_function(self, original_run_endpoint_function: Any, request: Request, dependant: Any, values: dict[str, Any], **kwargs: Any) -> Any: ...

class _InstrumentedValues(dict):
    request: Request

LOGFIRE_SPAN_SCOPE_KEY: str
