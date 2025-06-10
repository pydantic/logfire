from typing import Any
import warnings

warnings.filterwarnings(
    "ignore",
    message="Inheritance class _InstrumentedApplication from web.Application is discouraged",
    category=DeprecationWarning,
)
try:
    from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor
except ImportError:
    raise RuntimeError(
        "`logfire.instrument_aiohttp_server()` requires the `opentelemetry-instrumentation-aiohttp-server` package.\n"
        "You can install this with:\n"
        "    pip install 'logfire[aiohttp]'"
    )
from logfire import Logfire


def instrument_aiohttp_server(logfire_instance: Logfire, **kwargs: Any):
    """Instrument the `aiohttp` module so that spans are automatically created for each server request.

    See the `Logfire.instrument_aiohttp_server` method for details.
    """
    AioHttpServerInstrumentor().instrument(**kwargs)
