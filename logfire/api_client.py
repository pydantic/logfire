"""Logfire API client for interacting with the Logfire public API.

This module provides sync and async clients for managing Logfire resources such as
projects, tokens, alerts, dashboards, and channels.
"""

from __future__ import annotations

import os
from datetime import timedelta
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar
from uuid import UUID

from typing_extensions import NotRequired, Self

from logfire._internal.config import get_base_url_from_token

try:
    from httpx import AsyncClient, Client, Response, Timeout
    from httpx._client import BaseClient
except ImportError as e:  # pragma: no cover
    raise ImportError('httpx is required to use the Logfire API clients') from e

if TYPE_CHECKING:
    pass

DEFAULT_TIMEOUT = Timeout(30.0)

# Environment variable for API token
LOGFIRE_API_TOKEN_ENV = 'LOGFIRE_API_TOKEN'


# ============================================================================
# Exceptions
# ============================================================================


class LogfireAPIError(Exception):
    """Base exception for Logfire API errors."""

    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class LogfireAPINotFoundError(LogfireAPIError):
    """Resource not found (404)."""

    pass


class LogfireAPIForbiddenError(LogfireAPIError):
    """Permission denied (403)."""

    pass


class LogfireAPIConflictError(LogfireAPIError):
    """Resource already exists (409)."""

    pass


class LogfireAPIValidationError(LogfireAPIError):
    """Validation error (422)."""

    pass


class LogfireAPIRateLimitError(LogfireAPIError):
    """Rate limit exceeded (429)."""

    pass


# ============================================================================
# Type definitions for API responses
# ============================================================================

ProjectVisibility = Literal['private', 'public']


class ProjectRead(TypedDict):
    """Project information returned by the API."""

    id: str
    project_name: str
    created_at: str
    description: str | None
    organization_name: str
    visibility: ProjectVisibility


class ProjectCreate(TypedDict, total=False):
    """Data for creating a new project."""

    project_name: str
    description: NotRequired[str | None]
    visibility: NotRequired[ProjectVisibility]


class ProjectUpdate(TypedDict, total=False):
    """Data for updating a project."""

    project_name: NotRequired[str | None]
    description: NotRequired[str | None]
    visibility: NotRequired[ProjectVisibility | None]


class WriteTokenRead(TypedDict):
    """Write token information returned by the API."""

    id: str
    project_id: str
    created_at: str
    description: str | None
    project_name: str
    created_by_name: str | None
    token_prefix: str


class WriteTokenCreated(TypedDict):
    """Write token with the actual token value, returned on creation."""

    id: str
    project_id: str
    created_at: str
    description: str | None
    token: str


class ReadTokenRead(TypedDict):
    """Read token information returned by the API."""

    id: str
    project_id: str
    created_at: str
    description: str | None
    project_name: str
    created_by_name: str | None
    token_prefix: str


class ReadTokenCreated(TypedDict):
    """Read token with the actual token value, returned on creation."""

    id: str
    project_id: str
    created_at: str
    description: str | None
    token: str


NotifyWhen = Literal['has_matches', 'has_matches_changed', 'matches_changed']


class ChannelConfig(TypedDict, total=False):
    """Channel configuration (one of webhook, opsgenie, or notification)."""

    type: Literal['webhook', 'opsgenie', 'notification']
    # Webhook-specific
    format: NotRequired[Literal['auto', 'slack-blockkit', 'slack-legacy', 'raw-data']]
    url: NotRequired[str]
    # Opsgenie-specific
    auth_key: NotRequired[str]
    # Notification-specific
    recipients: NotRequired[list[str]]


class ChannelRead(TypedDict):
    """Channel information returned by the API."""

    id: str
    organization_id: str
    label: str
    active: bool
    created_at: str
    updated_at: str | None
    created_by_name: str | None
    updated_by_name: str | None
    config: ChannelConfig


class ChannelCreate(TypedDict):
    """Data for creating a new channel."""

    label: str
    config: ChannelConfig


class ChannelUpdate(TypedDict, total=False):
    """Data for updating a channel."""

    label: NotRequired[str | None]
    config: NotRequired[ChannelConfig | None]
    active: NotRequired[bool | None]


class AlertRead(TypedDict):
    """Alert information returned by the API."""

    id: str
    organization_id: str
    project_id: str
    created_at: str
    updated_at: str | None
    created_by_name: str | None
    updated_by_name: str | None
    name: str
    description: str | None
    query: str
    time_window: str  # ISO 8601 duration
    frequency: str  # ISO 8601 duration
    watermark: str  # ISO 8601 duration
    channels: list[ChannelRead]
    notify_when: NotifyWhen
    active: bool


class AlertWithLastRun(AlertRead):
    """Alert with last run information."""

    last_run: str | None
    has_matches: bool | None
    has_errors: bool | None
    result: Any
    result_length: int | None


