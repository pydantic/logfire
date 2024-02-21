from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

import requests

HOME_LOGFIRE = Path.home() / '.logfire'
"""Folder used to store global configuration, and user tokens."""
DEFAULT_FILE = HOME_LOGFIRE / 'default.toml'
"""File used to store user tokens."""


class LoginDeviceCodeResponse(TypedDict):
    """Response from the GitHub API for the device code request."""

    device_code: str
    user_code: str
    verification_uri: str
    expired_in: int
    interval: int


class UserTokenData(TypedDict):
    """User token data."""

    token: str
    expiration: str


class DefaultFile(TypedDict):
    """Content of the default.toml file."""

    tokens: dict[str, UserTokenData]


def request_device_code(session: requests.Session, github_client_id: str) -> LoginDeviceCodeResponse:
    """Request the device code from the GitHub API.

    Args:
        session: The `requests` session to use.
        github_client_id: The GitHub client ID.

    Returns:
        The response from the GitHub API.
    """
    response = session.post(
        url='https://github.com/login/device/code',
        params={'client_id': github_client_id, 'scope': 'user:email'},
    )
    response.raise_for_status()
    return response.json()


class ExpiredToken(Exception):
    """Raised when the device code has expired."""


class LoginCancelled(Exception):
    """Raised when the user cancels the login."""


def poll_for_token(session: requests.Session, *, client_id: str, interval: int, device_code: str) -> str:
    """Poll the GitHub API for the access token.

    This function will keep polling the GitHub API until it receives an access token.

    Args:
        session: The `requests` session to use.
        client_id: The GitHub client ID.
        interval: The interval in seconds to wait between polls.
        device_code: The device code to poll for.

    Returns:
        The access token.
    """
    access_token: str | None = None
    while access_token is None:
        res = request_access_token(session, device_code=device_code, client_id=client_id)
        error = res.get('error')

        if error == 'authorization_pending':
            time.sleep(interval)
        elif error == 'slow_down':
            time.sleep(interval + 5)
        elif error == 'expired_token':
            raise ExpiredToken('The device code has expired. Please run `login` again.')
        elif error == 'access_denied':
            raise LoginCancelled('Login cancelled by user.')

        access_token = res.get('access_token')
    return access_token


class SuccessResponse(TypedDict):
    """Response from the GitHub API for the access token request."""

    access_token: str
    token_type: Literal['bearer']
    scope: str


class ErrorResponse(TypedDict):
    """Error response from the GitHub API."""

    error: Literal['authorization_pending', 'slow_down', 'expired_token', 'access_denied']
    error_description: str
    error_uri: str


def request_access_token(
    session: requests.Session, *, device_code: str, client_id: str
) -> SuccessResponse | ErrorResponse:
    """Request the access token from the GitHub API.

    Args:
        session: The `requests` session to use.
        device_code: The device code to request the access token for.
        client_id: The GitHub client ID.

    Returns:
        The response from the GitHub API.
    """
    response = session.post(
        'https://github.com/login/oauth/access_token',
        params={
            'client_id': client_id,
            'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        },
    )
    return response.json()


def is_logged_in(data: DefaultFile, logfire_url: str) -> bool:
    """Check if the user is logged in.

    Returns:
        True if the user is logged in, False otherwise.
    """
    for url, info in data['tokens'].items():
        if url == logfire_url and datetime.now() < datetime.fromisoformat(info['expiration']):
            return True
    return False
