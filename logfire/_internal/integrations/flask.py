from __future__ import annotations

from typing import Any

from flask.app import Flask

from logfire._internal.stack_info import warn_at_user_stacklevel

try:
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_flask()` requires the `opentelemetry-instrumentation-flask` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[flask]'"
    )

from logfire import Logfire
from logfire._internal.utils import maybe_capture_server_headers
from logfire.integrations.flask import CommenterOptions, RequestHook, ResponseHook


def instrument_flask(
    logfire_instance: Logfire,
    # Note that `Logfire.instrument_flask()` requires this argument. It's only omitted when called via the
    # `logfire run` CLI. This is because `FlaskInstrumentor.instrument_app()` has to be called before
    # `from flask import Flask` which is easy to get wrong.
    app: Flask | None = None,
    *,
    capture_headers: bool = False,
    enable_commenter: bool = True,
    commenter_options: CommenterOptions | None = None,
    excluded_urls: str | None = None,
    request_hook: RequestHook | None = None,
    response_hook: ResponseHook | None = None,
    **kwargs: Any,
):
    """Instrument `app` so that spans are automatically created for each request.

    See the `Logfire.instrument_flask` method for details.
    """
    maybe_capture_server_headers(capture_headers)

    # Previously the parameter was accidentally called exclude_urls, so we support both.
    if 'exclude_urls' in kwargs:  # pragma: no cover
        warn_at_user_stacklevel('exclude_urls is deprecated; use excluded_urls instead', DeprecationWarning)
    excluded_urls = excluded_urls or kwargs.pop('exclude_urls', None)

    opentelemetry_kwargs = {
        'enable_commenter': enable_commenter,
        'commenter_options': commenter_options,
        'excluded_urls': excluded_urls,
        'request_hook': request_hook,
        'response_hook': response_hook,
        'tracer_provider': logfire_instance.config.get_tracer_provider(),
        'meter_provider': logfire_instance.config.get_meter_provider(),
        **kwargs,
    }

    if app is None:
        FlaskInstrumentor().instrument(**opentelemetry_kwargs)
    else:
        FlaskInstrumentor().instrument_app(app, **opentelemetry_kwargs)  # type: ignore[reportUnknownMemberType]