class AlertCreate(TypedDict):
    """Data for creating a new alert."""

    name: str
    description: str
    query: str
    time_window: str  # ISO 8601 duration or seconds as string
    frequency: str  # ISO 8601 duration or seconds as string
    watermark: str  # ISO 8601 duration or seconds as string
    channel_ids: list[str]
    notify_when: NotifyWhen


class AlertUpdate(TypedDict, total=False):
    """Data for updating an alert."""

    name: NotRequired[str | None]
    description: NotRequired[str | None]
    query: NotRequired[str | None]
    time_window: NotRequired[str | None]
    frequency: NotRequired[str | None]
    watermark: NotRequired[str | None]
    channel_ids: NotRequired[list[str] | None]
    notify_when: NotRequired[NotifyWhen | None]
    active: NotRequired[bool | None]


class DashboardSummary(TypedDict):
    """Dashboard summary information."""

    id: str
    project_id: str
    created_at: str
    updated_at: str | None
    created_by_name: str | None
    updated_by_name: str | None
    dashboard_name: str
    dashboard_slug: str


class DashboardCreateRequest(TypedDict):
    """Data for creating a new dashboard."""

    name: str
    slug: str
    definition: dict[str, Any]


class DashboardUpdateRequest(TypedDict, total=False):
    """Data for updating a dashboard."""

    name: NotRequired[str | None]
    definition: NotRequired[dict[str, Any] | None]


# ============================================================================
# Helper functions
# ============================================================================


def _timedelta_to_iso8601(td: timedelta) -> str:
    """Convert a timedelta to an ISO 8601 duration string."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = ['PT']
    if hours:
        parts.append(f'{hours}H')
    if minutes:
        parts.append(f'{minutes}M')
    if seconds or not (hours or minutes):
        parts.append(f'{seconds}S')

    return ''.join(parts)


# ============================================================================
# Base client implementation
# ============================================================================

T = TypeVar('T', bound=BaseClient)


class _BaseLogfireAPIClient(Generic[T]):
    """Base class for Logfire API clients."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: Timeout,
        client_cls: type[T],
        **client_kwargs: Any,
    ):
        self.base_url = base_url
        self.api_token = api_token
        self.timeout = timeout
        headers = client_kwargs.pop('headers', {})
        headers['Authorization'] = f'Bearer {api_token}'
        self.client: T = client_cls(timeout=timeout, base_url=base_url, headers=headers, **client_kwargs)

    def _handle_response(self, response: Response) -> Any:
        """Handle response and raise appropriate exceptions for errors."""
        if response.status_code == 204:
            return None

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = response.text

            if response.status_code == 401:
                raise LogfireAPIError('Authentication failed. Check your API token.', response.status_code, body)
            elif response.status_code == 403:
                detail = str(body.get('detail', 'Permission denied')) if isinstance(body, dict) else 'Permission denied'  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                raise LogfireAPIForbiddenError(detail, response.status_code, body)
            elif response.status_code == 404:
                detail = (
                    str(body.get('detail', 'Resource not found')) if isinstance(body, dict) else 'Resource not found'  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                )
                raise LogfireAPINotFoundError(detail, response.status_code, body)
            elif response.status_code == 409:
                detail = str(body.get('detail', 'Resource already exists')) if isinstance(body, dict) else 'Conflict'  # pyright: ignore[reportUnknownArgumentType, reportUnknownMemberType]
                raise LogfireAPIConflictError(str(detail), response.status_code, body)
            elif response.status_code == 422:
                raise LogfireAPIValidationError(f'Validation error: {body}', response.status_code, body)
            elif response.status_code == 429:
                raise LogfireAPIRateLimitError('Rate limit exceeded', response.status_code, body)
            else:
                raise LogfireAPIError(f'API error: {body}', response.status_code, body)

        if response.status_code == 200 or response.status_code == 201:
            return response.json()

        return None


