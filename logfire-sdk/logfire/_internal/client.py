from __future__ import annotations

from typing import Any, Self
from urllib.parse import urljoin

from requests import Response, Session

from logfire.exceptions import LogfireConfigError
from logfire.version import VERSION

from .auth import UserToken, UserTokenCollection
from .constants import HTTP_CONNECT_TIMEOUT
from .http_transport import install_connection_policy
from .server_response import ServerResponseCallback, install_logfire_response_hook
from .utils import UnexpectedResponse

UA_HEADER = f'logfire/{VERSION}'
_REQUEST_TIMEOUT = (HTTP_CONNECT_TIMEOUT, 30)


class LogfireClient:
    """A Logfire HTTP client to interact with the API.

    Args:
        user_token: The user token to use when authenticating against the API.
        server_response_hook: Optional override for the API response hook (see
            `AdvancedOptions.server_response_hook`).
    """

    def __init__(
        self,
        user_token: UserToken,
        server_response_hook: ServerResponseCallback | None = None,
    ) -> None:
        if user_token.is_expired:
            raise RuntimeError('The provided user token is expired')
        self.base_url = user_token.base_url
        self._token = user_token.token
        self._session = Session()
        install_connection_policy(self._session)
        self._session.headers.update({'Authorization': self._token, 'User-Agent': UA_HEADER})
        install_logfire_response_hook(self._session, server_response_hook)

    @classmethod
    def from_url(
        cls,
        base_url: str | None,
        server_response_hook: ServerResponseCallback | None = None,
    ) -> Self:
        """Create a client from the provided base URL.

        Args:
            base_url: The base URL to use when looking for a user token. If `None`, will prompt
                the user into selecting a token from the token collection (or, if only one available,
                use it directly). The token collection will be created from the `~/.logfire/default.toml`
                file (or an empty one if no such file exists).
            server_response_hook: Optional override for the API response hook (see
                `AdvancedOptions.server_response_hook`).
        """
        return cls(
            user_token=UserTokenCollection().get_token(base_url),
            server_response_hook=server_response_hook,
        )

    def _get_raw(self, endpoint: str, params: dict[str, Any] | None = None) -> Response:
        response = self._session.get(urljoin(self.base_url, endpoint), params=params, timeout=_REQUEST_TIMEOUT)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _get(self, endpoint: str, *, params: dict[str, Any] | None = None, error_message: str) -> Any:
        try:
            return self._get_raw(endpoint, params).json()
        except UnexpectedResponse as e:
            raise LogfireConfigError(error_message) from e

    def _put_raw(self, endpoint: str, body: Any | None = None) -> Response:  # pragma: no cover
        response = self._session.put(urljoin(self.base_url, endpoint), json=body, timeout=_REQUEST_TIMEOUT)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _put(self, endpoint: str, *, body: Any | None = None, error_message: str) -> Any:  # pragma: no cover
        try:
            return self._put_raw(endpoint, body).json()
        except UnexpectedResponse as e:
            raise LogfireConfigError(error_message) from e

    def get_user_information(self) -> dict[str, Any]:
        """Get information about the logged-in user."""
        return self._get('/v1/account/me', error_message='Error retrieving user information')

    def get_prompt(self, organization: str, project_name: str, issue: str) -> dict[str, Any]:
        """Get a prompt to be used with your favorite LLM."""
        return self._get(
            f'/v1/organizations/{organization}/projects/{project_name}/prompts',
            params={'issue': issue},
            error_message='Error retrieving prompt',
        )
