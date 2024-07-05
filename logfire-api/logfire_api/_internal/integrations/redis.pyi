from typing import Any

def instrument_redis(**kwargs: Any):
    """Instrument the `redis` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_redis` method for details.
    """
