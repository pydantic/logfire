"""Surface out-of-band signals the Logfire backend wants every SDK request to know about.

The server attaches the `X-Logfire-Warning` header to API responses to signal an
out-of-band warning the server wants the user to see. It is surfaced via
`warnings.warn(..., LogfireServerWarning)`. Python's standard "default" filter
dedupes identical messages, so a chatty server only warns once.

`install_logfire_response_hook(session)` wires this into a `requests.Session` as
a response hook so every Logfire-bound HTTP response is inspected. Callers can
pass a custom `hook` to replace the default behavior (see
`AdvancedOptions.server_response_hook`).
"""

from __future__ import annotations

from typing import Any

import requests

from logfire.types import ServerResponseCallback, ServerResponseCallbackHelper


def install_logfire_response_hook(
    session: requests.Session,
    hook: ServerResponseCallback | None = None,
) -> None:
    """Install a `requests` response hook on `session` for every Logfire API response.

    By default, calls `ServerResponseCallbackHelper.default_hook()`, which emits a warning
    if the `X-Logfire-Warning` response header is present.

    Pass a custom callable to replace the default behavior (e.g. opt out by passing `lambda _: None`).
    """

    def _hook(response: requests.Response, *args: Any, **kwargs: Any) -> requests.Response:
        helper = ServerResponseCallbackHelper(response, args, kwargs)
        if hook is not None:
            hook(helper)
        else:
            helper.default_hook()
        return response

    response_hooks: list[Any] = session.hooks.setdefault('response', [])
    response_hooks.append(_hook)
