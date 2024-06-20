from flask.app import Flask as Flask
from typing import Any

def instrument_flask(app: Flask, **kwargs: Any):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
