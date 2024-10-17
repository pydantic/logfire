from logfire import Logfire as Logfire
from typing import Any

def instrument_aiohttp_client(logfire_instance: Logfire, **kwargs: Any):
    """Instrument the `aiohttp` module so that spans are automatically created for each client request.

    See the `Logfire.instrument_aiohttp_client` method for details.
    """
