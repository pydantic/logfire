from __future__ import annotations

import warnings

import requests
from inline_snapshot import snapshot

from logfire.exceptions import LogfireServerWarning
from logfire.types import ServerResponseCallbackHelper


def test_process_response_warning_header_emits_warning():
    response = requests.Response()
    response.headers[ServerResponseCallbackHelper.WARNING_HEADER_NAME] = (
        'The /foo/bar endpoint is deprecated, please use /bar/baz'
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        ServerResponseCallbackHelper(response, (), {}).default_hook()
    assert [(w.category, str(w.message)) for w in caught] == snapshot(
        [(LogfireServerWarning, 'The /foo/bar endpoint is deprecated, please use /bar/baz')]
    )


def test_process_response_warning_header_dedupes():
    """Python's default `warnings` filter should fold repeats of the same message into one entry."""
    response = requests.Response()
    response.headers[ServerResponseCallbackHelper.WARNING_HEADER_NAME] = 'a duplicated warning'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('default')
        for _ in range(5):
            ServerResponseCallbackHelper(response, (), {}).default_hook()
    messages = [str(w.message) for w in caught]
    assert messages == ['a duplicated warning']
