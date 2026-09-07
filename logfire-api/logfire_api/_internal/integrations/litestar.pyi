from .asgi import ASGIApp as ASGIApp, ASGIInstrumentKwargs as ASGIInstrumentKwargs, instrument_asgi as instrument_asgi
from litestar import Litestar
from logfire import Logfire as Logfire
from typing_extensions import Unpack

def instrument_litestar(logfire_instance: Logfire, app: Litestar, *, record_send_receive: bool = False, capture_headers: bool = False, **kwargs: Unpack[ASGIInstrumentKwargs]) -> ASGIApp:
    """Wrap a Litestar app with OpenTelemetry middleware configured for Logfire."""
