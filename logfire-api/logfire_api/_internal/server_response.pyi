import requests
from logfire.types import ServerResponseCallback as ServerResponseCallback, ServerResponseCallbackHelper as ServerResponseCallbackHelper

def install_logfire_response_hook(session: requests.Session, hook: ServerResponseCallback | None = None) -> None:
    """Install a `requests` response hook on `session` for every Logfire API response.

    By default, calls `ServerResponseCallbackHelper.default_hook()`, which emits a warning
    if the `X-Logfire-Warning` response header is present.

    Pass a custom callable to replace the default behavior (e.g. opt out by passing `lambda _: None`).
    """
