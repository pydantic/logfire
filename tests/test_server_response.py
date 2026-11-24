from __future__ import annotations

import warnings

import requests
from inline_snapshot import snapshot

from logfire._internal.server_response import install_logfire_response_hook
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


def test_custom_response_hook_replaces_default_warning() -> None:
    session = requests.Session()
    seen: list[requests.Response] = []
    install_logfire_response_hook(session, lambda helper: seen.append(helper.response))
    response = requests.Response()
    response.headers[ServerResponseCallbackHelper.WARNING_HEADER_NAME] = 'custom warning'

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        [hook] = session.hooks['response']
        assert hook(response) is response

    assert seen == [response]
    assert caught == []
