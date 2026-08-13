from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests
from opentelemetry.sdk.trace import Span

from logfire._internal.main import set_user_attributes_on_raw_span
from logfire._internal.stack_info import warn_at_user_stacklevel
from logfire._internal.utils import handle_internal_errors

try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
except ImportError:
    raise RuntimeError(
        '`logfire.instrument_requests()` requires the `opentelemetry-instrumentation-requests` package.\n'
        'You can install this with:\n'
        "    pip install 'logfire[requests]'"
    )


def instrument_requests(
    excluded_urls: str | None = None,
    request_hook: Callable[[Span, requests.PreparedRequest], None] | None = None,
    response_hook: Callable[[Span, requests.PreparedRequest, requests.Response], None] | None = None,
    *,
    capture_all: bool = False,
    capture_request_body: bool = False,
    capture_response_body: bool = False,
    **kwargs: Any,
) -> None:
    """Instrument the `requests` module so that spans are automatically created for each request.

    See the `Logfire.instrument_requests` method for details.
    """
    if capture_all and (capture_request_body or capture_response_body):
        warn_at_user_stacklevel(
            'You should use either `capture_all` or the specific capture parameters, not both.', UserWarning
        )

    should_capture_request_body = capture_all or capture_request_body
    should_capture_response_body = capture_all or capture_response_body

    RequestsInstrumentor().instrument(
        excluded_urls=excluded_urls,
        request_hook=_make_request_hook(request_hook, should_capture_request_body),
        response_hook=_make_response_hook(response_hook, should_capture_response_body),
        **kwargs,
    )


def _make_request_hook(
    hook: Callable[[Span, requests.PreparedRequest], None] | None, capture_body: bool
) -> Callable[[Span, requests.PreparedRequest], None] | None:
    if not capture_body:
        return hook

    def request_hook(span: Span, request: requests.PreparedRequest) -> None:
        _capture_body(span, request.body, request.headers.get('Content-Type'), 'http.request.body.text')
        if callable(hook):
            hook(span, request)

    return request_hook


def _make_response_hook(
    hook: Callable[[Span, requests.PreparedRequest, requests.Response], None] | None, capture_body: bool
) -> Callable[[Span, requests.PreparedRequest, requests.Response], None] | None:
    if not capture_body:
        return hook

    def response_hook(span: Span, request: requests.PreparedRequest, response: requests.Response) -> None:
        # `_content` is populated only when Requests has already read the response. In
        # particular, this deliberately leaves streamed responses untouched.
        _capture_body(
            span, response.__dict__.get('_content'), response.headers.get('Content-Type'), 'http.response.body.text'
        )
        if callable(hook):
            hook(span, request, response)

    return response_hook


@handle_internal_errors
def _capture_body(span: Span, body: Any, content_type: str | None, attribute_name: str) -> None:
    if body is None or _is_multipart(content_type):
        return
    if isinstance(body, str):
        text = body
    elif isinstance(body, memoryview):
        try:
            text = body.tobytes().decode(_charset(content_type))
        except (LookupError, UnicodeDecodeError):
            return
    elif isinstance(body, (bytes, bytearray)):
        try:
            text = bytes(body).decode(_charset(content_type))
        except (LookupError, UnicodeDecodeError):
            return
    else:
        # File objects, iterators, generators, and streaming bodies must not be read.
        return

    # The object schema makes the exporter parse JSON objects without normalising
    # raw JSON strings or scalars. Setting the original text afterwards also lets
    # the normal span scrubber inspect secrets before export.
    set_user_attributes_on_raw_span(span, {attribute_name: {}})
    span.set_attribute(attribute_name, text)


def _is_multipart(content_type: str | None) -> bool:
    return bool(content_type and content_type.split(';', 1)[0].strip().lower().startswith('multipart/'))


def _charset(content_type: str | None) -> str:
    if content_type:
        for parameter in content_type.split(';')[1:]:
            name, separator, value = parameter.partition('=')
            if separator and name.strip().lower() == 'charset':
                return value.strip().strip('"\'')
    return 'utf-8'
