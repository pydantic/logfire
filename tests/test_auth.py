from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import inline_snapshot.extra
import pytest
from inline_snapshot import snapshot

from logfire._internal.auth import UserToken, UserTokenCollection
from logfire.exceptions import LogfireConfigError


@pytest.mark.parametrize(
    ['base_url', 'token', 'expected'],
    [
        (
            'https://logfire-us.pydantic.dev',
            'pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - pylf_v1_us_0kYhc****',
        ),
        (
            'https://logfire-eu.pydantic.dev',
            'pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'EU (https://logfire-eu.pydantic.dev) - pylf_v1_eu_0kYhc****',
        ),
        (
            'https://logfire-us.pydantic.dev',
            '0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - 0kYhc****',
        ),
        (
            'https://logfire-us.pydantic.dev',
            'pylf_v1_unknownregion_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W',
            'US (https://logfire-us.pydantic.dev) - pylf_v1_unknownregion_0kYhc****',
        ),
    ],
)
def test_user_token_str(base_url: str, token: str, expected: str) -> None:
    user_token = UserToken(
        token=token,
        base_url=base_url,
        expiration='1970-01-01',
    )
    assert str(user_token) == expected


def test_get_user_token_explicit_url(default_credentials: Path) -> None:
    token_collection = UserTokenCollection(default_credentials)

    # https://logfire-us.pydantic.dev is the URL present in the default credentials fixture:
    token = token_collection.get_token(base_url='https://logfire-us.pydantic.dev')
    assert token.base_url == 'https://logfire-us.pydantic.dev'

    with inline_snapshot.extra.raises(
        snapshot(
            'LogfireConfigError: No user token was found matching the https://logfire-eu.pydantic.dev Logfire URL. Please run `logfire auth` to authenticate.'
        )
    ):
        token_collection.get_token(base_url='https://logfire-eu.pydantic.dev')


def test_get_user_token_no_explicit_url(default_credentials: Path) -> None:
    token_collection = UserTokenCollection(default_credentials)

    token = token_collection.get_token(base_url=None)

    # https://logfire-us.pydantic.dev is the URL present in the default credentials fixture:
    assert token.base_url == 'https://logfire-us.pydantic.dev'


def test_get_user_token_input_choice(multiple_credentials: Path) -> None:
    token_collection = UserTokenCollection(multiple_credentials)

    with patch('rich.prompt.IntPrompt.ask', side_effect=[1]):
        token = token_collection.get_token(base_url=None)
        # https://logfire-us.pydantic.dev is the first URL present in the multiple credentials fixture:
        assert token.base_url == 'https://logfire-us.pydantic.dev'


def test_get_user_token_empty_credentials(tmp_path: Path) -> None:
    empty_auth_file = tmp_path / 'default.toml'
    empty_auth_file.touch()

    token_collection = UserTokenCollection(empty_auth_file)
    with inline_snapshot.extra.raises(
        snapshot('LogfireConfigError: No user tokens are available. Please run `logfire auth` to authenticate.')
    ):
        token_collection.get_token()


def test_get_user_token_expired_credentials(expired_credentials: Path) -> None:
    token_collection = UserTokenCollection(expired_credentials)

    with inline_snapshot.extra.raises(
        snapshot(
            'LogfireConfigError: User token US (https://logfire-us.pydantic.dev) - pylf_v1_us_0kYhc**** is expired. Please run `logfire auth` to authenticate.'
        )
    ):
        # https://logfire-us.pydantic.dev is the URL present in the expired credentials fixture:
        token_collection.get_token(base_url='https://logfire-us.pydantic.dev')


def test_get_user_token_not_authenticated(default_credentials: Path) -> None:
    token_collection = UserTokenCollection(default_credentials)

    with pytest.raises(
        LogfireConfigError,
        match=(
            'No user token was found matching the http://localhost:8234 Logfire URL. '
            'Please run `logfire auth` to authenticate.'
        ),
    ):
        # Use a port that we don't use for local development to reduce conflicts with local configuration
        token_collection.get_token(base_url='http://localhost:8234')
