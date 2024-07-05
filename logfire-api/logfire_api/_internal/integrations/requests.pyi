from typing import Any

def instrument_requests(excluded_urls: str | None = None, **kwargs: Any):
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
