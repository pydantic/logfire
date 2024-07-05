from typing import Any

def instrument_sqlalchemy(**kwargs: Any):
    """Instrument the `sqlalchemy` module so that spans are automatically created for each query.

    See the `Logfire.instrument_sqlalchemy` method for details.
    """
