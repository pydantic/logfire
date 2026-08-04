from __future__ import annotations

import re
import shlex
from contextlib import ExitStack
from importlib.metadata import version as package_version
from pathlib import Path
from unittest.mock import patch

import pytest
import requests_mock
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

import logfire
from logfire._internal.auth import UserToken
from logfire._internal.cli import main
from logfire._internal.client import UA_HEADER, LogfireClient
from logfire._internal.config import LogfireCredentials
from logfire._internal.exporters.otlp import OTLP_EXPORTER_UA_HEADER
from logfire.experimental.api_client import AsyncLogfireAPIClient, LogfireAPIClient
from logfire.experimental.query_client import LogfireQueryClient
from logfire.version import VERSION

from .test_configure import wait_for_check_token_thread


def test_ua_header_is_a_low_cardinality_product_token() -> None:
    assert UA_HEADER == f'logfire-python/{VERSION}'
    # A single RFC 9110 product token, matching the other SDKs (`logfire-js/<v>`, `logfire-rust/<v>`).
    # No parenthesised platform details: runtime/OS info belongs in resource attributes, and keeping
    # the User-Agent low-cardinality keeps it usable for filtering and aggregation.
    assert re.fullmatch(r'logfire-python/[\w.+-]+', UA_HEADER)


def test_otlp_ua_header_retains_upstream_exporter_identifier() -> None:
    """The OTLP User-Agent must be `<our product token> <upstream exporter's default User-Agent>`.

    The OTLP exporter spec recommends that a distribution's identifier is prepended while the
    exporter's own identifier is retained:
    https://opentelemetry.io/docs/specs/otel/protocol/exporter/#user-agent

    Since the upstream exporter drops its default User-Agent when custom headers are supplied, we
    rebuild it from the installed package version. Comparing against a freshly constructed
    exporter's actual default guards against the upstream format drifting.
    """
    upstream_default = str(OTLPSpanExporter()._session.headers['User-Agent'])  # type: ignore[reportPrivateUsage]
    assert OTLP_EXPORTER_UA_HEADER == f'{UA_HEADER} {upstream_default}'
    assert upstream_default == (
        f'OTel-OTLP-Exporter-Python/{package_version("opentelemetry-exporter-otlp-proto-http")}'
    )


def test_configure_sends_expected_user_agents() -> None:
    request_mocker = requests_mock.Mocker()
    request_mocker.get(
        'https://logfire-us.pydantic.dev/v1/info',
        json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
    )
    request_mocker.post('https://logfire-us.pydantic.dev/v1/traces')

    with request_mocker:
        logfire.configure(send_to_logfire=True, token='abc1', console=False, metrics=False)
        wait_for_check_token_thread()
        logfire.info('test')
        logfire.force_flush()

    requests_by_path = {request.path: request for request in request_mocker.request_history}
    # Plain API requests carry the SDK product token alone; OTLP exports also retain the
    # upstream exporter's identifier.
    assert requests_by_path['/v1/info'].headers['User-Agent'] == UA_HEADER
    assert requests_by_path['/v1/traces'].headers['User-Agent'] == OTLP_EXPORTER_UA_HEADER


def test_logfire_client_user_agent() -> None:
    client = LogfireClient(UserToken(token='123', base_url='http://localhost', expiration='2099-12-31T23:59:59'))
    assert client._session.headers['User-Agent'] == UA_HEADER  # type: ignore[reportPrivateUsage]


def test_datasets_api_client_user_agent() -> None:
    with LogfireAPIClient(api_key='test-key', base_url='http://localhost') as client:
        assert client.client.headers.get_list('user-agent') == [UA_HEADER]


@pytest.mark.anyio
async def test_async_datasets_api_client_user_agent() -> None:
    async with AsyncLogfireAPIClient(api_key='test-key', base_url='http://localhost') as client:
        assert client.client.headers.get_list('user-agent') == [UA_HEADER]


def test_query_client_user_agent() -> None:
    with LogfireQueryClient('fake-read-token') as client:
        assert client.client.headers.get_list('user-agent') == [UA_HEADER]


def test_query_client_user_agent_caller_override() -> None:
    # A caller-supplied user-agent wins regardless of key casing, and exactly one entry is sent:
    # a plain-dict `setdefault('user-agent', ...)` next to a caller's `'User-Agent'` key would
    # produce two entries, which httpx sends as duplicate headers.
    with LogfireQueryClient('fake-read-token', headers={'User-Agent': 'my-agent/1.0'}) as client:
        assert client.client.headers.get_list('user-agent') == ['my-agent/1.0']


def test_cli_requests_user_agent(tmp_dir_cwd: Path) -> None:
    LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://logfire-us.pydantic.dev',
    ).write_creds_file(tmp_dir_cwd)
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(token='123', base_url='http://localhost', expiration='2099-12-31T23:59:59'),
            )
        )
        request_mocker = requests_mock.Mocker()
        stack.enter_context(request_mocker)
        request_mocker.get('http://localhost/v1/account/me', json={'name': 'test-user'})

        main(shlex.split(f'--base-url=http://localhost:0 whoami --data-dir {tmp_dir_cwd}'))

    assert request_mocker.request_history
    for request in request_mocker.request_history:
        assert request.headers['User-Agent'] == UA_HEADER
