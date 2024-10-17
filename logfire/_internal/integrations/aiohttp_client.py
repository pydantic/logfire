from typing import Any

from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

from logfire import Logfire


def instrument_aiohttp_client(logfire_instance: Logfire, **kwargs: Any):
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """
    AioHttpClientInstrumentor().instrument(  # type: ignore[reportUnknownMemberType]
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )
