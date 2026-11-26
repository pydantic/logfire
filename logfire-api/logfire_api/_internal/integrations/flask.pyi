from flask.app import Flask
from logfire import Logfire as Logfire
from logfire._internal.utils import maybe_capture_server_headers as maybe_capture_server_headers
from logfire.integrations.flask import CommenterOptions as CommenterOptions, RequestHook as RequestHook, ResponseHook as ResponseHook
from typing import Any

def instrument_flask(logfire_instance: Logfire, app: Flask | None = None, *, capture_headers: bool = False, enable_commenter: bool = True, commenter_options: CommenterOptions | None = None, excluded_urls: str | None = None, request_hook: RequestHook | None = None, response_hook: ResponseHook | None = None, **kwargs: Any) -> None:
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
