"""Tests for the Logfire API client."""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from unittest.mock import patch

import pytest
from inline_snapshot import snapshot

from logfire.api_client import (
    LOGFIRE_API_TOKEN_ENV,
    AsyncLogfireAPIClient,
    LogfireAPIClient,
    LogfireAPIError,
    LogfireAPIForbiddenError,
    LogfireAPINotFoundError,
    LogfireAPIRateLimitError,
    LogfireAPIValidationError,
)

# This file is intended to be updated by the Logfire developers, with the development platform running locally.
# To update, set the `CLIENT_BASE_URL` and `CLIENT_API_TOKEN` values to match the local development environment,
# and run the tests with `--record-mode=rewrite --inline-snapshot=fix` to update the cassettes and snapshots.
CLIENT_BASE_URL = 'http://localhost:8000/'
CLIENT_API_TOKEN = 'pylf_v1_local_test_api_token'

pytestmark = [
    pytest.mark.vcr(),
    pytest.mark.skipif(
        sys.version_info < (3, 10),
        reason='vcr is not compatible with latest urllib3 on python<3.10, '
        'see https://github.com/kevin1024/vcrpy/issues/688.',
    ),
]


# =============================================================================
# Token/Base URL inference tests (don't need VCR)
# =============================================================================


@pytest.mark.parametrize('client_class', [AsyncLogfireAPIClient, LogfireAPIClient])
@pytest.mark.parametrize(
    ['token', 'expected'],
    [
        ('pylf_v1_us_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-us.pydantic.dev'),
        ('pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-eu.pydantic.dev'),
        ('0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W', 'https://logfire-us.pydantic.dev'),
    ],
)
def test_infers_base_url_from_token(
    client_class: type[AsyncLogfireAPIClient | LogfireAPIClient], token: str, expected: str
):
    """Test that base URL is correctly inferred from token region."""
    client = client_class(api_token=token)
    assert client.base_url == expected


def test_from_env_raises_when_no_token():
    """Test that from_env raises ValueError when no token is set."""
    with patch.dict(os.environ, {}, clear=True):
        # Make sure the env var is not set
        os.environ.pop(LOGFIRE_API_TOKEN_ENV, None)
        with pytest.raises(ValueError, match='LOGFIRE_API_TOKEN environment variable is not set'):
            LogfireAPIClient.from_env()


def test_from_env_uses_env_var():
    """Test that from_env uses the LOGFIRE_API_TOKEN environment variable."""
    test_token = 'pylf_v1_us_test_token_12345'
    with patch.dict(os.environ, {LOGFIRE_API_TOKEN_ENV: test_token}):
        client = LogfireAPIClient.from_env()
        assert client.api_token == test_token
        assert client.base_url == 'https://logfire-us.pydantic.dev'


def test_explicit_base_url_overrides_token():
    """Test that explicit base_url overrides token-based inference."""
    client = LogfireAPIClient(
        api_token='pylf_v1_us_test_token',
        base_url='https://custom.example.com',
    )
    assert client.base_url == 'https://custom.example.com'


# =============================================================================
# Integration tests using VCR cassettes
# =============================================================================


def test_list_projects_sync():
    """Test listing projects with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        projects = client.list_projects()
        assert isinstance(projects, list)
        # The actual content depends on the recorded cassette
        assert projects == snapshot(
            [
                {
                    'id': '00000000-0000-0000-0000-000000000001',
                    'project_name': 'test-project',
                    'created_at': '2024-01-01T00:00:00Z',
                    'description': 'Test project',
                    'organization_name': 'test-org',
                    'visibility': 'private',
                }
            ]
        )


@pytest.mark.anyio
async def test_list_projects_async():
    """Test listing projects with async client."""
    async with AsyncLogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        projects = await client.list_projects()
        assert isinstance(projects, list)
        assert projects == snapshot(
            [
                {
                    'id': '00000000-0000-0000-0000-000000000001',
                    'project_name': 'test-project',
                    'created_at': '2024-01-01T00:00:00Z',
                    'description': 'Test project',
                    'organization_name': 'test-org',
                    'visibility': 'private',
                }
            ]
        )


def test_get_project_by_name_sync():
    """Test getting a project by name with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        assert project['project_name'] == 'test-project'


def test_get_project_by_name_not_found_sync():
    """Test that get_project_by_name raises NotFoundError for missing projects."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPINotFoundError, match="Project 'nonexistent' not found"):
            client.get_project_by_name('nonexistent')


def test_create_write_token_sync():
    """Test creating a write token with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        write_token = client.create_write_token(project['id'])
        assert 'token' in write_token
        assert 'id' in write_token
        assert write_token == snapshot(
            {
                'id': '00000000-0000-0000-0000-000000000002',
                'project_id': '00000000-0000-0000-0000-000000000001',
                'created_at': '2024-01-01T00:00:00Z',
                'description': 'Created by Public API',
                'token': 'pylf_v1_us_new_write_token',
            }
        )


