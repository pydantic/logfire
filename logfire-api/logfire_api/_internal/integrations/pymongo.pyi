from typing import Any

def instrument_pymongo(**kwargs: Any):
    """Instrument the `pymongo` module so that spans are automatically created for each operation.

    See the `Logfire.instrument_pymongo` method for details.
    """
