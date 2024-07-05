import requests
from .utils import UnexpectedResponse as UnexpectedResponse
from _typeshed import Incomplete
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from typing import TypedDict

HOME_LOGFIRE: Incomplete
DEFAULT_FILE: Incomplete

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
def is_logged_in(data: DefaultFile, logfire_url: str) -> bool:
    """Check if the user is logged in.

    Returns:
        True if the user is logged in, False otherwise.
    """
