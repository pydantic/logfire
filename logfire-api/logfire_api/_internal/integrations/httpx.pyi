import httpx
from logfire import Logfire as Logfire
from opentelemetry.instrumentation.httpx import AsyncRequestHook, AsyncResponseHook, RequestHook, ResponseHook
from typing import TypedDict, Unpack

class HTTPXInstrumentKwargs(TypedDict, total=False):
    request_hook: RequestHook
    response_hook: ResponseHook
    async_request_hook: AsyncRequestHook
    async_response_hook: AsyncResponseHook
    skip_dep_check: bool

def instrument_httpx(logfire_instance: Logfire, client: httpx.Client | httpx.AsyncClient | None, **kwargs: Unpack[HTTPXInstrumentKwargs]) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
