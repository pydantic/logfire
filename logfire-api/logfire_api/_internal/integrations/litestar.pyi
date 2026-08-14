from logfire import Logfire as Logfire
from logfire._internal.integrations.asgi import tweak_asgi_spans_tracer_provider as tweak_asgi_spans_tracer_provider
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from logfire.integrations.litestar import LitestarInstrumentKwargs as LitestarInstrumentKwargs
from opentelemetry.instrumentation.asgi.types import ClientRequestHook, ClientResponseHook, ServerRequestHook
from typing import Any
from typing_extensions import Unpack

def instrument_litestar(logfire_instance: Logfire, *, record_send_receive: bool = False, capture_headers: bool = False, server_request_hook: ServerRequestHook | None = None, client_request_hook: ClientRequestHook | None = None, client_response_hook: ClientResponseHook | None = None, **kwargs: Unpack[LitestarInstrumentKwargs]) -> Any:
    """Return Litestar's OpenTelemetry plugin configured for Logfire."""
