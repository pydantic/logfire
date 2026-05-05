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
a response hook so every Logfire-bound HTTP response is inspected.
"""

from __future__ import annotations

import warnings
from typing import Any

import requests

from logfire.exceptions import LogfireServerError, LogfireServerWarning

WARNING_HEADER_NAME = 'X-Logfire-Warning'
ERROR_HEADER_NAME = 'X-Logfire-Error'


def process_logfire_response_headers(response: requests.Response, *_args: Any, **_kwargs: Any) -> requests.Response:
    """Handle `X-Logfire-Warning` / `X-Logfire-Error` headers on a Logfire API response.

    Designed to be installed as a `requests` response hook
    (`session.hooks['response'].append(...)`).
    """
    warning_message = response.headers.get(WARNING_HEADER_NAME)
    if warning_message:
        warnings.warn(warning_message, LogfireServerWarning, stacklevel=2)
    error_message = response.headers.get(ERROR_HEADER_NAME)
    if error_message:
        raise LogfireServerError(error_message)
    return response


def install_logfire_response_hook(session: requests.Session) -> None:
    """Install `process_logfire_response_headers` as a response hook on `session`.

    `requests.Session()` always initialises `hooks['response']` to a list, and every
    call site here passes a freshly-built session, so we just append.
    """
    response_hooks: list[Any] = session.hooks.setdefault('response', [])
    response_hooks.append(process_logfire_response_headers)