def test_list_write_tokens_sync():
    """Test listing write tokens with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        tokens = client.list_write_tokens(project['id'])
        assert isinstance(tokens, list)


def test_create_read_token_sync():
    """Test creating a read token with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        read_token = client.create_read_token(project['id'])
        assert 'token' in read_token
        assert 'id' in read_token


def test_list_channels_sync():
    """Test listing notification channels with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        channels = client.list_channels()
        assert isinstance(channels, list)


def test_list_alerts_sync():
    """Test listing alerts with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        alerts = client.list_alerts(project['id'])
        assert isinstance(alerts, list)


def test_list_dashboards_sync():
    """Test listing dashboards with sync client."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        project = client.get_project_by_name('test-project')
        dashboards = client.list_dashboards(project['id'])
        assert isinstance(dashboards, list)


# =============================================================================
# Error handling tests
# =============================================================================


def test_unauthorized_error():
    """Test that 401 errors raise LogfireAPIError."""
    with LogfireAPIClient(api_token='invalid_token', base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPIError, match='Authentication failed'):
            client.list_projects()


def test_forbidden_error():
    """Test that 403 errors raise LogfireAPIForbiddenError."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPIForbiddenError):
            # This should fail if the token doesn't have the required scope
            client.delete_project('00000000-0000-0000-0000-000000000001')


def test_not_found_error():
    """Test that 404 errors raise LogfireAPINotFoundError."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPINotFoundError):
            client.get_project('00000000-0000-0000-0000-nonexistent')


def test_validation_error():
    """Test that 422 errors raise LogfireAPIValidationError."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPIValidationError, match='Validation error'):
            # Project name too short
            client.create_project(project_name='x')


def test_rate_limit_error():
    """Test that 429 errors raise LogfireAPIRateLimitError."""
    with LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL) as client:
        with pytest.raises(LogfireAPIRateLimitError):
            client.list_projects()


# =============================================================================
# Context manager tests
# =============================================================================


def test_sync_context_manager():
    """Test that sync client works as context manager."""
    client = LogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL)

    with client:
        # Client should be usable inside context
        projects = client.list_projects()
        assert isinstance(projects, list)

    # After context, client should be closed (but still accessible)
    assert client.client is not None


@pytest.mark.anyio
async def test_async_context_manager():
    """Test that async client works as context manager."""
    client = AsyncLogfireAPIClient(api_token=CLIENT_API_TOKEN, base_url=CLIENT_BASE_URL)

    async with client:
        # Client should be usable inside context
        projects = await client.list_projects()
        assert isinstance(projects, list)

    # After context, client should be closed (but still accessible)
    assert client.client is not None


# =============================================================================
# logfire.api_client() method tests
# =============================================================================


def test_logfire_api_client_method_no_token():
    """Test that logfire.api_client() raises error when no token is available."""
    import logfire

    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop(LOGFIRE_API_TOKEN_ENV, None)
        with pytest.raises(ValueError, match='No API token available'):
            logfire.api_client()


def test_logfire_api_client_method_with_env_var():
    """Test that logfire.api_client() uses LOGFIRE_API_TOKEN env var."""
    import logfire

    test_token = 'pylf_v1_us_test_token_12345'
    with patch.dict(os.environ, {LOGFIRE_API_TOKEN_ENV: test_token}):
        client = logfire.api_client()
        assert client.api_token == test_token


def test_logfire_api_client_method_with_explicit_token():
    """Test that logfire.api_client() accepts explicit token."""
    import logfire

    test_token = 'pylf_v1_eu_0kYhc414Ys2FNDRdt5vFB05xFx5NjVcbcBMy4Kp6PH0W'
    client = logfire.api_client(api_token=test_token)
    assert client.api_token == test_token
    assert client.base_url == 'https://logfire-eu.pydantic.dev'


# =============================================================================
# Timedelta conversion tests
# =============================================================================


def test_timedelta_to_iso8601():
    """Test that timedelta values are properly converted to ISO 8601 format."""
    from logfire.api_client import _timedelta_to_iso8601  # pyright: ignore[reportPrivateUsage]

    assert _timedelta_to_iso8601(timedelta(hours=1)) == 'PT1H'
    assert _timedelta_to_iso8601(timedelta(minutes=30)) == 'PT30M'
    assert _timedelta_to_iso8601(timedelta(seconds=45)) == 'PT45S'
    assert _timedelta_to_iso8601(timedelta(hours=1, minutes=30)) == 'PT1H30M'
    assert _timedelta_to_iso8601(timedelta(hours=1, minutes=30, seconds=45)) == 'PT1H30M45S'
    assert _timedelta_to_iso8601(timedelta(seconds=0)) == 'PT0S'