# ============================================================================
# Synchronous client
# ============================================================================
class LogfireAPIClient(_BaseLogfireAPIClient[Client]):
    """Synchronous client for the Logfire public API.

    This client provides methods to interact with the Logfire API for managing
    projects, tokens, alerts, dashboards, and channels.

    Example:
        ```python
        from logfire.api_client import LogfireAPIClient

        # Using environment variable LOGFIRE_API_TOKEN
        client = LogfireAPIClient.from_env()

        # Or with explicit token
        client = LogfireAPIClient(api_token='your-api-token')

        with client:
            projects = client.list_projects()
            for project in projects:
                print(project['project_name'])
        ```
    """

    def __init__(
        self,
        api_token: str,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **client_kwargs: Any,
    ):
        """Initialize a synchronous Logfire API client.

        Args:
            api_token: The API token for authentication.
            base_url: The base URL for the API. If not provided, it will be
                inferred from the token's region.
            timeout: Request timeout. Defaults to 30 seconds.
            **client_kwargs: Additional keyword arguments passed to httpx.Client.
        """
        base_url = base_url or get_base_url_from_token(api_token)
        super().__init__(base_url, api_token, timeout, Client, **client_kwargs)

    @classmethod
    def from_env(
        cls,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **client_kwargs: Any,
    ) -> Self:
        """Create a client using the LOGFIRE_API_TOKEN environment variable.

        Args:
            base_url: The base URL for the API. If not provided, it will be
                inferred from the token's region.
            timeout: Request timeout. Defaults to 30 seconds.
            **client_kwargs: Additional keyword arguments passed to httpx.Client.

        Returns:
            A new LogfireAPIClient instance.

        Raises:
            ValueError: If LOGFIRE_API_TOKEN is not set.
        """
        api_token = os.environ.get(LOGFIRE_API_TOKEN_ENV)
        if not api_token:
            raise ValueError(f'{LOGFIRE_API_TOKEN_ENV} environment variable is not set')
        return cls(api_token=api_token, base_url=base_url, timeout=timeout, **client_kwargs)

    def __enter__(self) -> Self:
        self.client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        self.client.__exit__(exc_type, exc_value, traceback)

    # ========================================================================
    # Projects API
    # ========================================================================

    def list_projects(self) -> list[ProjectRead]:
        """List all projects accessible to the API token.

        Returns:
            A list of projects.

        Required scope: `project:read`
        """
        response = self.client.get('/api/v1/projects/')
        return self._handle_response(response)

    def create_project(
        self,
        project_name: str,
        description: str | None = None,
        visibility: ProjectVisibility = 'public',
    ) -> ProjectRead:
        """Create a new project.

        Args:
            project_name: The name of the project (2-50 characters).
            description: Optional description (max 500 characters).
            visibility: Project visibility ('private' or 'public').

        Returns:
            The created project.

        Required scope: `project:write`
        """
        data: ProjectCreate = {
            'project_name': project_name,
            'visibility': visibility,
        }
        if description is not None:
            data['description'] = description
        response = self.client.post('/api/v1/projects/', json=data)
        return self._handle_response(response)

    def get_project(self, project_id: str | UUID) -> ProjectRead:
        """Get a specific project by ID.

        Args:
            project_id: The project ID.

        Returns:
            The project information.

        Required scope: `project:read`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/')
        return self._handle_response(response)

    def update_project(
        self,
        project_id: str | UUID,
        project_name: str | None = None,
        description: str | None = None,
        visibility: ProjectVisibility | None = None,
    ) -> ProjectRead:
        """Update a project.

        Args:
            project_id: The project ID.
            project_name: New project name.
            description: New description.
            visibility: New visibility setting.

        Returns:
            The updated project.

        Required scope: `project:write`
        """
        data: ProjectUpdate = {}
        if project_name is not None:
            data['project_name'] = project_name
        if description is not None:
            data['description'] = description
        if visibility is not None:
            data['visibility'] = visibility
        response = self.client.put(f'/api/v1/projects/{project_id}/', json=data)
        return self._handle_response(response)

    def delete_project(self, project_id: str | UUID) -> None:
        """Delete a project.

        Args:
            project_id: The project ID.

        Required scope: `project:write`
        """
        response = self.client.delete(f'/api/v1/projects/{project_id}/')
        self._handle_response(response)

    def get_project_by_name(self, project_name: str) -> ProjectRead:
        """Get a project by name.

        Args:
            project_name: The project name.

        Returns:
            The project information.

        Raises:
            LogfireAPINotFoundError: If the project is not found.

        Required scope: `project:read`
        """
        projects = self.list_projects()
        for project in projects:
            if project['project_name'] == project_name:
                return project
        raise LogfireAPINotFoundError(f"Project '{project_name}' not found")

    # ========================================================================
    # Write Tokens API
    # ========================================================================

    def list_write_tokens(self, project_id: str | UUID) -> list[WriteTokenRead]:
        """List write tokens for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of write tokens.

        Required scope: `project:write_token`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/write-tokens/')
        return self._handle_response(response)

    def create_write_token(self, project_id: str | UUID) -> WriteTokenCreated:
        """Create a write token for a project.

        The write token allows you to add data to your project.

        Args:
            project_id: The project ID.

        Returns:
            The created write token with the actual token value.

        Required scope: `project:write_token`
        """
        response = self.client.post(f'/api/v1/projects/{project_id}/write-tokens/')
        return self._handle_response(response)

    def delete_write_token(self, project_id: str | UUID, token_id: str | UUID) -> None:
        """Revoke a write token.

        Args:
            project_id: The project ID.
            token_id: The token ID.

        Required scope: `project:write_token`
        """
        response = self.client.delete(f'/api/v1/projects/{project_id}/write-tokens/{token_id}/')
        self._handle_response(response)

    # ========================================================================
    # Read Tokens API
    # ========================================================================

    def list_read_tokens(self, project_id: str | UUID) -> list[ReadTokenRead]:
        """List read tokens for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of read tokens.

        Required scope: `project:read_token`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/read-tokens/')
        return self._handle_response(response)

    def create_read_token(self, project_id: str | UUID) -> ReadTokenCreated:
        """Create a read token for a project.

        The read token allows you to read data from your project.

        Args:
            project_id: The project ID.

        Returns:
            The created read token with the actual token value.

        Required scope: `project:read_token`
        """
        response = self.client.post(f'/api/v1/projects/{project_id}/read-tokens/')
        return self._handle_response(response)

    def delete_read_token(self, project_id: str | UUID, token_id: str | UUID) -> None:
        """Revoke a read token.

        Args:
            project_id: The project ID.
            token_id: The token ID.

        Required scope: `project:read_token`
        """
        response = self.client.delete(f'/api/v1/projects/{project_id}/read-tokens/{token_id}/')
        self._handle_response(response)

    # ========================================================================
    # Alerts API
    # ========================================================================

    def list_alerts(self, project_id: str | UUID) -> list[AlertWithLastRun]:
        """List alerts for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of alerts with last run information.

        Required scope: `project:read_alert`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/alerts/')
        return self._handle_response(response)

    def create_alert(
        self,
        project_id: str | UUID,
        *,
        name: str,
        description: str,
        query: str,
        time_window: timedelta | str,
        frequency: timedelta | str,
        watermark: timedelta | str,
        channel_ids: list[str | UUID],
        notify_when: NotifyWhen,
    ) -> AlertRead:
        """Create an alert for a project.

        Args:
            project_id: The project ID.
            name: Alert name.
            description: Alert description.
            query: SQL query for the alert.
            time_window: Time window for the query (timedelta or ISO 8601 duration).
            frequency: How often to run the alert (timedelta or ISO 8601 duration).
            watermark: Watermark for the alert (timedelta or ISO 8601 duration).
            channel_ids: List of channel IDs to notify.
            notify_when: When to send notifications.

        Returns:
            The created alert.

        Required scope: `project:write_alert`
        """
        data: AlertCreate = {
            'name': name,
            'description': description,
            'query': query,
            'time_window': _timedelta_to_iso8601(time_window) if isinstance(time_window, timedelta) else time_window,
            'frequency': _timedelta_to_iso8601(frequency) if isinstance(frequency, timedelta) else frequency,
            'watermark': _timedelta_to_iso8601(watermark) if isinstance(watermark, timedelta) else watermark,
            'channel_ids': [str(cid) for cid in channel_ids],
            'notify_when': notify_when,
        }
        response = self.client.post(f'/api/v1/projects/{project_id}/alerts/', json=data)
        return self._handle_response(response)

    def get_alert(self, project_id: str | UUID, alert_id: str | UUID) -> AlertWithLastRun:
        """Get a specific alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.

        Returns:
            The alert information with last run details.

        Required scope: `project:read_alert`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/alerts/{alert_id}/')
        return self._handle_response(response)

    def update_alert(
        self,
        project_id: str | UUID,
        alert_id: str | UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        query: str | None = None,
        time_window: timedelta | str | None = None,
        frequency: timedelta | str | None = None,
        watermark: timedelta | str | None = None,
        channel_ids: list[str | UUID] | None = None,
        notify_when: NotifyWhen | None = None,
        active: bool | None = None,
    ) -> AlertRead:
        """Update an alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.
            name: New alert name.
            description: New description.
            query: New SQL query.
            time_window: New time window.
            frequency: New frequency.
            watermark: New watermark.
            channel_ids: New list of channel IDs.
            notify_when: New notification setting.
            active: Whether the alert is active.

        Returns:
            The updated alert.

        Required scope: `project:write_alert`
        """
        data: AlertUpdate = {}
        if name is not None:
            data['name'] = name
        if description is not None:
            data['description'] = description
        if query is not None:
            data['query'] = query
        if time_window is not None:
            data['time_window'] = (
                _timedelta_to_iso8601(time_window) if isinstance(time_window, timedelta) else time_window
            )
        if frequency is not None:
            data['frequency'] = _timedelta_to_iso8601(frequency) if isinstance(frequency, timedelta) else frequency
        if watermark is not None:
            data['watermark'] = _timedelta_to_iso8601(watermark) if isinstance(watermark, timedelta) else watermark
        if channel_ids is not None:
            data['channel_ids'] = [str(cid) for cid in channel_ids]
        if notify_when is not None:
            data['notify_when'] = notify_when
        if active is not None:
            data['active'] = active
        response = self.client.put(f'/api/v1/projects/{project_id}/alerts/{alert_id}/', json=data)
        return self._handle_response(response)

    def delete_alert(self, project_id: str | UUID, alert_id: str | UUID) -> None:
        """Delete an alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.

        Required scope: `project:write_alert`
        """
        response = self.client.delete(f'/api/v1/projects/{project_id}/alerts/{alert_id}/')
        self._handle_response(response)

    # ========================================================================
    # Channels API
    # ========================================================================

    def list_channels(self) -> list[ChannelRead]:
        """List notification channels for the organization.

        Returns:
            A list of channels.

        Required scope: `organization:read_channel`
        """
        response = self.client.get('/api/v1/channels/')
        return self._handle_response(response)

    def create_channel(self, label: str, config: ChannelConfig) -> ChannelRead:
        """Create a notification channel.

        Args:
            label: Channel label.
            config: Channel configuration.

        Returns:
            The created channel.

        Required scope: `organization:write_channel`
        """
        data: ChannelCreate = {'label': label, 'config': config}
        response = self.client.post('/api/v1/channels/', json=data)
        return self._handle_response(response)

    def get_channel(self, channel_id: str | UUID) -> ChannelRead:
        """Get a specific channel.

        Args:
            channel_id: The channel ID.

        Returns:
            The channel information.

        Required scope: `organization:read_channel`
        """
        response = self.client.get(f'/api/v1/channels/{channel_id}/')
        return self._handle_response(response)

    def update_channel(
        self,
        channel_id: str | UUID,
        *,
        label: str | None = None,
        config: ChannelConfig | None = None,
        active: bool | None = None,
    ) -> ChannelRead:
        """Update a channel.

        Args:
            channel_id: The channel ID.
            label: New label.
            config: New configuration.
            active: Whether the channel is active.

        Returns:
            The updated channel.

        Required scope: `organization:write_channel`
        """
        data: ChannelUpdate = {}
        if label is not None:
            data['label'] = label
        if config is not None:
            data['config'] = config
        if active is not None:
            data['active'] = active
        response = self.client.put(f'/api/v1/channels/{channel_id}/', json=data)
        return self._handle_response(response)

    def delete_channel(self, channel_id: str | UUID) -> None:
        """Delete a channel.

        Args:
            channel_id: The channel ID.

        Required scope: `organization:write_channel`
        """
        response = self.client.delete(f'/api/v1/channels/{channel_id}/')
        self._handle_response(response)

    # ========================================================================
    # Dashboards API
    # ========================================================================

    def list_dashboards(self, project_id: str | UUID) -> list[DashboardSummary]:
        """List dashboards for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of dashboard summaries.

        Required scope: `project:read_dashboard`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/dashboards/')
        return self._handle_response(response)

    def create_dashboard(
        self,
        project_id: str | UUID,
        *,
        name: str,
        slug: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a dashboard.

        Args:
            project_id: The project ID.
            name: Dashboard name.
            slug: Dashboard slug (URL-friendly identifier).
            definition: Dashboard definition.

        Returns:
            The created dashboard.

        Required scope: `project:write_dashboard`
        """
        data: DashboardCreateRequest = {'name': name, 'slug': slug, 'definition': definition}
        response = self.client.post(f'/api/v1/projects/{project_id}/dashboards/', json=data)
        return self._handle_response(response)

    def get_dashboard(self, project_id: str | UUID, dashboard_id: str | UUID) -> dict[str, Any]:
        """Get a specific dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.

        Returns:
            The dashboard information.

        Required scope: `project:read_dashboard`
        """
        response = self.client.get(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/')
        return self._handle_response(response)

    def update_dashboard(
        self,
        project_id: str | UUID,
        dashboard_id: str | UUID,
        *,
        name: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.
            name: New dashboard name.
            definition: New dashboard definition.

        Returns:
            The updated dashboard.

        Required scope: `project:write_dashboard`
        """
        data: DashboardUpdateRequest = {}
        if name is not None:
            data['name'] = name
        if definition is not None:
            data['definition'] = definition
        response = self.client.put(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/', json=data)
        return self._handle_response(response)

    def delete_dashboard(self, project_id: str | UUID, dashboard_id: str | UUID) -> None:
        """Delete a dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.

        Required scope: `project:write_dashboard`
        """
        response = self.client.delete(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/')
        self._handle_response(response)


# ============================================================================
# Asynchronous client
# ============================================================================


class AsyncLogfireAPIClient(_BaseLogfireAPIClient[AsyncClient]):
    """Asynchronous client for the Logfire public API.

    This client provides async methods to interact with the Logfire API for managing
    projects, tokens, alerts, dashboards, and channels.

    Example:
        ```python
        from logfire.api_client import AsyncLogfireAPIClient

        # Using environment variable LOGFIRE_API_TOKEN
        client = AsyncLogfireAPIClient.from_env()

        async with client:
            projects = await client.list_projects()
            for project in projects:
                print(project['project_name'])
        ```
    """

    def __init__(
        self,
        api_token: str,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **client_kwargs: Any,
    ):
        """Initialize an asynchronous Logfire API client.

        Args:
            api_token: The API token for authentication.
            base_url: The base URL for the API. If not provided, it will be
                inferred from the token's region.
            timeout: Request timeout. Defaults to 30 seconds.
            **client_kwargs: Additional keyword arguments passed to httpx.AsyncClient.
        """
        base_url = base_url or get_base_url_from_token(api_token)
        super().__init__(base_url, api_token, timeout, AsyncClient, **client_kwargs)

    @classmethod
    def from_env(
        cls,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **client_kwargs: Any,
    ) -> Self:
        """Create a client using the LOGFIRE_API_TOKEN environment variable.

        Args:
            base_url: The base URL for the API. If not provided, it will be
                inferred from the token's region.
            timeout: Request timeout. Defaults to 30 seconds.
            **client_kwargs: Additional keyword arguments passed to httpx.AsyncClient.

        Returns:
            A new AsyncLogfireAPIClient instance.

        Raises:
            ValueError: If LOGFIRE_API_TOKEN is not set.
        """
        api_token = os.environ.get(LOGFIRE_API_TOKEN_ENV)
        if not api_token:
            raise ValueError(f'{LOGFIRE_API_TOKEN_ENV} environment variable is not set')
        return cls(api_token=api_token, base_url=base_url, timeout=timeout, **client_kwargs)

    async def __aenter__(self) -> Self:
        await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.client.__aexit__(exc_type, exc_value, traceback)

    # ========================================================================
    # Projects API
    # ========================================================================

    async def list_projects(self) -> list[ProjectRead]:
        """List all projects accessible to the API token.

        Returns:
            A list of projects.

        Required scope: `project:read`
        """
        response = await self.client.get('/api/v1/projects/')
        return self._handle_response(response)

    async def create_project(
        self,
        project_name: str,
        description: str | None = None,
        visibility: ProjectVisibility = 'public',
    ) -> ProjectRead:
        """Create a new project.

        Args:
            project_name: The name of the project (2-50 characters).
            description: Optional description (max 500 characters).
            visibility: Project visibility ('private' or 'public').

        Returns:
            The created project.

        Required scope: `project:write`
        """
        data: ProjectCreate = {
            'project_name': project_name,
            'visibility': visibility,
        }
        if description is not None:
            data['description'] = description
        response = await self.client.post('/api/v1/projects/', json=data)
        return self._handle_response(response)

    async def get_project(self, project_id: str | UUID) -> ProjectRead:
        """Get a specific project by ID.

        Args:
            project_id: The project ID.

        Returns:
            The project information.

        Required scope: `project:read`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/')
        return self._handle_response(response)

    async def update_project(
        self,
        project_id: str | UUID,
        project_name: str | None = None,
        description: str | None = None,
        visibility: ProjectVisibility | None = None,
    ) -> ProjectRead:
        """Update a project.

        Args:
            project_id: The project ID.
            project_name: New project name.
            description: New description.
            visibility: New visibility setting.

        Returns:
            The updated project.

        Required scope: `project:write`
        """
        data: ProjectUpdate = {}
        if project_name is not None:
            data['project_name'] = project_name
        if description is not None:
            data['description'] = description
        if visibility is not None:
            data['visibility'] = visibility
        response = await self.client.put(f'/api/v1/projects/{project_id}/', json=data)
        return self._handle_response(response)

    async def delete_project(self, project_id: str | UUID) -> None:
        """Delete a project.

        Args:
            project_id: The project ID.

        Required scope: `project:write`
        """
        response = await self.client.delete(f'/api/v1/projects/{project_id}/')
        self._handle_response(response)

    async def get_project_by_name(self, project_name: str) -> ProjectRead:
        """Get a project by name.

        Args:
            project_name: The project name.

        Returns:
            The project information.

        Raises:
            LogfireAPINotFoundError: If the project is not found.

        Required scope: `project:read`
        """
        projects = await self.list_projects()
        for project in projects:
            if project['project_name'] == project_name:
                return project
        raise LogfireAPINotFoundError(f"Project '{project_name}' not found")

    # ========================================================================
    # Write Tokens API
    # ========================================================================

    async def list_write_tokens(self, project_id: str | UUID) -> list[WriteTokenRead]:
        """List write tokens for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of write tokens.

        Required scope: `project:write_token`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/write-tokens/')
        return self._handle_response(response)

    async def create_write_token(self, project_id: str | UUID) -> WriteTokenCreated:
        """Create a write token for a project.

        The write token allows you to add data to your project.

        Args:
            project_id: The project ID.

        Returns:
            The created write token with the actual token value.

        Required scope: `project:write_token`
        """
        response = await self.client.post(f'/api/v1/projects/{project_id}/write-tokens/')
        return self._handle_response(response)

    async def delete_write_token(self, project_id: str | UUID, token_id: str | UUID) -> None:
        """Revoke a write token.

        Args:
            project_id: The project ID.
            token_id: The token ID.

        Required scope: `project:write_token`
        """
        response = await self.client.delete(f'/api/v1/projects/{project_id}/write-tokens/{token_id}/')
        self._handle_response(response)

    # ========================================================================
    # Read Tokens API
    # ========================================================================

    async def list_read_tokens(self, project_id: str | UUID) -> list[ReadTokenRead]:
        """List read tokens for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of read tokens.

        Required scope: `project:read_token`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/read-tokens/')
        return self._handle_response(response)

    async def create_read_token(self, project_id: str | UUID) -> ReadTokenCreated:
        """Create a read token for a project.

        The read token allows you to read data from your project.

        Args:
            project_id: The project ID.

        Returns:
            The created read token with the actual token value.

        Required scope: `project:read_token`
        """
        response = await self.client.post(f'/api/v1/projects/{project_id}/read-tokens/')
        return self._handle_response(response)

    async def delete_read_token(self, project_id: str | UUID, token_id: str | UUID) -> None:
        """Revoke a read token.

        Args:
            project_id: The project ID.
            token_id: The token ID.

        Required scope: `project:read_token`
        """
        response = await self.client.delete(f'/api/v1/projects/{project_id}/read-tokens/{token_id}/')
        self._handle_response(response)

    # ========================================================================
    # Alerts API
    # ========================================================================

    async def list_alerts(self, project_id: str | UUID) -> list[AlertWithLastRun]:
        """List alerts for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of alerts with last run information.

        Required scope: `project:read_alert`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/alerts/')
        return self._handle_response(response)

    async def create_alert(
        self,
        project_id: str | UUID,
        *,
        name: str,
        description: str,
        query: str,
        time_window: timedelta | str,
        frequency: timedelta | str,
        watermark: timedelta | str,
        channel_ids: list[str | UUID],
        notify_when: NotifyWhen,
    ) -> AlertRead:
        """Create an alert for a project.

        Args:
            project_id: The project ID.
            name: Alert name.
            description: Alert description.
            query: SQL query for the alert.
            time_window: Time window for the query (timedelta or ISO 8601 duration).
            frequency: How often to run the alert (timedelta or ISO 8601 duration).
            watermark: Watermark for the alert (timedelta or ISO 8601 duration).
            channel_ids: List of channel IDs to notify.
            notify_when: When to send notifications.

        Returns:
            The created alert.

        Required scope: `project:write_alert`
        """
        data: AlertCreate = {
            'name': name,
            'description': description,
            'query': query,
            'time_window': _timedelta_to_iso8601(time_window) if isinstance(time_window, timedelta) else time_window,
            'frequency': _timedelta_to_iso8601(frequency) if isinstance(frequency, timedelta) else frequency,
            'watermark': _timedelta_to_iso8601(watermark) if isinstance(watermark, timedelta) else watermark,
            'channel_ids': [str(cid) for cid in channel_ids],
            'notify_when': notify_when,
        }
        response = await self.client.post(f'/api/v1/projects/{project_id}/alerts/', json=data)
        return self._handle_response(response)

    async def get_alert(self, project_id: str | UUID, alert_id: str | UUID) -> AlertWithLastRun:
        """Get a specific alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.

        Returns:
            The alert information with last run details.

        Required scope: `project:read_alert`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/alerts/{alert_id}/')
        return self._handle_response(response)

    async def update_alert(
        self,
        project_id: str | UUID,
        alert_id: str | UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        query: str | None = None,
        time_window: timedelta | str | None = None,
        frequency: timedelta | str | None = None,
        watermark: timedelta | str | None = None,
        channel_ids: list[str | UUID] | None = None,
        notify_when: NotifyWhen | None = None,
        active: bool | None = None,
    ) -> AlertRead:
        """Update an alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.
            name: New alert name.
            description: New description.
            query: New SQL query.
            time_window: New time window.
            frequency: New frequency.
            watermark: New watermark.
            channel_ids: New list of channel IDs.
            notify_when: New notification setting.
            active: Whether the alert is active.

        Returns:
            The updated alert.

        Required scope: `project:write_alert`
        """
        data: AlertUpdate = {}
        if name is not None:
            data['name'] = name
        if description is not None:
            data['description'] = description
        if query is not None:
            data['query'] = query
        if time_window is not None:
            data['time_window'] = (
                _timedelta_to_iso8601(time_window) if isinstance(time_window, timedelta) else time_window
            )
        if frequency is not None:
            data['frequency'] = _timedelta_to_iso8601(frequency) if isinstance(frequency, timedelta) else frequency
        if watermark is not None:
            data['watermark'] = _timedelta_to_iso8601(watermark) if isinstance(watermark, timedelta) else watermark
        if channel_ids is not None:
            data['channel_ids'] = [str(cid) for cid in channel_ids]
        if notify_when is not None:
            data['notify_when'] = notify_when
        if active is not None:
            data['active'] = active
        response = await self.client.put(f'/api/v1/projects/{project_id}/alerts/{alert_id}/', json=data)
        return self._handle_response(response)

    async def delete_alert(self, project_id: str | UUID, alert_id: str | UUID) -> None:
        """Delete an alert.

        Args:
            project_id: The project ID.
            alert_id: The alert ID.

        Required scope: `project:write_alert`
        """
        response = await self.client.delete(f'/api/v1/projects/{project_id}/alerts/{alert_id}/')
        self._handle_response(response)

    # ========================================================================
    # Channels API
    # ========================================================================

    async def list_channels(self) -> list[ChannelRead]:
        """List notification channels for the organization.

        Returns:
            A list of channels.

        Required scope: `organization:read_channel`
        """
        response = await self.client.get('/api/v1/channels/')
        return self._handle_response(response)

    async def create_channel(self, label: str, config: ChannelConfig) -> ChannelRead:
        """Create a notification channel.

        Args:
            label: Channel label.
            config: Channel configuration.

        Returns:
            The created channel.

        Required scope: `organization:write_channel`
        """
        data: ChannelCreate = {'label': label, 'config': config}
        response = await self.client.post('/api/v1/channels/', json=data)
        return self._handle_response(response)

    async def get_channel(self, channel_id: str | UUID) -> ChannelRead:
        """Get a specific channel.

        Args:
            channel_id: The channel ID.

        Returns:
            The channel information.

        Required scope: `organization:read_channel`
        """
        response = await self.client.get(f'/api/v1/channels/{channel_id}/')
        return self._handle_response(response)

    async def update_channel(
        self,
        channel_id: str | UUID,
        *,
        label: str | None = None,
        config: ChannelConfig | None = None,
        active: bool | None = None,
    ) -> ChannelRead:
        """Update a channel.

        Args:
            channel_id: The channel ID.
            label: New label.
            config: New configuration.
            active: Whether the channel is active.

        Returns:
            The updated channel.

        Required scope: `organization:write_channel`
        """
        data: ChannelUpdate = {}
        if label is not None:
            data['label'] = label
        if config is not None:
            data['config'] = config
        if active is not None:
            data['active'] = active
        response = await self.client.put(f'/api/v1/channels/{channel_id}/', json=data)
        return self._handle_response(response)

    async def delete_channel(self, channel_id: str | UUID) -> None:
        """Delete a channel.

        Args:
            channel_id: The channel ID.

        Required scope: `organization:write_channel`
        """
        response = await self.client.delete(f'/api/v1/channels/{channel_id}/')
        self._handle_response(response)

    # ========================================================================
    # Dashboards API
    # ========================================================================

    async def list_dashboards(self, project_id: str | UUID) -> list[DashboardSummary]:
        """List dashboards for a project.

        Args:
            project_id: The project ID.

        Returns:
            A list of dashboard summaries.

        Required scope: `project:read_dashboard`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/dashboards/')
        return self._handle_response(response)

    async def create_dashboard(
        self,
        project_id: str | UUID,
        *,
        name: str,
        slug: str,
        definition: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a dashboard.

        Args:
            project_id: The project ID.
            name: Dashboard name.
            slug: Dashboard slug (URL-friendly identifier).
            definition: Dashboard definition.

        Returns:
            The created dashboard.

        Required scope: `project:write_dashboard`
        """
        data: DashboardCreateRequest = {'name': name, 'slug': slug, 'definition': definition}
        response = await self.client.post(f'/api/v1/projects/{project_id}/dashboards/', json=data)
        return self._handle_response(response)

    async def get_dashboard(self, project_id: str | UUID, dashboard_id: str | UUID) -> dict[str, Any]:
        """Get a specific dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.

        Returns:
            The dashboard information.

        Required scope: `project:read_dashboard`
        """
        response = await self.client.get(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/')
        return self._handle_response(response)

    async def update_dashboard(
        self,
        project_id: str | UUID,
        dashboard_id: str | UUID,
        *,
        name: str | None = None,
        definition: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.
            name: New dashboard name.
            definition: New dashboard definition.

        Returns:
            The updated dashboard.

        Required scope: `project:write_dashboard`
        """
        data: DashboardUpdateRequest = {}
        if name is not None:
            data['name'] = name
        if definition is not None:
            data['definition'] = definition
        response = await self.client.put(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/', json=data)
        return self._handle_response(response)

    async def delete_dashboard(self, project_id: str | UUID, dashboard_id: str | UUID) -> None:
        """Delete a dashboard.

        Args:
            project_id: The project ID.
            dashboard_id: The dashboard ID or slug.

        Required scope: `project:write_dashboard`
        """
        response = await self.client.delete(f'/api/v1/projects/{project_id}/dashboards/{dashboard_id}/')
        self._handle_response(response)
