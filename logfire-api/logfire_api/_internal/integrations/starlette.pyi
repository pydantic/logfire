from starlette.applications import Starlette as Starlette
from typing import Any

def instrument_starlette(app: Starlette, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_starlette` method for details.
    """
