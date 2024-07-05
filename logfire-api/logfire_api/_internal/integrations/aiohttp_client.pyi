from typing import Any

def instrument_aiohttp_client(**kwargs: Any):
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """
