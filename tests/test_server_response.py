from __future__ import annotations

import warnings

import pytest
import requests
import requests_mock
from inline_snapshot import snapshot

from logfire.exceptions import LogfireServerError, LogfireServerWarning
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


def test_process_response_error_header_raises():
    response = requests.Response()
    response.headers[ServerResponseCallbackHelper.ERROR_HEADER_NAME] = 'something is wrong'
    with pytest.raises(LogfireServerError, match='something is wrong'):
        ServerResponseCallbackHelper(response, (), {}).default_hook()


def test_response_hook_installed_on_logfire_client():
    from logfire._internal.auth import UserToken
    from logfire._internal.client import LogfireClient

    token = UserToken(
        token='pylf_v1_us_xxx',
        base_url='https://logfire-us.pydantic.dev',
        expiration='2099-12-31T23:59:59',
    )
    client = LogfireClient(user_token=token)

    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'name': 'me'},
            headers={ServerResponseCallbackHelper.WARNING_HEADER_NAME: 'deprecated endpoint'},
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            client.get_user_information()

    assert any(isinstance(w.message, LogfireServerWarning) for w in caught)

    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'name': 'me'},
            headers={ServerResponseCallbackHelper.ERROR_HEADER_NAME: 'no longer supported'},
        )
        with pytest.raises(LogfireServerError, match='no longer supported'):
            client.get_user_information()


def test_custom_server_response_hook_replaces_default():
    """A custom hook replaces the built-in header processor entirely."""
    from logfire._internal.auth import UserToken
    from logfire._internal.client import LogfireClient

    seen: list[requests.Response] = []

    def my_hook(helper: ServerResponseCallbackHelper) -> None:
        seen.append(helper.response)

    token = UserToken(
        token='pylf_v1_us_xxx',
        base_url='https://logfire-us.pydantic.dev',
        expiration='2099-12-31T23:59:59',
    )
    client = LogfireClient(user_token=token, server_response_hook=my_hook)

    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'name': 'me'},
            # Both headers set: default would warn AND raise; custom hook ignores them.
            headers={
                ServerResponseCallbackHelper.WARNING_HEADER_NAME: 'deprecated',
                ServerResponseCallbackHelper.ERROR_HEADER_NAME: 'broken',
            },
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            client.get_user_information()

    assert len(seen) == 1
    assert not any(isinstance(w.message, LogfireServerWarning) for w in caught)


def test_server_response_hook_can_opt_out():
    """`lambda response: None` disables both warnings and errors."""
    from logfire._internal.auth import UserToken
    from logfire._internal.client import LogfireClient

    token = UserToken(
        token='pylf_v1_us_xxx',
        base_url='https://logfire-us.pydantic.dev',
        expiration='2099-12-31T23:59:59',
    )
    client = LogfireClient(user_token=token, server_response_hook=lambda response: None)

    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'name': 'me'},
            headers={ServerResponseCallbackHelper.ERROR_HEADER_NAME: 'no longer supported'},
        )
        # No exception raised.
        assert client.get_user_information() == {'name': 'me'}
