from typing import Any
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor
    except ImportError:  # pragma: no cover
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
