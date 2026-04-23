from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from requests import Response, Session
from typing_extensions import Self

from logfire.exceptions import LogfireConfigError
from logfire.version import VERSION

from .auth import UserToken, UserTokenCollection
from .utils import UnexpectedResponse

UA_HEADER = f'logfire/{VERSION}'


def _apply_auth_header(session: Session, user_token: UserToken) -> None:
    session.headers['Authorization'] = user_token.header_value


class ProjectAlreadyExists(Exception):
    pass


class InvalidProjectName(Exception):
    def __init__(self, reason: str, /) -> None:
        self.reason = reason


class LogfireClient:
    """A Logfire HTTP client to interact with the API.

    Args:
        user_token: The user token to use when authenticating against the API.
    """

    def __init__(
        self,
        user_token: UserToken,
        collection: UserTokenCollection | None = None,
    ) -> None:
        self._user_token = user_token
        self._collection = collection
        if user_token.is_expired and not self._try_refresh():
            raise RuntimeError('The provided user token is expired')
        self.base_url = user_token.base_url
        self._session = Session()
        self._session.headers['User-Agent'] = UA_HEADER
        _apply_auth_header(self._session, user_token)

    @property
    def _token(self) -> str:
        return self._user_token.token.get_secret_value()

    @classmethod
    def from_url(cls, base_url: str | None) -> Self:
        """Create a client from the provided base URL.

        Args:
            base_url: The base URL to use when looking for a user token. If `None`, will prompt
                the user into selecting a token from the token collection (or, if only one available,
                use it directly). The token collection will be created from the `~/.logfire/default.toml`
                file (or an empty one if no such file exists).
        """
        collection = UserTokenCollection()
        return cls(user_token=collection.get_token(base_url), collection=collection)

    def _try_refresh(self, *, force: bool = False) -> bool:
        """Refresh the OAuth access token if possible. Returns True on success.

        ``force=True`` bypasses the "near-expiry" check; used after a 401 so
        we rotate even when the access token's nominal TTL is still in the
        future (the server has already told us the credential is rejected).
        """
        token = self._user_token
        if token.auth_method != 'oauth' or not token.refresh_token or self._collection is None:
            return False
        before_access = token.token
        self._collection.refresh_if_needed(token, Session(), force=force)
        if token.token != before_access and not token.is_expired:
            # Propagate the refreshed token to our session.
            if hasattr(self, '_session'):
                _apply_auth_header(self._session, token)
            return True
        return False

    def _maybe_refresh_before_request(self) -> None:
        if self._user_token.needs_refresh:
            self._try_refresh()

    def _get_raw(self, endpoint: str, params: dict[str, Any] | None = None) -> Response:
        self._maybe_refresh_before_request()
        response = self._session.get(urljoin(self.base_url, endpoint), params=params)
        if response.status_code == 401 and self._try_refresh(force=True):
            response = self._session.get(urljoin(self.base_url, endpoint), params=params)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _get(self, endpoint: str, *, params: dict[str, Any] | None = None, error_message: str) -> Any:
        try:
            return self._get_raw(endpoint, params).json()
        except UnexpectedResponse as e:
            raise LogfireConfigError(error_message) from e

    def _post_raw(self, endpoint: str, body: Any | None = None) -> Response:
        self._maybe_refresh_before_request()
        response = self._session.post(urljoin(self.base_url, endpoint), json=body)
        if response.status_code == 401 and self._try_refresh(force=True):
            response = self._session.post(urljoin(self.base_url, endpoint), json=body)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _put_raw(self, endpoint: str, body: Any | None = None) -> Response:  # pragma: no cover
        response = self._session.put(urljoin(self.base_url, endpoint), json=body)
        UnexpectedResponse.raise_for_status(response)
        return response

    def _put(self, endpoint: str, *, body: Any | None = None, error_message: str) -> Any:  # pragma: no cover
        try:
            return self._put_raw(endpoint, body).json()
        except UnexpectedResponse as e:
            raise LogfireConfigError(error_message) from e

    def _post(self, endpoint: str, *, body: Any | None = None, error_message: str) -> Any:
        try:
            return self._post_raw(endpoint, body).json()
        except UnexpectedResponse as e:
            raise LogfireConfigError(error_message) from e

    def get_user_organizations(self) -> list[dict[str, Any]]:
        """Get the organizations of the logged-in user."""
        return self._get(
            '/v1/organizations/available-for-projects/', error_message='Error retrieving list of organizations'
        )

    def get_user_information(self) -> dict[str, Any]:
        """Get information about the logged-in user."""
        return self._get('/v1/account/me', error_message='Error retrieving user information')

    def get_user_projects(self) -> list[dict[str, Any]]:
        """Get the projects of the logged-in user."""
        return self._get('/v1/writable-projects/', error_message='Error retrieving list of projects')

    def create_new_project(self, organization: str, project_name: str):
        """Create a new project.

        Args:
            organization: The organization that should hold the new project.
            project_name: The name of the project to be created.

        Returns:
            The newly created project.
        """
        try:
            response = self._post_raw(f'/v1/organizations/{organization}/projects', body={'project_name': project_name})
        except UnexpectedResponse as e:
            r = e.response
            if r.status_code == 409:
                raise ProjectAlreadyExists
            if r.status_code == 422:
                error = r.json()['detail'][0]
                if error['loc'] == ['body', 'project_name']:  # pragma: no branch
                    raise InvalidProjectName(error['msg'])

            raise LogfireConfigError('Error creating new project')
        return response.json()

    def create_write_token(self, organization: str, project_name: str) -> dict[str, Any]:
        """Create a write token for the given project in the given organization."""
        return self._post(
            f'/v1/organizations/{organization}/projects/{project_name}/write-tokens/',
            error_message='Error creating project write token',
        )

    def create_read_token(self, organization: str, project_name: str) -> dict[str, Any]:
        """Create a read token for the given project in the given organization."""
        return self._post(
            f'/v1/organizations/{organization}/projects/{project_name}/read-tokens',
            body={'description': 'Created by Logfire CLI'},
            error_message='Error creating project read token',
        )

    def get_prompt(self, organization: str, project_name: str, issue: str) -> dict[str, Any]:
        """Get a prompt to be used with your favorite LLM."""
        return self._get(
            f'/v1/organizations/{organization}/projects/{project_name}/prompts',
            params={'issue': issue},
            error_message='Error retrieving prompt',
        )
