from typing import Any, Optional

from opentelemetry.instrumentation.requests import RequestsInstrumentor

from logfire import Logfire


def instrument_requests(logfire_instance: Logfire, excluded_urls: Optional[str] = None, **kwargs: Any):
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
    RequestsInstrumentor().instrument(  # type: ignore[reportUnknownMemberType]
        excluded_urls=excluded_urls,
        **{
            'tracer_provider': logfire_instance.config.get_tracer_provider(),
            'meter_provider': logfire_instance.config.get_meter_provider(),
            **kwargs,
        },
    )
