from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from requests import Response, Session

from logfire.exceptions import LogfireConfigError
from logfire.version import VERSION

from .utils import UnexpectedResponse

if TYPE_CHECKING:
    from .auth import UserToken


UA_HEADER = f'logfire/{VERSION}'


class ProjectAlreadyExists(Exception):
    pass


class InvalidProjectName(Exception):
    def __init__(self, reason: str, /) -> None:
        self.reason = reason


class LogfireClient:
    def __init__(self, user_token: UserToken) -> None:
        if user_token.is_expired:
            raise RuntimeError
        self.base_url = user_token.base_url
        self._token = user_token.token
        self._session = Session()
        self._session.headers.update({'Authorization': self._token, 'User-Agent': UA_HEADER})

    def _get(self, endpoint: str) -> Response:
        response = self._session.get(urljoin(self.base_url, endpoint))
        UnexpectedResponse.raise_for_status(response)
        return response

    def _post(self, endpoint: str, body: Any | None = None) -> Response:
        response = self._session.post(urljoin(self.base_url, endpoint), json=body)
        UnexpectedResponse.raise_for_status(response)
        return response

    def get_user_organizations(self) -> list[dict[str, Any]]:
        """Get the organizations of the logged-in user."""
        try:
            response = self._get('/v1/organizations')
        except UnexpectedResponse as e:
            raise LogfireConfigError('Error retrieving list of organizations') from e
        return response.json()

    def get_user_information(self) -> dict[str, Any]:
        """Get information about the logged-in user."""
        try:
            response = self._get('/v1/account/me')
        except UnexpectedResponse as e:
            raise LogfireConfigError('Error retrieving user information') from e
        return response.json()

    def get_user_projects(self) -> list[dict[str, Any]]:
        """Get the projects of the logged-in user."""
        try:
            response = self._get('/v1/projects')
        except UnexpectedResponse as e:  # pragma: no cover
            raise LogfireConfigError('Error retrieving list of projects') from e
        return response.json()

    def create_new_project(self, organization: str, project_name: str):
        """Create a new project.

        Args:
            organization: The organization that should hold the new project.
            project_name: The name of the project to be created.

        Returns:
            The newly created project.
        """
        try:
            response = self._post(f'/v1/projects/{organization}', body={'project_name': project_name})
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
        try:
            response = self._post(f'/v1/organizations/{organization}/projects/{project_name}/write-tokens')
        except UnexpectedResponse as e:
            raise LogfireConfigError('Error creating project write token') from e
        return response.json()
