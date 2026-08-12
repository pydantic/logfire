from __future__ import annotations

import pytest
import requests_mock

from logfire._internal.auth import UserToken
from logfire._internal.client import (
    _REQUEST_TIMEOUT,  # pyright: ignore[reportPrivateUsage]
    LogfireClient,
)


def test_client_expired_token() -> None:
    with pytest.raises(RuntimeError):
        LogfireClient(user_token=UserToken(token='abc', base_url='http://localhost', expiration='1970-01-01T00:00:00'))


def test_requests_send_a_timeout() -> None:
    """Every request the client makes must carry a timeout, otherwise an unresponsive server hangs the CLI."""
    client = LogfireClient(
        user_token=UserToken(token='abc', base_url='http://localhost', expiration='2099-12-31T23:59:59')
    )

    with requests_mock.Mocker() as m:
        m.get('http://localhost/v1/account/me', json={'name': 'me'})
        m.post('http://localhost/v1/organizations/my-org/projects/my-project/write-tokens/', json={'token': 'abc'})
        m.put('http://localhost/v1/anything', json={})

        client.get_user_information()
        client.create_write_token('my-org', 'my-project')
        # `_put_raw` has no public caller yet, so exercise the PUT path directly.
        client._put_raw('/v1/anything', body={})  # pyright: ignore[reportPrivateUsage]

    assert [(request.method, request.timeout) for request in m.request_history] == [
        ('GET', _REQUEST_TIMEOUT),
        ('POST', _REQUEST_TIMEOUT),
        ('PUT', _REQUEST_TIMEOUT),
    ]
