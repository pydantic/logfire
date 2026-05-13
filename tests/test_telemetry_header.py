from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import requests
import requests_mock

import logfire
from logfire._internal.client import UA_HEADER
from logfire._internal.config import GLOBAL_CONFIG, LogfireCredentials
from logfire._internal.telemetry_header import TELEMETRY_HEADER_NAME, build_telemetry_header
from logfire.version import VERSION


def _parse_header(value: str) -> dict[str, Any]:
    return json.loads(value)


def test_build_telemetry_header_without_config_is_none():
    assert build_telemetry_header() is None


def test_build_telemetry_header_with_config():
    header = build_telemetry_header(GLOBAL_CONFIG)
    assert header is not None
    pairs = _parse_header(header)
    for key in ('code_source_set', 'variables_set', 'token_count'):
        assert key in pairs


def test_telemetry_header_excludes_secrets():
    """The header must never carry the token, api key, environment or service name."""
    secrets = ['shhh-secret-token', 'secret-api-key', 'top-secret-env', 'secret-service-name']
    with patch.dict('os.environ', {}, clear=False):
        logfire.configure(
            send_to_logfire=False,
            token=secrets[0],
            api_key=secrets[1],
            environment=secrets[2],
            service_name=secrets[3],
            console=False,
        )
    try:
        header = build_telemetry_header(GLOBAL_CONFIG)
        assert header is not None
        for secret in secrets:
            assert secret not in header
    finally:
        # Reset to the default test config.
        logfire.configure(send_to_logfire=False, console=False)


def test_user_agent_carries_sdk_identity():
    assert UA_HEADER.startswith(f'logfire-sdk-python/{VERSION} (')
    assert 'os ' in UA_HEADER
    assert 'arch ' in UA_HEADER


def test_otlp_export_sends_telemetry_header():
    captured: list[dict[str, str]] = []

    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        def _capture(request: requests.PreparedRequest, _context: object) -> str:
            captured.append(dict(request.headers))
            return ''

        m.post('https://logfire-us.pydantic.dev/v1/traces', text=_capture, status_code=200)

        logfire.configure(send_to_logfire=True, token='abc1', console=False)
        for thread in __import__('threading').enumerate():
            if thread.name == 'check_logfire_token':  # pragma: no cover
                thread.join()

        with logfire.span('a span'):
            pass
        logfire.force_flush()

    assert any(TELEMETRY_HEADER_NAME in headers for headers in captured)
    [headers] = [headers for headers in captured if TELEMETRY_HEADER_NAME in headers]
    pairs = _parse_header(headers[TELEMETRY_HEADER_NAME])
    assert pairs['token_count'] == 1
    assert 'abc1' not in headers[TELEMETRY_HEADER_NAME]
    # SDK identity travels on User-Agent, not the telemetry header.
    assert 'sdk_version' not in pairs
    assert headers['User-Agent'].startswith(f'logfire-sdk-python/{VERSION}')
    # The header must advertise the same `service.instance.id` carried by OTLP
    # resource attributes so the backend can correlate the two.
    resource = GLOBAL_CONFIG.get_tracer_provider().resource
    assert pairs['service_instance_id'] == resource.attributes['service.instance.id']


def test_from_token_sends_telemetry_header():
    with requests_mock.Mocker() as m:
        m.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )
        session = requests.Session()
        LogfireCredentials.from_token(
            'pylf_v1_us_xxx', session, 'https://logfire-us.pydantic.dev', telemetry_header='{"token_count":1}'
        )
        [history] = m.request_history
        assert history.headers[TELEMETRY_HEADER_NAME] == '{"token_count":1}'
