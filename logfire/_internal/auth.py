from __future__ import annotations

import platform
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urljoin

if sys.version_info >= (3, 9):
    from functools import cache
else:
    from functools import lru_cache

    cache = lru_cache(maxsize=None)

import requests
from rich.prompt import IntPrompt
from typing_extensions import Self

from logfire.exceptions import LogfireConfigError

from .utils import UnexpectedResponse, read_toml_file

HOME_LOGFIRE = Path.home() / '.logfire'
"""Folder used to store global configuration, and user tokens."""
DEFAULT_FILE = HOME_LOGFIRE / 'default.toml'
"""File used to store user tokens."""


class UserTokenData(TypedDict):
    """User token data."""

    token: str
    expiration: str


class TokensFileData(TypedDict):
    """Content of the file containing the user tokens."""

    tokens: dict[str, UserTokenData]


@dataclass
class UserToken:
    """A user token."""

    token: str
    base_url: str
    expiration: str

    @classmethod
    def from_user_token_data(cls, base_url: str, token: UserTokenData) -> Self:
        return cls(
            token=token['token'],
            base_url=base_url,
            expiration=token['expiration'],
        )

    @property
    def is_expired(self) -> bool:
        return datetime.now(tz=timezone.utc) >= datetime.fromisoformat(self.expiration.rstrip('Z')).replace(
            tzinfo=timezone.utc
        )

    def __str__(self) -> str:
        # TODO define in this module?
        from .config import PYDANTIC_LOGFIRE_TOKEN_PATTERN, REGIONS

        region = 'us'
        if match := PYDANTIC_LOGFIRE_TOKEN_PATTERN.match(self.token):
            region = match.group('region')
            if region not in REGIONS:
                region = 'us'

        token_repr = f'{region.upper()} ({self.base_url}) - '
        if match:
            token_repr += match.group('safe_part') + match.group('token')[:5]
        else:
            token_repr += self.token[:5]
        token_repr += '****'
        return token_repr


@dataclass
class UserTokenCollection:
    """A collection of user tokens."""
    user_tokens: list[UserToken]

    @classmethod
    def from_tokens(cls, tokens: TokensFileData) -> Self:
        return cls(
            user_tokens=[
                UserToken.from_user_token_data(url, data)  # pyright: ignore[reportArgumentType], waiting for PEP 728
                for url, data in tokens.items()
            ]
        )

    @classmethod
    def from_tokens_file(cls, file: Path) -> Self:
        return cls.from_tokens(cast(TokensFileData, read_toml_file(file)))

    def get_token(self, base_url: str | None = None) -> UserToken:
        if base_url is not None:
            token = next((t for t in self.user_tokens if t.base_url == base_url), None)
            if token is None:
                raise LogfireConfigError(
                    f'No user token was found matching the {base_url} Logfire URL. '
                    'Please run `logfire auth` to authenticate.'
                )
        else:
            if len(self.user_tokens) == 1:
                token = self.user_tokens[0]
            elif len(self.user_tokens) >= 2:
                choices_str = '\n'.join(
                    f'{i}. {token} ({"expired" if token.is_expired else "valid"})'
                    for i, token in enumerate(self.user_tokens, start=1)
                )
                int_choice = IntPrompt.ask(
                    f'Multiple user tokens found. Please select one:\n{choices_str}\n',
                    choices=[str(i) for i in range(1, len(self.user_tokens) + 1)],
                )
                token = self.user_tokens[int_choice - 1]
            else:  # self.user_tokens == []
                raise LogfireConfigError('No user tokens are available. Please run `logfire auth` to authenticate.')

        if token.is_expired:
            raise LogfireConfigError(f'User token {token} is expired. Pleas run `logfire auth` to authenticate.')
        return token

    def is_logged_in(self, base_url: str | None = None) -> bool:
        if base_url is not None:
            tokens = (t for t in self.user_tokens if t.base_url == base_url)
        else:
            tokens = self.user_tokens
        return any(not t.is_expired for t in tokens)

    def add_token(self, base_url: str, token: UserTokenData) -> UserToken:
        existing_token = next((t for t in self.user_tokens if t.base_url == base_url), None)
        if existing_token:
            token_index = self.user_tokens.index(existing_token)
            self.user_tokens.remove(existing_token)
        else:
            token_index = len(self.user_tokens)

        user_token = UserToken.from_user_token_data(base_url, token)
        self.user_tokens.insert(token_index, user_token)
        return user_token

    def dump(self, path: Path) -> None:
        # There's no standard library package to write TOML files, so we'll write it manually.
        with path.open('w') as f:
            for user_token in self.user_tokens:
                f.write(f'[tokens."{user_token.base_url}"]\n')
                f.write(f'token = "{user_token.token}"\n')
                f.write(f'expiration = "{user_token.expiration}"\n')


@cache
def default_token_collection() -> UserTokenCollection:
    """The default token collection, created from the `~/.logfire/default.toml` file."""
    return UserTokenCollection.from_tokens_file(DEFAULT_FILE)


class NewDeviceFlow(TypedDict):
    """Matches model of the same name in the backend."""

    device_code: str
    frontend_auth_url: str


def request_device_code(session: requests.Session, base_api_url: str) -> tuple[str, str]:
    """Request a device code from the Logfire API.

    Args:
        session: The `requests` session to use.
        base_api_url: The base URL of the Logfire instance.

    Returns:
    return data['device_code'], data['frontend_auth_url']
        The device code and the frontend URL to authenticate the device at, as a `NewDeviceFlow` dict.
    """
    machine_name = platform.uname()[1]
    device_auth_endpoint = urljoin(base_api_url, '/v1/device-auth/new/')
    try:
        res = session.post(device_auth_endpoint, params={'machine_name': machine_name})
        UnexpectedResponse.raise_for_status(res)
    except requests.RequestException as e:  # pragma: no cover
        raise LogfireConfigError('Failed to request a device code.') from e
    data: NewDeviceFlow = res.json()
    return data['device_code'], data['frontend_auth_url']


def poll_for_token(session: requests.Session, device_code: str, base_api_url: str) -> UserTokenData:
    """Poll the Logfire API for the user token.

    This function will keep polling the API until it receives a user token, not that
    each request should take ~10 seconds as the API endpoint will block waiting for the user to
    complete authentication.

    Args:
        session: The `requests` session to use.
        device_code: The device code to poll for.
        base_api_url: The base URL of the Logfire instance.

    Returns:
        The user token.
    """
    auth_endpoint = urljoin(base_api_url, f'/v1/device-auth/wait/{device_code}')
    errors = 0
    while True:
        try:
            res = session.get(auth_endpoint, timeout=15)
            UnexpectedResponse.raise_for_status(res)
        except requests.RequestException as e:
            errors += 1
            if errors >= 4:
                raise LogfireConfigError('Failed to poll for token.') from e
            warnings.warn('Failed to poll for token. Retrying...')
        else:
            opt_user_token: UserTokenData | None = res.json()
            if opt_user_token:
                return opt_user_token
