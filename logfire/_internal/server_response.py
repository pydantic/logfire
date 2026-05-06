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
pass a custom `hook` to replace the default behaviour (see
`AdvancedOptions.transport_response_hook`).
"""

from __future__ import annotations

import warnings
from typing import Any, Callable

import requests

from logfire.exceptions import LogfireServerError, LogfireServerWarning

WARNING_HEADER_NAME = 'X-Logfire-Warning'
ERROR_HEADER_NAME = 'X-Logfire-Error'

TransportResponseHook = Callable[[requests.Response], object]
"""Callable invoked for every Logfire API response received by the SDK.

The return value is ignored; raise to abort the call.
"""


def process_logfire_response_headers(response: requests.Response) -> None:
    """Default transport response hook: surface `X-Logfire-Warning` / `X-Logfire-Error` headers."""
    warning_message = response.headers.get(WARNING_HEADER_NAME)
    if warning_message:
        warnings.warn(warning_message, LogfireServerWarning, stacklevel=2)
    error_message = response.headers.get(ERROR_HEADER_NAME)
    if error_message:
        raise LogfireServerError(error_message)


def install_logfire_response_hook(
    session: requests.Session,
    hook: TransportResponseHook | None = None,
) -> None:
    """Install a `requests` response hook on `session` for every Logfire API response.

    `hook` defaults to `process_logfire_response_headers`. Pass a custom callable
    to replace the default behaviour (e.g. opt out by passing `lambda response: None`).
    """
    user_hook = hook if hook is not None else process_logfire_response_headers

    def _hook(response: requests.Response, *_args: Any, **_kwargs: Any) -> requests.Response:
        user_hook(response)
        return response

    response_hooks: list[Any] = session.hooks.setdefault('response', [])
    response_hooks.append(_hook)
