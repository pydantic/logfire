from _typeshed import Incomplete
from typing import TypedDict, Unpack

RequestHook: Incomplete
ResponseHook: Incomplete
AsyncRequestHook: Incomplete
AsyncResponseHook: Incomplete

class HTTPXInstrumentKwargs(TypedDict, total=False):
    request_hook: RequestHook
    response_hook: ResponseHook
    async_request_hook: AsyncRequestHook
    async_response_hook: AsyncResponseHook
    skip_dep_check: bool

def instrument_httpx(**kwargs: Unpack[HTTPXInstrumentKwargs]) -> None:
    """Instrument the `httpx` module so that spans are automatically created for each request.

    See the `Logfire.instrument_httpx` method for details.
    """
