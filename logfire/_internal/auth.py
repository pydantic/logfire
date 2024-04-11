from __future__ import annotations

import platform
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict
from urllib.parse import urljoin

import requests

from logfire.exceptions import LogfireConfigError

from .utils import UnexpectedResponse

HOME_LOGFIRE = Path.home() / '.logfire'
"""Folder used to store global configuration, and user tokens."""
DEFAULT_FILE = HOME_LOGFIRE / 'default.toml'
"""File used to store user tokens."""


class UserTokenData(TypedDict):
    """User token data."""

    token: str
    expiration: str


class DefaultFile(TypedDict):
    """Content of the default.toml file."""

    tokens: dict[str, UserTokenData]


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


def is_logged_in(data: DefaultFile, logfire_url: str) -> bool:
    """Check if the user is logged in.

    Returns:
        True if the user is logged in, False otherwise.
    """
    for url, info in data['tokens'].items():  # pragma: no branch
        # token expirations are in UTC
        expiry_date = datetime.fromisoformat(info['expiration'].rstrip('Z')).replace(tzinfo=timezone.utc)
        if url == logfire_url and datetime.now(tz=timezone.utc) < expiry_date:  # pragma: no branch
            return True
    return False  # pragma: no cover
