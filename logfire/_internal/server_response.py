"""Surface out-of-band signals the Logfire backend wants every SDK request to know about.

The server attaches custom headers to API responses:

* `X-Logfire-Warning`: an out-of-band warning the server wants the user to see.
  Surfaced via `warnings.warn(..., LogfireServerWarning)`. Python's standard
  "default" filter dedupes identical messages, so a chatty server only warns once.
* `X-Logfire-Error`: an out-of-band error the server wants the SDK to raise.
  Always raised as `LogfireServerError`. Callers that want to keep working past
  it (the OTLP pipeline, the variables provider) already swallow exceptions from
  their HTTP calls; CRUD/CLI propagate the error to the user.

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

    By default, calls ServerResponseCallbackHelper.default_hook(), which emits warnings and raises errors based
    on the presence of `X-Logfire-Warning` and `X-Logfire-Error` response headers.

    Pass a custom callable to replace the default behavior (e.g. opt out by passing `lambda _: None`).
    """

    def _hook(response: requests.Response, *args: Any, **kwargs: Any) -> requests.Response:
        helper = ServerResponseCallbackHelper(response, args, kwargs)
        if hook:
            hook(helper)
        else:
            helper.default_hook()
        return response

    response_hooks: list[Any] = session.hooks.setdefault('response', [])
    response_hooks.append(_hook)
