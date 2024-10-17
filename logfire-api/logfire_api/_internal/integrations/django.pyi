from logfire import Logfire as Logfire
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from typing import Any

def instrument_django(logfire_instance: Logfire, *, capture_headers: bool = False, **kwargs: Any):
    """Instrument the `django` module so that spans are automatically created for each web request.

    See the `Logfire.instrument_django` method for details.
    """
