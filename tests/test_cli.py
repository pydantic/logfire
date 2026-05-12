from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
import types
import webbrowser
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine, Generator
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock, call, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import requests_mock
from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire._internal.cli
import logfire._internal.cli.ai_tools as ai_tools
import logfire._internal.cli.gateway as gateway_cli
import logfire._internal.cli.gateway_auth as gateway_auth
from logfire import VERSION
from logfire._internal.auth import UserToken
from logfire._internal.cli import OrgProjectAction, SplitArgs, main
from logfire._internal.cli.run import (
    find_recommended_instrumentations_to_install,
    get_recommendation_texts,
    instrument_packages,
    instrumented_packages_text,
)
from logfire._internal.config import LogfireCredentials, sanitize_project_name
from logfire.exceptions import LogfireConfigError
from tests.import_used_for_tests import run_script_test


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://logfire-us.pydantic.dev',
    )


def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert 'usage: logfire [-h] [--version] [--base-url BASE_URL | --region {us,eu}]  ...' in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    main(['--version'])
    assert VERSION in capsys.readouterr().out.strip()


def test_nice_interrupt(capsys: pytest.CaptureFixture[str]) -> None:
    with patch('logfire._internal.cli._main', side_effect=KeyboardInterrupt):
        try:
            main([])
        except SystemExit:
            pass
        assert capsys.readouterr().err == 'User cancelled.\n'


def test_whoami_token_env_var(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {'LOGFIRE_TOKEN': 'foobar'}), requests_mock.Mocker() as request_mocker:
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        main(['whoami'])

        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'


def test_whoami_eu_token_env_var(capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {'LOGFIRE_TOKEN': 'pylf_v1_eu_foobar'}), requests_mock.Mocker() as request_mocker:
        request_mocker.get(
            'https://logfire-eu.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        main(['whoami'])

        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'


def test_whoami_multiple_tokens(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.dict(os.environ, {'LOGFIRE_TOKEN': 'pylf_v1_us_token1,pylf_v1_eu_token2'}),
        requests_mock.Mocker() as request_mocker,
    ):
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'project1', 'project_url': 'https://logfire-us.pydantic.dev/project1'},
        )
        request_mocker.get(
            'https://logfire-eu.pydantic.dev/v1/info',
            json={'project_name': 'project2', 'project_url': 'https://logfire-eu.pydantic.dev/project2'},
        )

        main(['whoami'])

        assert len(request_mocker.request_history) == 2
        output_lines = capsys.readouterr().err.splitlines()
        assert output_lines == [
            'Token 1 of 2:',
            'Logfire project URL: https://logfire-us.pydantic.dev/project1',
            '',
            'Token 2 of 2:',
            'Logfire project URL: https://logfire-eu.pydantic.dev/project2',
        ]


def test_whoami(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {'LOGFIRE_TOKEN': 'foobar'}), requests_mock.Mocker() as request_mocker:
        # Also test LOGFIRE_TOKEN being set but the API being healthy, so it can't be checked
        request_mocker.get('http://localhost/v1/info', status_code=500)

        logfire_credentials.write_creds_file(tmp_dir_cwd)

        with pytest.warns(
            UserWarning, match='Logfire API returned status code 500, you may have trouble sending data.'
        ):
            main(shlex.split(f'--base-url=http://localhost:0 whoami --data-dir {tmp_dir_cwd}'))

        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err.splitlines() == snapshot(
            [
                'Not logged in. Run `logfire auth` to log in.',
                IsStr(regex=rf'^Credentials loaded from data dir: {tmp_dir_cwd}'),
                '',
                'Logfire project URL: https://dashboard.logfire.dev',
            ]
        )


def test_whoami_without_data(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Change to the temp dir so the test doesn't fail if executed from a folder containing logfire credentials.
    current_dir = os.getcwd()
    os.chdir(tmp_dir_cwd)
    try:
        main(['--base-url=http://localhost:0', 'whoami'])
    except SystemExit as e:
        assert e.code == 1
        assert capsys.readouterr().err.splitlines() == snapshot(
            [
                'Not logged in. Run `logfire auth` to log in.',
                IsStr(regex=r'No Logfire credentials found in .*/\.logfire'),
            ]
        )
    finally:
        os.chdir(current_dir)


def test_whoami_logged_in(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(token='123', base_url='http://localhost', expiration='2099-12-31T23:59:59'),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)

        m.get('http://localhost/v1/account/me', json={'name': 'test-user'})

        main(shlex.split(f'--base-url=http://localhost:0 whoami --data-dir {tmp_dir_cwd}'))
    assert capsys.readouterr().err.splitlines() == snapshot(
        [
            'Logged in as: test-user',
            IsStr(regex=rf'^Credentials loaded from data dir: {tmp_dir_cwd}'),
            '',
            'Logfire project URL: https://dashboard.logfire.dev',
        ]
    )


def test_whoami_default_dir(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['--base-url=http://localhost:0', 'whoami'])
    assert capsys.readouterr().err.splitlines() == snapshot(
        [
            'Not logged in. Run `logfire auth` to log in.',
            IsStr(regex=r'^Credentials loaded from data dir: .*/\.logfire$'),
            '',
            'Logfire project URL: https://dashboard.logfire.dev',
        ]
    )


def test_whoami_no_token_no_url(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / 'default.toml'
    with patch('logfire._internal.auth.DEFAULT_FILE', auth_file), pytest.raises(SystemExit):
        main(['whoami'])

        assert 'Not logged in. Run `logfire auth` to log in.' in capsys.readouterr().err


@pytest.mark.parametrize(
    'confirm,output',
    [
        ('y', 'Cleaned Logfire data.\n'),
        ('yes', 'Cleaned Logfire data.\n'),
        ('n', 'Clean aborted.\n'),
    ],
)
def test_clean(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    confirm: str,
    output: str,
) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO(confirm))

    log_file = tmp_dir_cwd / 'logfire.log'
    log_file.touch()
    monkeypatch.setattr(logfire._internal.cli, 'LOGFIRE_LOG_FILE', log_file)

    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'clean --data-dir {str(tmp_dir_cwd)} --logs'))
    out, err = capsys.readouterr()
    assert err == output
    assert out.splitlines() == [
        'The following files will be deleted:',
        str(log_file),
        str(tmp_dir_cwd / 'logfire_credentials.json'),
        'Are you sure? [N/y]',
    ]


def test_clean_default_dir_does_not_exist(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(shlex.split('clean --data-dir potato'))
    assert 'No Logfire data found in' in capsys.readouterr().err
    assert exc.value.code == 1


def test_clean_default_dir_is_not_a_directory(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO('y'))
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    with pytest.raises(SystemExit) as exc:
        main(shlex.split(f'clean --data-dir {str(tmp_dir_cwd)}/logfire_credentials.json'))
    assert 'No Logfire data found in' in capsys.readouterr().err
    assert exc.value.code == 1


def test_inspect(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    os.environ['COLUMNS'] = '150'
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    with pytest.raises(SystemExit):
        main(['inspect'])
    assert capsys.readouterr().err == snapshot("""\


╭───────────────────────────────────────────────────────────────── Logfire Summary ──────────────────────────────────────────────────────────────────╮
│                                                                                                                                                    │
│  ☐ botocore (need to install opentelemetry-instrumentation-botocore)                                                                               │
│  ☐ jinja2 (need to install opentelemetry-instrumentation-jinja2)                                                                                   │
│  ☐ pymysql (need to install opentelemetry-instrumentation-pymysql)                                                                                 │
│  ☐ urllib (need to install opentelemetry-instrumentation-urllib)                                                                                   │
│                                                                                                                                                    │
│                                                                                                                                                    │
│  To install all recommended packages at once, run:                                                                                                 │
│                                                                                                                                                    │
│  uv add opentelemetry-instrumentation-botocore opentelemetry-instrumentation-jinja2 opentelemetry-instrumentation-pymysql                          │
│  opentelemetry-instrumentation-urllib                                                                                                              │
│                                                                                                                                                    │
│  ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────  │
│                                                                                                                                                    │
│  To hide this summary box, use: logfire run --no-summary.                                                                                          │
│                                                                                                                                                    │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

""")


@pytest.mark.parametrize(
    ('otel_instrumentation_map', 'installed', 'should_install'),
    [
        (
            {
                'opentelemetry-instrumentation-fastapi': 'fastapi',
                'opentelemetry-instrumentation-urllib': 'urllib',
                'opentelemetry-instrumentation-sqlite3': 'sqlite3',
            },
            {'fastapi'},
            snapshot(
                {
                    ('opentelemetry-instrumentation-fastapi', 'fastapi'),
                    ('opentelemetry-instrumentation-urllib', 'urllib'),
                    ('opentelemetry-instrumentation-sqlite3', 'sqlite3'),
                }
            ),
        ),
        (
            {
                'opentelemetry-instrumentation-fastapi': 'fastapi',
                'opentelemetry-instrumentation-starlette': 'starlette',
            },
            {'fastapi', 'starlette'},
            snapshot({('opentelemetry-instrumentation-fastapi', 'fastapi')}),
        ),
        (
            {
                'opentelemetry-instrumentation-urllib3': 'urllib3',
                'opentelemetry-instrumentation-requests': 'requests',
                'opentelemetry-instrumentation-sqlite3': 'sqlite3',
            },
            {'urllib3', 'requests'},
            snapshot(
                {
                    ('opentelemetry-instrumentation-requests', 'requests'),
                    ('opentelemetry-instrumentation-sqlite3', 'sqlite3'),
                }
            ),
        ),
        (
            {'opentelemetry-instrumentation-starlette': 'starlette'},
            {'starlette'},
            snapshot({('opentelemetry-instrumentation-starlette', 'starlette')}),
        ),
    ],
)
def test_recommended_packages_with_dependencies(
    otel_instrumentation_map: dict[str, str],
    installed: set[str],
    should_install: set[tuple[str, str]],
) -> None:
    recommendations = find_recommended_instrumentations_to_install(otel_instrumentation_map, set(), installed)
    assert recommendations == should_install


@pytest.mark.parametrize('webbrowser_error', [False, True])
def test_auth(tmp_path: Path, webbrowser_error: bool, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        # Necessary to assert that credentials are written to the `auth_file` (which happens from the `cli` module)
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.input'))
        webbrowser_open = stack.enter_context(
            patch('webbrowser.open', side_effect=webbrowser.Error if webbrowser_error is True else None)
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/device-auth/wait/DC',
            [
                dict(text='null'),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
        )

        main(['--region', 'us', 'auth'])

        assert auth_file.read_text() == snapshot(
            """\
[tokens."https://logfire-us.pydantic.dev"]
token = "fake_token"
expiration = "fake_exp"
"""
        )
        _, err = capsys.readouterr()
        assert err.splitlines() == snapshot(
            [
                '',
                'Welcome to Logfire! 🔥',
                'Before you can send data to Logfire, we need to authenticate you.',
                '',
                'Press Enter to open example.com in your browser...',
                "Please open http://example.com/auth in your browser to authenticate if it hasn't already.",
                'Waiting for you to authenticate with Logfire...',
                'Successfully authenticated!',
                '',
                IsStr(regex=r'Your Logfire credentials are stored in (.*\.toml)'),
            ]
        )

        webbrowser_open.assert_called_once_with('http://example.com/auth', new=2)


def test_auth_temp_failure(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.input'))
        stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/device-auth/wait/DC',
            [
                dict(exc=requests.exceptions.ConnectTimeout),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
        )

        with pytest.warns(UserWarning, match=r'^Failed to poll for token\. Retrying\.\.\.$'):
            main(['--region', 'us', 'auth'])


def test_auth_permanent_failure(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.input'))
        stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get('https://logfire-us.pydantic.dev/v1/device-auth/wait/DC', text='Error', status_code=500)

        with pytest.warns(UserWarning, match=r'^Failed to poll for token\. Retrying\.\.\.$'):
            with pytest.raises(LogfireConfigError, match='Failed to poll for token.'):
                main(['--region', 'us', 'auth'])


def test_auth_on_authenticated_user(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch('logfire._internal.auth.DEFAULT_FILE', default_credentials):
        # US is the default region in the default credentials fixture:
        main(['--region', 'us', 'auth'])

        _, err = capsys.readouterr()
        assert 'You are already logged in' in err


def test_auth_logout(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch('logfire._internal.auth.DEFAULT_FILE', default_credentials):
        main(['--region', 'us', 'auth', 'logout'])

    assert default_credentials.read_text() == ''
    _, err = capsys.readouterr()
    assert err.splitlines() == snapshot(
        [
            'Successfully logged out from https://logfire-us.pydantic.dev',
            '',
            IsStr(regex=r'Your Logfire credentials have been removed from .*\.toml'),
        ]
    )


def test_auth_logout_not_logged_in(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    auth_file = tmp_path / 'default.toml'
    auth_file.touch()
    with patch('logfire._internal.auth.DEFAULT_FILE', auth_file), pytest.raises(SystemExit) as exc:
        main(['auth', 'logout'])
    assert exc.value.code == 1
    assert 'You are not logged into Logfire' in capsys.readouterr().err


def test_auth_logout_wrong_region(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with patch('logfire._internal.auth.DEFAULT_FILE', default_credentials), pytest.raises(SystemExit) as exc:
        main(['--region', 'eu', 'auth', 'logout'])
    assert exc.value.code == 1
    assert 'No user token was found matching' in capsys.readouterr().err


def test_auth_no_region_specified(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        # Necessary to assert that credentials are written to the `auth_file` (which happens from the `cli` module)
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        # 'not_an_int' is used as the first input to test that invalid inputs are supported,
        # '2' will result in the EU region being used:
        stack.enter_context(patch('logfire._internal.cli.auth.input', side_effect=['not_an_int', '2', '']))
        stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-eu.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-eu.pydantic.dev/v1/device-auth/wait/DC',
            [
                dict(text='null'),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
        )

        # Run the auth command, *without* any region specified
        main(['auth'])

        assert auth_file.read_text() == snapshot(
            """\
[tokens."https://logfire-eu.pydantic.dev"]
token = "fake_token"
expiration = "fake_exp"
"""
        )


def test_projects_help(capsys: pytest.CaptureFixture[str]) -> None:
    main(['projects'])
    assert capsys.readouterr().out.splitlines()[0] == 'usage: logfire projects [-h] {list,new,use} ...'


def test_projects_list(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[{'organization_name': 'test-org', 'project_name': 'test-pr'}],
        )

        main(['projects', 'list'])

        output = capsys.readouterr().err
        assert output.splitlines() == snapshot(
            [
                "List of the projects you have write access to (requires the 'write_token' permission):",
                '',
                ' Organization   | Project',
                '----------------|--------',
                ' test-org       | test-pr',
            ]
        )


def test_projects_list_no_project(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])

        main(['projects', 'list'])

        output = capsys.readouterr().err
        assert (
            output
            == 'No projects found for the current user. You can create a new project with `logfire projects new`\n'
        )


def test_projects_new_with_project_name_and_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--org', 'fake_org'])

        output = capsys.readouterr().err
        assert output.splitlines() == snapshot(
            ['Project created successfully. You will be able to view it at: fake_project_url']
        )

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_with_project_name_without_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_with_project_name_and_wrong_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--org', 'wrong_org'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]
        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_with_project_name_and_default_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--default-org'])

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_with_project_name_multiple_organizations(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['fake_org']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'default_organization': {'organization_name': 'fake_default_org'}},
        )

        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject'])

        assert prompt_mock.mock_calls == [
            call(
                '\nTo create and use a new project, please provide the following information:\nSelect the organization to create the project in',
                choices=['fake_org', 'fake_default_org'],
                default='fake_default_org',
            )
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_with_project_name_and_default_org_multiple_organizations(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/account/me',
            json={'default_organization': {'organization_name': 'fake_default_org'}},
        )

        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_default_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--default-org'])

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_without_project_name(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', '--default-org'])

        assert prompt_mock.mock_calls == [
            call('Enter the project name', default=sanitize_project_name(tmp_dir_cwd.name))
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_invalid_project_name(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new', 'invalid name', '--default-org'])

        assert prompt_mock.mock_calls == [
            call(
                "\nThe project name you've entered is invalid. Valid project names:\n"
                '  * may contain lowercase alphanumeric characters\n'
                '  * may contain single hyphens\n'
                '  * may not start or end with a hyphen\n\n'
                'Enter the project name you want to use:',
                default='testprojectsnewinvalidproj0',
            ),
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        with pytest.raises(LogfireConfigError, match='Invalid credentials, when initializing project:'):
            main(['projects', 'new', 'myproject', '--org', 'fake_org'])


def test_projects_without_project_name_without_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects',
            [create_project_response],
        )

        main(['projects', 'new'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]
        assert prompt_mock.mock_calls == [
            call('Enter the project name', default=sanitize_project_name(tmp_dir_cwd.name))
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project created successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_new_get_organizations_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error retrieving list of organizations'):
            main(['projects', 'new'])


def test_projects_new_get_user_info_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get('https://logfire-us.pydantic.dev/v1/account/me', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error retrieving user information'):
            main(['projects', 'new'])


def test_projects_new_create_project_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-us.pydantic.dev/v1/writable-projects/', json=[])
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/available-for-projects/',
            json=[{'organization_name': 'fake_org'}],
        )
        m.post('https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error creating new project'):
            main(['projects', 'new', 'myproject', '--org', 'fake_org'])


def test_create_read_token(tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/read-tokens',
            json={'token': 'fake_token'},
        )

        main(['read-tokens', '--project', 'fake_org/myproject', 'create'])

        output = capsys.readouterr().out
        assert output == snapshot('fake_token\n')


def test_get_prompt(tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/prompts',
            json={'prompt': 'This is the prompt\n'},
        )

        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123'])

        output = capsys.readouterr().out
        assert output == snapshot('This is the prompt\n')


def test_projects_use(tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[
                {'organization_name': 'fake_org', 'project_name': 'myproject'},
                {'organization_name': 'fake_org', 'project_name': 'otherproject'},
            ],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject'])

        output = capsys.readouterr().err
        assert output == snapshot('Project configured successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_use_without_project_name(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[
                {'organization_name': 'fake_org', 'project_name': 'myproject'},
                {'organization_name': 'fake_org', 'project_name': 'otherproject'},
            ],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use'])

        assert prompt_mock.mock_calls == [
            call(
                (
                    "Please select one of the following projects by number (requires the 'write_token' permission):\n"
                    '1. fake_org/myproject\n'
                    '2. fake_org/otherproject\n'
                ),
                choices=['1', '2'],
                default='1',
            )
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project configured successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_use_multiple(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        config_console = stack.enter_context(patch('logfire._internal.config.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[
                {'organization_name': 'fake_org', 'project_name': 'myproject'},
                {'organization_name': 'other_org', 'project_name': 'myproject'},
            ],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject'])

        output = capsys.readouterr().err
        assert output == snapshot('Project configured successfully. You will be able to view it at: fake_project_url\n')

        config_console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in config_console.mock_calls]
        assert config_console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Found multiple projects with name `myproject`.')",
        ]

        assert prompt_mock.mock_calls == [
            call(
                (
                    "Please select one of the following projects by number (requires the 'write_token' permission):\n"
                    '1. fake_org/myproject\n'
                    '2. other_org/myproject\n'
                ),
                choices=['1', '2'],
                default='1',
            )
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_use_multiple_with_org(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[
                {'organization_name': 'fake_org', 'project_name': 'myproject'},
                {'organization_name': 'other_org', 'project_name': 'myproject'},
            ],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject', '--org', 'fake_org'])

        output = capsys.readouterr().err
        assert output == snapshot('Project configured successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_use_wrong_project(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['y', '1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'myproject'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'wrong-project', '--org', 'fake_org'])

        assert prompt_mock.mock_calls == [
            call(
                'No projects with name `wrong-project` found for the current user in organization `fake_org`. Choose from all projects?',
                choices=['y', 'n'],
                default='y',
            ),
            call(
                "Please select one of the following projects by number (requires the 'write_token' permission):\n1. fake_org/myproject\n",
                choices=['1'],
                default='1',
            ),
        ]

        output = capsys.readouterr().err
        assert output == snapshot('Project configured successfully. You will be able to view it at: fake_project_url\n')

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-us.pydantic.dev',
        }


def test_projects_use_wrong_project_give_up(
    tmp_dir_cwd: Path, default_credentials: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        config_console = stack.enter_context(patch('logfire._internal.config.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['n']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'myproject'}],
        )

        main(['projects', 'use', 'wrong-project', '--org', 'fake_org'])

        assert prompt_mock.mock_calls == [
            call(
                'No projects with name `wrong-project` found for the current user in organization `fake_org`. Choose from all projects?',
                choices=['y', 'n'],
                default='y',
            ),
        ]
        config_console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in config_console.mock_calls]
        assert config_console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('You can create a new project in organization `fake_org` with `logfire projects new --org fake_org`')",
        ]


def test_projects_use_without_projects(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[],
        )

        main(['projects', 'use', 'myproject'])

        assert (
            re.sub(r'\s+', ' ', capsys.readouterr().err).strip()
            == 'No projects found for the current user. You can create a new project with `logfire projects new`'
        )


def test_projects_use_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'myproject'}],
        )
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        with pytest.raises(LogfireConfigError, match='Invalid credentials, when initializing project:'):
            main(['projects', 'use', 'myproject', '--org', 'fake_org'])


def test_projects_use_write_token_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/writable-projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'myproject'}],
        )
        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            text='Error',
            status_code=500,
        )

        with pytest.raises(LogfireConfigError, match='Error creating project write token'):
            main(['projects', 'use', 'myproject', '--org', 'fake_org'])


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    main(['info'])
    output = capsys.readouterr().err.strip()
    assert output.startswith('logfire="')
    assert '[related_packages]' in output


def test_instrument_packages_calls_instrument(monkeypatch: pytest.MonkeyPatch):
    fake_logfire = types.SimpleNamespace()
    called = {}

    def make_instrument(name: str):
        def f():
            called[name] = True

        return f

    fake_logfire.instrument_foo = make_instrument('foo')
    monkeypatch.setattr(logfire._internal.cli.run, 'logfire', fake_logfire)
    installed_otel = {'opentelemetry-instrumentation-foo'}
    instrument_pkg_map = {'opentelemetry-instrumentation-foo': 'foo'}
    result = instrument_packages(installed_otel, instrument_pkg_map)
    assert result == snapshot(['foo'])
    assert called['foo'] is True


def test_instrument_packages_handles_missing(monkeypatch: pytest.MonkeyPatch):
    fake_logfire = types.SimpleNamespace()
    monkeypatch.setitem(sys.modules, 'logfire', fake_logfire)
    installed_otel = {'opentelemetry-instrumentation-bar'}
    instrument_pkg_map = {'opentelemetry-instrumentation-bar': 'bar'}
    result = instrument_packages(installed_otel, instrument_pkg_map)
    assert result == []


def test_instrumented_packages_text_basic():
    installed_otel_pkgs = {'opentelemetry-instrumentation-foo', 'opentelemetry-instrumentation-bar'}
    instrumented_packages = ['foo']
    installed_pkgs = {'foo', 'bar'}
    text = instrumented_packages_text(installed_otel_pkgs.copy(), instrumented_packages, installed_pkgs)
    assert '✓ foo' in text
    assert '⚠️ bar' in text


def test_get_recommendation_texts():
    recs = {('opentelemetry-instrumentation-foo', 'foo'), ('opentelemetry-instrumentation-bar', 'bar')}
    recommended, install = get_recommendation_texts(recs)
    assert 'uv add opentelemetry-instrumentation-bar opentelemetry-instrumentation-foo' in install
    assert 'need to install opentelemetry-instrumentation-bar' in recommended
    assert 'need to install opentelemetry-instrumentation-foo' in recommended


def test_instrument_packages_openai() -> None:
    instrument_packages({'openai'}, {'openai': 'openai'})

    import openai

    client = openai.Client(api_key='test-key')
    assert getattr(client, '_is_instrumented_by_logfire', False) is True


def test_instrument_packages_aiohttp_server() -> None:
    try:
        instrument_packages(
            {'opentelemetry-instrumentation-aiohttp-server'},
            {'opentelemetry-instrumentation-aiohttp-server': 'aiohttp_server'},
        )

        import aiohttp.web

        app = aiohttp.web.Application()
        assert app.middlewares[0].__module__ == 'opentelemetry.instrumentation.aiohttp_server'
    finally:
        from opentelemetry.instrumentation.aiohttp_server import AioHttpServerInstrumentor

        AioHttpServerInstrumentor().uninstrument()


async def test_instrument_packages_aiohttp_client() -> None:
    try:
        instrument_packages(
            {'opentelemetry-instrumentation-aiohttp-client'},
            {'opentelemetry-instrumentation-aiohttp-client': 'aiohttp_client'},
        )

        import aiohttp.client

        async with aiohttp.client.ClientSession() as client:
            assert getattr(client.trace_configs[0], '_is_instrumented_by_opentelemetry', False) is True
    finally:
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

        AioHttpClientInstrumentor().uninstrument()


def test_split_args_action() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--foo', action=SplitArgs)
    args = parser.parse_args(['--foo', 'a,b,c'])
    assert args.foo == ['a', 'b', 'c']


def test_org_project_action() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', action=OrgProjectAction)
    args = parser.parse_args(['--project', 'organization/project'])
    assert args.project == 'project'
    assert args.organization == 'organization'

    # Missing `/` separation.
    with pytest.raises(SystemExit):
        args = parser.parse_args(['--project', 'organization'])

    # Empty project or organization name.
    with pytest.raises(SystemExit):
        args = parser.parse_args(['--project', 'organization/'])

    # Can't split multiple `/`.
    with pytest.raises(SystemExit):
        args = parser.parse_args(['--project', 'organization/project/extra'])


def test_gateway_help(capsys: pytest.CaptureFixture[str]) -> None:
    main(['gateway'])

    assert 'usage: logfire gateway {launch,serve}' in capsys.readouterr().err


def test_gateway_parses_launch_args() -> None:
    context = gateway_cli.GatewayCommandContext(
        raw_args=['launch', 'claude', '--', '--dangerously-skip-permissions'], region='eu', logfire_url=None
    )

    assert gateway_cli.parse_gateway_command(context) == gateway_cli.GatewayCommand(
        'launch', ('claude', '--', '--dangerously-skip-permissions')
    )


def test_gateway_parses_bare_integration_as_launch() -> None:
    context = gateway_cli.GatewayCommandContext(raw_args=['claude'], region=None, logfire_url=None)

    assert gateway_cli.parse_gateway_command(context) == gateway_cli.GatewayCommand('launch', ('claude',))


def test_gateway_parses_serve_args() -> None:
    context = gateway_cli.GatewayCommandContext(raw_args=['serve', '--device-flow'], region=None, logfire_url=None)

    assert gateway_cli.parse_gateway_command(context) == gateway_cli.GatewayCommand('serve', ('--device-flow',))


def test_gateway_cli_adapter_exits_for_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], gateway_cli.GatewayCommandContext]] = []

    def run_launch(raw_args: list[str], context: gateway_cli.GatewayCommandContext) -> int:
        calls.append((raw_args, context))
        return 0

    monkeypatch.setattr(gateway_cli, '_run_launch', run_launch)

    with pytest.raises(SystemExit) as exc_info:
        main(['--region', 'eu', 'gateway', 'launch', 'claude'])

    assert exc_info.value.code == 0
    assert calls == [
        (
            ['claude'],
            gateway_cli.GatewayCommandContext(
                raw_args=['launch', 'claude'], region='eu', logfire_url='https://logfire-eu.pydantic.dev'
            ),
        )
    ]


def test_gateway_cli_adapter_exits_for_serve(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], gateway_cli.GatewayCommandContext]] = []

    def run_serve(raw_args: list[str], context: gateway_cli.GatewayCommandContext) -> int:
        calls.append((raw_args, context))
        return 130

    monkeypatch.setattr(gateway_cli, '_run_serve', run_serve)

    with pytest.raises(SystemExit) as exc_info:
        main(['gateway', 'serve'])

    assert exc_info.value.code == 130
    assert calls == [([], gateway_cli.GatewayCommandContext(raw_args=['serve'], region=None, logfire_url=None))]


def test_gateway_optional_dependency_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_dependency(name: str) -> types.ModuleType:
        raise ImportError(name)

    monkeypatch.setattr(gateway_cli.importlib, 'import_module', missing_dependency)

    with pytest.raises(LogfireConfigError, match=r'pip install "logfire\[gateway\]"'):
        gateway_cli.load_gateway_deps()


def test_gateway_optional_dependencies_load(monkeypatch: pytest.MonkeyPatch) -> None:
    modules = {
        'httpx': types.SimpleNamespace(),
        'uvicorn': types.SimpleNamespace(),
        'starlette.applications': types.SimpleNamespace(Starlette='Starlette'),
        'starlette.responses': types.SimpleNamespace(
            Response='Response', JSONResponse='JSONResponse', StreamingResponse='StreamingResponse'
        ),
        'starlette.routing': types.SimpleNamespace(Route='Route'),
    }

    def import_module(name: str) -> Any:
        return modules[name]

    monkeypatch.setattr(gateway_cli.importlib, 'import_module', import_module)

    deps = gateway_cli.load_gateway_deps()

    assert deps.httpx is modules['httpx']
    assert deps.uvicorn is modules['uvicorn']
    assert deps.Starlette == 'Starlette'
    assert deps.Route == 'Route'
    assert deps.Response == 'Response'
    assert deps.JSONResponse == 'JSONResponse'
    assert deps.StreamingResponse == 'StreamingResponse'


def test_ai_tool_opencode_gateway_launch_config(tmp_path: Path) -> None:
    integration = ai_tools.resolve_ai_tool('opencode')

    env = integration.build_gateway_env(
        proxy_base='http://127.0.0.1:11465', model='gpt-5', workdir=tmp_path, local_token='local-secret'
    )

    assert env == {
        'OPENCODE_PROVIDER': 'logfire-gateway',
        'OPENCODE_CONFIG': str(tmp_path / 'opencode.jsonc'),
    }
    assert json.loads((tmp_path / 'opencode.jsonc').read_text()) == snapshot(
        {
            '$schema': 'https://opencode.ai/config.json',
            'model': 'logfire-gateway/gpt-5',
            'provider': {
                'logfire-gateway': {
                    'npm': '@ai-sdk/openai-compatible',
                    'name': 'Logfire Gateway',
                    'options': {'apiKey': 'local-secret', 'baseURL': 'http://127.0.0.1:11465/proxy/openai/v1'},
                    'models': {'gpt-5': {}},
                }
            },
        }
    )


def test_ai_tool_opencode_gateway_launch_config_without_model(tmp_path: Path) -> None:
    integration = ai_tools.resolve_ai_tool('opencode')

    env = integration.build_gateway_env(
        proxy_base='http://127.0.0.1:11465', model=None, workdir=tmp_path, local_token='local-secret'
    )

    assert env == {
        'OPENCODE_PROVIDER': 'logfire-gateway',
        'OPENCODE_CONFIG': str(tmp_path / 'opencode.jsonc'),
    }
    assert json.loads((tmp_path / 'opencode.jsonc').read_text()) == snapshot(
        {
            '$schema': 'https://opencode.ai/config.json',
            'provider': {
                'logfire-gateway': {
                    'npm': '@ai-sdk/openai-compatible',
                    'name': 'Logfire Gateway',
                    'options': {'apiKey': 'local-secret', 'baseURL': 'http://127.0.0.1:11465/proxy/openai/v1'},
                }
            },
        }
    )


def test_ai_tool_codex_gateway_launch_config() -> None:
    integration = ai_tools.resolve_ai_tool('codex')

    env = integration.build_gateway_env(
        proxy_base='http://127.0.0.1:11465/', model='gpt-5', workdir=Path(), local_token='local-secret'
    )

    assert env == snapshot(
        {
            'OPENAI_BASE_URL': 'http://127.0.0.1:11465/proxy/openai/v1',
            'OPENAI_API_KEY': 'local-secret',
            'OPENAI_MODEL': 'gpt-5',
        }
    )


def test_ai_tool_gateway_launch_config_without_model() -> None:
    integration = ai_tools.resolve_ai_tool('codex')

    env = integration.build_gateway_env(
        proxy_base='http://127.0.0.1:11465/', model=None, workdir=Path(), local_token='local-secret'
    )

    assert env == snapshot(
        {
            'OPENAI_BASE_URL': 'http://127.0.0.1:11465/proxy/openai/v1',
            'OPENAI_API_KEY': 'local-secret',
        }
    )


def test_gateway_local_request_authorization() -> None:
    local_request_authorized = getattr(gateway_cli, '_local_request_authorized')

    assert local_request_authorized({'authorization': 'Bearer local-secret'}, 'local-secret')
    assert local_request_authorized({'x-api-key': 'local-secret'}, 'local-secret')
    assert not local_request_authorized({}, 'local-secret')
    assert not local_request_authorized({'authorization': 'Bearer wrong'}, 'local-secret')


def test_gateway_streaming_detection() -> None:
    is_streaming = getattr(gateway_cli, '_is_streaming')

    assert is_streaming(b'{"model":"x","stream" : true}')
    assert not is_streaming(b'{"model":"x","stream": false}')
    assert not is_streaming(b'not-json')
    assert not is_streaming(b'[]')


def test_gateway_filter_headers() -> None:
    assert gateway_cli.filter_headers(
        {
            'Authorization': 'secret',
            'X-Api-Key': 'secret',
            'Host': 'example.com',
            'Connection': 'keep-alive',
            'X-Trace': 'trace-id',
        },
        direction='request',
    ) == [('X-Trace', 'trace-id')]
    assert gateway_cli.filter_headers(
        {
            'Content-Encoding': 'gzip',
            'Transfer-Encoding': 'chunked',
            'Content-Type': 'application/json',
        },
        direction='response',
    ) == [('Content-Type', 'application/json')]


def test_gateway_oauth_callback_html_escapes_query_params() -> None:
    oauth_done_html = getattr(gateway_cli, '_oauth_done_html')

    html = oauth_done_html('Authorization failed', '<script>alert(1)</script>')

    assert '<script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html


def test_gateway_cimd_client_id_and_redirect_uri() -> None:
    gateway_cimd_client_id = getattr(gateway_cli, '_gateway_cimd_client_id')
    oauth_redirect_uri = getattr(gateway_cli, '_oauth_redirect_uri')

    assert gateway_cimd_client_id('http://localhost:3000/') == ('http://localhost:3000/clients/logfire-gateway.json')
    assert gateway_cimd_client_id('https://logfire-eu.pydantic.dev') == (
        'https://logfire.pydantic.dev/clients/logfire-gateway.json'
    )
    assert gateway_cimd_client_id('https://logfire-eu.pydantic.info') == (
        'https://logfire.pydantic.info/clients/logfire-gateway.json'
    )
    assert oauth_redirect_uri(11465) == 'http://127.0.0.1:11465/callback'


def test_gateway_pick_port_uses_preferred_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    pick_port = getattr(gateway_cli, '_pick_port')
    bound_addresses: list[tuple[str, int]] = []

    class FakeSocket:
        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *_exc_info: object) -> None:
            pass

        def bind(self, address: tuple[str, int]) -> None:
            bound_addresses.append(address)

    def fake_socket(_family: int, _type: int) -> FakeSocket:
        return FakeSocket()

    monkeypatch.setattr(gateway_cli.socket, 'socket', fake_socket)

    assert pick_port(12345) == 12345
    assert bound_addresses == [('127.0.0.1', 12345)]


def test_gateway_urls_defaults_and_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway_urls = getattr(gateway_cli, '_gateway_urls')

    args = argparse.Namespace(gateway_region='eu', logfire_url=None, gateway_url=None)
    assert gateway_urls(args) == (
        'eu',
        'https://logfire-eu.pydantic.dev',
        'https://gateway-eu.pydantic.dev',
        'https://logfire.pydantic.dev/clients/logfire-gateway.json',
    )

    with patch.dict(os.environ, {'LOGFIRE_GATEWAY_URL': 'https://gateway.env/'}):
        assert gateway_urls(args) == (
            'eu',
            'https://logfire-eu.pydantic.dev',
            'https://gateway.env',
            'https://logfire.pydantic.dev/clients/logfire-gateway.json',
        )

    args = argparse.Namespace(gateway_region='us', logfire_url='https://backend.example/', gateway_url=None)
    assert gateway_urls(args) == (
        'us',
        'https://backend.example',
        'https://backend.example',
        'https://backend.example/clients/logfire-gateway.json',
    )

    args = argparse.Namespace(
        gateway_region='us', logfire_url='https://backend.example/', gateway_url='https://gateway.example/'
    )
    with patch.dict(os.environ, {'LOGFIRE_GATEWAY_URL': 'https://gateway.env/'}):
        assert gateway_urls(args) == (
            'us',
            'https://backend.example',
            'https://gateway.example',
            'https://backend.example/clients/logfire-gateway.json',
        )

    args = argparse.Namespace(
        gateway_region='us',
        logfire_url='https://logfire-eu.pydantic.info/',
        gateway_url='https://gateway.pydantic.info/',
    )
    assert gateway_urls(args) == (
        'us',
        'https://logfire-eu.pydantic.info',
        'https://gateway.pydantic.info',
        'https://logfire.pydantic.info/clients/logfire-gateway.json',
    )


def test_gateway_pick_port_falls_back_when_preferred_is_busy() -> None:
    pick_port = getattr(gateway_cli, '_pick_port')

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        preferred = cast(int, sock.getsockname()[1])

        picked = pick_port(preferred)

    assert picked != preferred
    assert picked > 0


def test_gateway_parse_serve_args() -> None:
    parse_serve_args = getattr(gateway_cli, '_parse_serve_args')

    args = parse_serve_args(
        ['--device-flow', '--region', 'eu', '--gateway-url', 'https://gateway.example/', '--port', '1234'],
        gateway_cli.GatewayCommandContext(raw_args=[], region='us', logfire_url='https://backend.example/'),
    )

    assert args.device_flow is True
    assert args.gateway_region == 'eu'
    assert args.gateway_url == 'https://gateway.example/'
    assert args.port == 1234
    assert args.logfire_url is None

    args = parse_serve_args(
        [], gateway_cli.GatewayCommandContext(raw_args=[], region='eu', logfire_url='https://backend.example/')
    )

    assert args.gateway_region == 'eu'
    assert args.logfire_url == 'https://backend.example/'


def test_gateway_handle_proxy_rejects_unknown_route_and_unauthorized_request() -> None:
    handle_proxy = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_proxy'))

    class CapturedJSONResponse:
        def __init__(self, content: dict[str, Any], *, status_code: int) -> None:
            self.content = content
            self.status_code = status_code

    deps = gateway_cli.GatewayDeps(
        httpx=Mock(),
        uvicorn=Mock(),
        Starlette=Mock(),
        Route=Mock(),
        Response=Mock(),
        JSONResponse=CapturedJSONResponse,
        StreamingResponse=Mock(),
    )
    state = gateway_cli.ProxyState(
        deps=deps,
        auth=cast(gateway_auth.GatewayAuth, Mock()),
        client=Mock(),
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    async def body() -> bytes:
        raise AssertionError('body should not be read')

    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace(logfire_gateway=state)),
        url=types.SimpleNamespace(path='/not-proxy', query=''),
        headers={},
        method='POST',
        body=body,
    )

    response = asyncio.run(handle_proxy(request))
    assert response.status_code == 404
    assert response.content == {'error': 'no route', 'path': '/not-proxy'}

    request.url.path = '/proxy/openai/v1/chat/completions'
    response = asyncio.run(handle_proxy(request))
    assert response.status_code == 401
    assert response.content == {'error': 'unauthorized'}


def test_gateway_handle_proxy_forwards_non_streaming_request() -> None:
    handle_proxy = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_proxy'))

    class CapturedResponse:
        def __init__(
            self, *, content: bytes, status_code: int, headers: dict[str, str], media_type: str | None
        ) -> None:
            self.content = content
            self.status_code = status_code
            self.headers = headers
            self.media_type = media_type

    deps = gateway_cli.GatewayDeps(
        httpx=Mock(),
        uvicorn=Mock(),
        Starlette=Mock(),
        Route=Mock(),
        Response=CapturedResponse,
        JSONResponse=Mock(),
        StreamingResponse=Mock(),
    )
    state = gateway_cli.ProxyState(
        deps=deps,
        auth=cast(gateway_auth.GatewayAuth, Mock()),
        client=Mock(),
        gateway='https://gateway.example.com/',
        region='us',
        local_token='local-token',
    )
    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace(logfire_gateway=state)),
        url=types.SimpleNamespace(path='/proxy/openai/v1/chat/completions', query='a=1'),
        headers={
            'authorization': 'Bearer local-token',
            'x-api-key': 'local-token',
            'host': 'localhost',
            'x-trace': 'trace-id',
        },
        method='POST',
    )

    async def body() -> bytes:
        return b'{"stream": false}'

    request.body = body
    captured: dict[str, Any] = {}

    async def fake_gateway_request(
        _state: gateway_cli.ProxyState, method: str, upstream_url: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, str], bytes, str]:
        captured.update(method=method, upstream_url=upstream_url, headers=headers, body=body)
        return 201, {'content-type': 'application/json', 'content-encoding': 'gzip'}, b'{"ok":true}', 'application/json'

    with patch.object(gateway_cli, '_gateway_request', fake_gateway_request):
        response = asyncio.run(handle_proxy(request))

    assert captured == {
        'method': 'POST',
        'upstream_url': 'https://gateway.example.com/proxy/openai/v1/chat/completions?a=1',
        'headers': {'x-trace': 'trace-id'},
        'body': b'{"stream": false}',
    }
    assert response.status_code == 201
    assert response.content == b'{"ok":true}'
    assert response.headers == {'content-type': 'application/json'}
    assert response.media_type == 'application/json'


def test_gateway_oauth_callback_and_favicon_handlers() -> None:
    handle_oauth_callback = cast(
        Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_oauth_callback')
    )
    handle_favicon = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_favicon'))

    class CapturedResponse:
        def __init__(self, content: str = '', *, status_code: int, media_type: str | None = None) -> None:
            self.content = content
            self.status_code = status_code
            self.media_type = media_type

    class CapturedAuth:
        def __init__(self) -> None:
            self.calls: list[dict[str, str | None]] = []

        def complete_browser_callback(
            self, *, error: str | None, error_description: str | None, code: str | None, state: str | None
        ) -> gateway_auth.OAuthCallbackResult:
            self.calls.append({'error': error, 'error_description': error_description, 'code': code, 'state': state})
            return gateway_auth.OAuthCallbackResult('Authorization failed', '<bad>', status_code=400)

    auth = CapturedAuth()
    deps = gateway_cli.GatewayDeps(
        httpx=Mock(),
        uvicorn=Mock(),
        Starlette=Mock(),
        Route=Mock(),
        Response=CapturedResponse,
        JSONResponse=Mock(),
        StreamingResponse=Mock(),
    )
    state = gateway_cli.ProxyState(
        deps=deps,
        auth=cast(gateway_auth.GatewayAuth, auth),
        client=Mock(),
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )
    request = types.SimpleNamespace(
        app=types.SimpleNamespace(state=types.SimpleNamespace(logfire_gateway=state)),
        query_params={'error': 'access_denied', 'error_description': 'nope', 'code': 'code', 'state': 'state'},
    )

    response = asyncio.run(handle_oauth_callback(request))
    favicon = asyncio.run(handle_favicon(request))

    assert auth.calls == [{'error': 'access_denied', 'error_description': 'nope', 'code': 'code', 'state': 'state'}]
    assert response.status_code == 400
    assert response.media_type == 'text/html'
    assert '&lt;bad&gt;' in response.content
    assert favicon.status_code == 204


def test_gateway_build_app_registers_routes() -> None:
    class CapturedApp:
        def __init__(self, *, routes: list[Any]) -> None:
            self.routes = routes
            self.state = types.SimpleNamespace()

    def route(path: str, endpoint: Any, *, methods: list[str]) -> tuple[str, Any, list[str]]:
        return path, endpoint, methods

    deps = gateway_cli.GatewayDeps(
        httpx=Mock(),
        uvicorn=Mock(),
        Starlette=CapturedApp,
        Route=route,
        Response=Mock(),
        JSONResponse=Mock(),
        StreamingResponse=Mock(),
    )
    state = gateway_cli.ProxyState(
        deps=deps,
        auth=cast(gateway_auth.GatewayAuth, Mock()),
        client=Mock(),
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    app = gateway_cli.build_app(deps, state)

    assert app.state.logfire_gateway is state
    assert [(path, methods) for path, _endpoint, methods in app.routes] == [
        ('/callback', ['GET']),
        ('/_logfire_gateway/oauth/callback', ['GET']),
        ('/favicon.ico', ['GET']),
        ('/{path:path}', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']),
    ]


class MockOAuthTokenResponse:
    status_code = 200
    text = ''

    def json(self) -> dict[str, Any]:
        return {'access_token': 'access-token', 'refresh_token': 'refresh-token', 'expires_in': 3600}


class MockOAuthDeviceResponse:
    status_code = 200
    text = ''

    def json(self) -> dict[str, Any]:
        return {
            'device_code': 'device-code-123',
            'user_code': 'user-code-123',
            'verification_uri': 'http://localhost:3000/activate',
            'expires_in': 1,
            'interval': 0,
        }


class MockCimdOAuthClient:
    client_id = 'http://localhost:3000/clients/logfire-gateway.json'

    def __init__(self) -> None:
        self.device_authorization_requests: list[dict[str, str]] = []
        self.token_requests: list[dict[str, str]] = []

    async def start_device_authorization(self, data: dict[str, str]) -> MockOAuthDeviceResponse:
        self.device_authorization_requests.append(data)
        return MockOAuthDeviceResponse()

    async def post_token(self, data: dict[str, str]) -> MockOAuthTokenResponse:
        self.token_requests.append(data)
        return MockOAuthTokenResponse()


def test_gateway_auth_code_flow_uses_cimd_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []

    def open_browser(url: str) -> None:
        opened_urls.append(url)

    monkeypatch.setattr(gateway_auth.webbrowser, 'open', open_browser)

    async def run() -> MockCimdOAuthClient:
        client = MockCimdOAuthClient()
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='http://localhost:3000/oauth/authorize',
                token_endpoint='http://localhost:3000/oauth/token',
                device_authorization_endpoint='http://localhost:3000/oauth/device',
            ),
            resource='http://localhost:3000/proxy',
            scope='project:gateway_proxy',
        )
        bootstrap = gateway_auth.AuthBootstrap(redirect_uri='http://127.0.0.1:11465/callback')
        authorize_task = asyncio.create_task(session.auth_code_flow(bootstrap))
        for _ in range(10):
            if opened_urls:
                break
            await asyncio.sleep(0)
        bootstrap.received_code = 'code-123'
        bootstrap.event.set()
        await authorize_task
        return client

    client = asyncio.run(run())
    assert opened_urls
    query = {key: values[0] for key, values in parse_qs(urlparse(opened_urls[0]).query).items()}
    assert query['client_id'] == 'http://localhost:3000/clients/logfire-gateway.json'
    assert query['redirect_uri'] == 'http://127.0.0.1:11465/callback'
    assert query['resource'] == 'http://localhost:3000/proxy'
    assert query['scope'] == 'project:gateway_proxy'

    assert len(client.token_requests) == 1
    token_request = client.token_requests[0].copy()
    assert token_request.pop('code_verifier')
    assert token_request == {
        'grant_type': 'authorization_code',
        'code': 'code-123',
        'client_id': 'http://localhost:3000/clients/logfire-gateway.json',
        'redirect_uri': 'http://127.0.0.1:11465/callback',
        'resource': 'http://localhost:3000/proxy',
    }


def test_gateway_device_flow_uses_cimd_client_id(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []

    def open_browser(url: str) -> None:
        opened_urls.append(url)

    monkeypatch.setattr(gateway_auth.webbrowser, 'open', open_browser)

    async def run() -> MockCimdOAuthClient:
        client = MockCimdOAuthClient()
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='http://localhost:3000/oauth/authorize',
                token_endpoint='http://localhost:3000/oauth/token',
                device_authorization_endpoint='http://localhost:3000/oauth/device',
            ),
            resource='http://localhost:3000/proxy',
            scope='project:gateway_proxy',
        )
        await session.device_flow()
        return client

    client = asyncio.run(run())
    assert opened_urls == ['http://localhost:3000/activate']

    assert len(client.device_authorization_requests) == 1
    device_request = client.device_authorization_requests[0].copy()
    assert device_request.pop('code_challenge')
    assert device_request == {
        'client_id': 'http://localhost:3000/clients/logfire-gateway.json',
        'resource': 'http://localhost:3000/proxy',
        'scope': 'project:gateway_proxy',
        'code_challenge_method': 'S256',
    }

    assert len(client.token_requests) == 1
    token_request = client.token_requests[0].copy()
    assert token_request.pop('code_verifier')
    assert token_request == {
        'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        'device_code': 'device-code-123',
        'client_id': 'http://localhost:3000/clients/logfire-gateway.json',
        'resource': 'http://localhost:3000/proxy',
    }


class MockOAuthSession:
    def __init__(self) -> None:
        self._bootstrap_ready: asyncio.Event | None = None
        self.browser_bootstrap: gateway_auth.AuthBootstrap | None = None
        self.device_calls = 0
        self.refresh_calls = 0
        self.refresh_error = False
        self.in_flight_device_calls = 0
        self.max_in_flight_device_calls = 0

    @property
    def bootstrap_ready(self) -> asyncio.Event:
        if self._bootstrap_ready is None:
            self._bootstrap_ready = asyncio.Event()
        return self._bootstrap_ready

    async def auth_code_flow(self, bootstrap: gateway_auth.AuthBootstrap) -> None:
        bootstrap.expected_state = 'expected-state'
        self.browser_bootstrap = bootstrap
        self.bootstrap_ready.set()
        await bootstrap.event.wait()
        if bootstrap.error is not None:
            raise RuntimeError(bootstrap.error)

    async def device_flow(self) -> None:
        self.device_calls += 1
        self.in_flight_device_calls += 1
        self.max_in_flight_device_calls = max(self.max_in_flight_device_calls, self.in_flight_device_calls)
        await asyncio.sleep(0)
        self.in_flight_device_calls -= 1

    async def current_access_token(self) -> str:
        return 'access-token'

    async def force_refresh(self) -> str:
        self.refresh_calls += 1
        if self.refresh_error:
            raise RuntimeError('refresh failed')
        return 'refreshed-token'


def test_gateway_auth_browser_callback_completes_authorize() -> None:
    async def run() -> tuple[gateway_auth.OAuthCallbackResult, gateway_auth.AuthBootstrap]:
        session = MockOAuthSession()
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, session), redirect_uri='http://127.0.0.1/callback', flow='browser'
        )
        authorize_task = asyncio.create_task(auth.authorize())
        await session.bootstrap_ready.wait()
        assert session.browser_bootstrap is not None
        result = auth.complete_browser_callback(
            error=None, error_description=None, code='code-123', state='expected-state'
        )
        await authorize_task
        return result, session.browser_bootstrap

    result, bootstrap = asyncio.run(run())

    assert result == gateway_auth.OAuthCallbackResult(
        'Authorized', 'You can close this tab and return to the terminal.'
    )
    assert bootstrap.received_code == 'code-123'
    assert bootstrap.event.is_set()


def test_gateway_auth_recover_after_rejection_uses_refresh_then_reauth() -> None:
    async def run() -> tuple[bool, bool, bool, MockOAuthSession]:
        session = MockOAuthSession()
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, session), redirect_uri='http://127.0.0.1/callback', flow='device'
        )
        refresh_ok = await auth.recover_after_rejection(use_reauth=False)
        reauth_ok = await auth.recover_after_rejection(use_reauth=True)
        session.refresh_error = True
        refresh_failed = await auth.recover_after_rejection(use_reauth=False)
        return refresh_ok, reauth_ok, refresh_failed, session

    refresh_ok, reauth_ok, refresh_failed, session = asyncio.run(run())

    assert (refresh_ok, reauth_ok, refresh_failed) == (True, True, False)
    assert session.refresh_calls == 2
    assert session.device_calls == 1


def test_gateway_auth_reauthorization_is_serialized() -> None:
    async def run() -> MockOAuthSession:
        session = MockOAuthSession()
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, session), redirect_uri='http://127.0.0.1/callback', flow='device'
        )
        await asyncio.gather(
            auth.recover_after_rejection(use_reauth=True),
            auth.recover_after_rejection(use_reauth=True),
        )
        return session

    session = asyncio.run(run())

    assert session.device_calls == 2
    assert session.max_in_flight_device_calls == 1


def test_gateway_auth_discovers_oauth_metadata() -> None:
    class Response:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                'authorization_endpoint': 'https://backend.example/authorize',
                'token_endpoint': 'https://backend.example/token',
                'device_authorization_endpoint': 'https://backend.example/device',
            }

    class Http:
        def __init__(self) -> None:
            self.urls: list[str] = []

        async def get(self, url: str) -> Response:
            self.urls.append(url)
            return Response()

    async def run() -> tuple[gateway_auth.OAuthMetadata, Http]:
        http = Http()
        return await gateway_auth.discover_oauth_metadata(http, 'https://backend.example/'), http

    metadata, http = asyncio.run(run())

    assert metadata == gateway_auth.OAuthMetadata(
        authorization_endpoint='https://backend.example/authorize',
        token_endpoint='https://backend.example/token',
        device_authorization_endpoint='https://backend.example/device',
    )
    assert http.urls == ['https://backend.example/.well-known/oauth-authorization-server']


def test_gateway_auth_discovery_errors() -> None:
    class Response:
        def __init__(self, status_code: int, body: Any) -> None:
            self.status_code = status_code
            self._body = body

        def json(self) -> Any:
            return self._body

    class Http:
        def __init__(self, response: Response) -> None:
            self.response = response

        async def get(self, _url: str) -> Response:
            return self.response

    async def run(response: Response) -> None:
        await gateway_auth.discover_oauth_metadata(Http(response), 'https://backend.example')

    with pytest.raises(RuntimeError, match='OAuth discovery failed'):
        asyncio.run(run(Response(500, {})))
    with pytest.raises(RuntimeError, match="missing field 'device_authorization_endpoint'"):
        asyncio.run(run(Response(200, {'authorization_endpoint': 'a', 'token_endpoint': 't'})))
    with pytest.raises(RuntimeError, match='Expected JSON object response, got list'):
        asyncio.run(run(Response(200, [])))


def test_gateway_auth_cimd_client_posts_to_metadata_urls() -> None:
    class Http:
        def __init__(self) -> None:
            self.posts: list[tuple[str, dict[str, str]]] = []

        async def post(self, url: str, *, data: dict[str, str]) -> object:
            self.posts.append((url, data))
            return object()

    metadata = gateway_auth.OAuthMetadata(
        authorization_endpoint='https://backend.example/authorize',
        token_endpoint='https://backend.example/token',
        device_authorization_endpoint='https://backend.example/device',
    )

    async def run() -> Http:
        http = Http()
        client = gateway_auth.CimdOAuthClient(http, metadata, client_id='client-id')
        await client.start_device_authorization({'device': '1'})
        await client.post_token({'token': '1'})
        return http

    http = asyncio.run(run())

    assert http.posts == [
        ('https://backend.example/device', {'device': '1'}),
        ('https://backend.example/token', {'token': '1'}),
    ]


def test_gateway_auth_browser_callback_error_branches() -> None:
    async def run() -> None:
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, MockOAuthSession()),
            redirect_uri='http://127.0.0.1/callback',
            flow='browser',
        )

        assert auth.complete_browser_callback(error=None, error_description=None, code='code', state='state') == (
            gateway_auth.OAuthCallbackResult('No pending authorization', 'Return to the terminal.', status_code=400)
        )

        bootstrap = gateway_auth.AuthBootstrap(redirect_uri='http://127.0.0.1/callback', expected_state='expected')
        setattr(auth, '_auth_bootstrap', bootstrap)
        assert auth.complete_browser_callback(
            error='access_denied', error_description='nope', code=None, state=None
        ) == gateway_auth.OAuthCallbackResult('Authorization failed', 'access_denied: nope', status_code=400)
        assert bootstrap.error == 'access_denied: nope'
        assert bootstrap.event.is_set()

        bootstrap = gateway_auth.AuthBootstrap(redirect_uri='http://127.0.0.1/callback', expected_state='expected')
        setattr(auth, '_auth_bootstrap', bootstrap)
        assert auth.complete_browser_callback(error=None, error_description=None, code='code', state='wrong') == (
            gateway_auth.OAuthCallbackResult('Authorization failed', 'invalid or missing code/state', status_code=400)
        )
        assert bootstrap.error == 'invalid or missing code/state'
        assert bootstrap.event.is_set()

    asyncio.run(run())


def test_gateway_auth_code_flow_error_and_missing_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_open(_url: str) -> None:
        pass

    monkeypatch.setattr(gateway_auth.webbrowser, 'open', no_open)

    async def run(*, callback_error: str | None) -> None:
        client = MockCimdOAuthClient()
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='http://localhost:3000/oauth/authorize',
                token_endpoint='http://localhost:3000/oauth/token',
                device_authorization_endpoint='http://localhost:3000/oauth/device',
            ),
            resource='http://localhost:3000/proxy',
            scope='project:gateway_proxy',
        )
        bootstrap = gateway_auth.AuthBootstrap(redirect_uri='http://127.0.0.1:11465/callback')
        authorize_task = asyncio.create_task(session.auth_code_flow(bootstrap))
        for _ in range(10):
            if bootstrap.expected_state:
                break
            await asyncio.sleep(0)
        bootstrap.error = callback_error
        bootstrap.event.set()
        await authorize_task

    with pytest.raises(RuntimeError, match='authorization failed: access_denied'):
        asyncio.run(run(callback_error='access_denied'))
    with pytest.raises(RuntimeError, match='authorization completed without a code'):
        asyncio.run(run(callback_error=None))


class ConfigurableOAuthResponse:
    text = 'response-text'

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> Any:
        return self._body


class ConfigurableDeviceClient:
    client_id = 'client-id'

    def __init__(
        self, start_response: ConfigurableOAuthResponse, token_responses: list[ConfigurableOAuthResponse]
    ) -> None:
        self.start_response = start_response
        self.token_responses = token_responses
        self.token_requests: list[dict[str, str]] = []

    async def start_device_authorization(self, data: dict[str, str]) -> ConfigurableOAuthResponse:
        return self.start_response

    async def post_token(self, data: dict[str, str]) -> ConfigurableOAuthResponse:
        self.token_requests.append(data)
        return self.token_responses.pop(0)


def device_start_response(*, expires_in: int = 60, interval: int = 0) -> ConfigurableOAuthResponse:
    return ConfigurableOAuthResponse(
        200,
        {
            'device_code': 'device-code',
            'user_code': 'user-code',
            'verification_uri': 'https://backend.example/activate',
            'expires_in': expires_in,
            'interval': interval,
        },
    )


def device_token_error(error: str) -> ConfigurableOAuthResponse:
    return ConfigurableOAuthResponse(400, {'detail': {'error': error}})


def device_token_success() -> ConfigurableOAuthResponse:
    return ConfigurableOAuthResponse(200, {'access_token': 'access-token', 'refresh_token': 'refresh-token'})


def test_gateway_device_flow_errors_and_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_intervals: list[float] = []

    def no_open(_url: str) -> None:
        pass

    monkeypatch.setattr(gateway_auth.webbrowser, 'open', no_open)

    async def sleep(interval: float) -> None:
        sleep_intervals.append(interval)

    monkeypatch.setattr(gateway_auth.asyncio, 'sleep', sleep)

    def make_session(client: ConfigurableDeviceClient) -> gateway_auth.OAuthSession:
        return gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )

    async def run_device_flow(client: ConfigurableDeviceClient) -> None:
        await make_session(client).device_flow()

    with pytest.raises(RuntimeError, match=r'Device authorization failed \(500\): response-text'):
        asyncio.run(run_device_flow(ConfigurableDeviceClient(ConfigurableOAuthResponse(500, {}), [])))

    client = ConfigurableDeviceClient(
        device_start_response(interval=0), [device_token_error('authorization_pending'), device_token_success()]
    )
    asyncio.run(run_device_flow(client))
    assert len(client.token_requests) == 2

    sleep_intervals.clear()
    client = ConfigurableDeviceClient(
        device_start_response(interval=0), [device_token_error('slow_down'), device_token_success()]
    )
    asyncio.run(run_device_flow(client))
    assert sleep_intervals == [0, 5]

    with pytest.raises(RuntimeError, match='Device flow failed'):
        asyncio.run(
            run_device_flow(
                ConfigurableDeviceClient(device_start_response(interval=0), [device_token_error('invalid_grant')])
            )
        )

    with pytest.raises(RuntimeError, match='Device flow timed out'):
        asyncio.run(run_device_flow(ConfigurableDeviceClient(device_start_response(expires_in=0), [])))


def test_gateway_oauth_session_token_error_paths() -> None:
    async def run() -> None:
        metadata = gateway_auth.OAuthMetadata(
            authorization_endpoint='https://backend.example/authorize',
            token_endpoint='https://backend.example/token',
            device_authorization_endpoint='https://backend.example/device',
        )
        client = ConfigurableDeviceClient(device_start_response(), [])
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            metadata,
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )

        with pytest.raises(RuntimeError, match='gateway proxy used before authorization completed'):
            await session.current_access_token()
        with pytest.raises(RuntimeError, match='no refresh token; reauthorize'):
            await session.refresh()

        client.token_responses.append(ConfigurableOAuthResponse(500, {}))
        with pytest.raises(RuntimeError, match=r'token exchange failed \(500\): response-text'):
            post_token = cast(Callable[..., Coroutine[Any, Any, None]], getattr(session, '_post_token'))
            await post_token({'grant_type': 'authorization_code'}, error_prefix='token exchange failed')

        setattr(session, '_access_token', 'old-token')
        setattr(session, '_refresh_token', 'refresh-token')
        setattr(session, '_expires_at', 0.0)
        client.token_responses.append(ConfigurableOAuthResponse(200, {'access_token': 'new-token', 'expires_in': 3600}))

        assert await session.current_access_token() == 'new-token'
        assert client.token_requests[-1] == {
            'grant_type': 'refresh_token',
            'refresh_token': 'refresh-token',
            'client_id': 'client-id',
            'resource': 'https://backend.example/proxy',
        }

    asyncio.run(run())


def test_gateway_oauth_session_refresh_failure_falls_back_to_valid_token() -> None:
    async def run() -> tuple[str, int]:
        client = ConfigurableDeviceClient(device_start_response(), [ConfigurableOAuthResponse(500, {})])
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )
        setattr(session, '_access_token', 'old-token')
        setattr(session, '_refresh_token', 'refresh-token')
        setattr(session, '_expires_at', time.time() + 60)
        return await session.current_access_token(), len(client.token_requests)

    token, request_count = asyncio.run(run())

    assert token == 'old-token'
    assert request_count == 1


def test_gateway_oauth_session_refresh_failure_raises_for_expired_token() -> None:
    async def run() -> None:
        client = ConfigurableDeviceClient(device_start_response(), [ConfigurableOAuthResponse(500, {})])
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )
        setattr(session, '_access_token', 'old-token')
        setattr(session, '_refresh_token', 'refresh-token')
        setattr(session, '_expires_at', time.time() - 1)
        await session.current_access_token()

    with pytest.raises(RuntimeError, match=r'token refresh failed \(500\): response-text'):
        asyncio.run(run())


def test_gateway_oauth_session_missing_refresh_token_falls_back_to_valid_token() -> None:
    async def run() -> tuple[str, list[dict[str, str]]]:
        client = ConfigurableDeviceClient(device_start_response(), [])
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )
        setattr(session, '_access_token', 'old-token')
        setattr(session, '_expires_at', time.time() + 60)
        return await session.current_access_token(), client.token_requests

    token, token_requests = asyncio.run(run())

    assert token == 'old-token'
    assert token_requests == []


def test_gateway_oauth_session_uses_fresh_token_without_refresh() -> None:
    async def run() -> tuple[str, list[dict[str, str]]]:
        client = ConfigurableDeviceClient(device_start_response(), [])
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )
        setattr(session, '_access_token', 'old-token')
        setattr(session, '_expires_at', time.time() + 3600)
        return await session.current_access_token(), client.token_requests

    token, token_requests = asyncio.run(run())

    assert token == 'old-token'
    assert token_requests == []


def test_gateway_oauth_session_force_refresh() -> None:
    async def run() -> tuple[str, dict[str, str]]:
        client = ConfigurableDeviceClient(
            device_start_response(), [ConfigurableOAuthResponse(200, {'access_token': 'new-token', 'expires_in': 3600})]
        )
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, client),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )
        setattr(session, '_refresh_token', 'refresh-token')
        token = await session.force_refresh()
        return token, client.token_requests[-1]

    token, token_request = asyncio.run(run())

    assert token == 'new-token'
    assert token_request == {
        'grant_type': 'refresh_token',
        'refresh_token': 'refresh-token',
        'client_id': 'client-id',
        'resource': 'https://backend.example/proxy',
    }


def test_gateway_oauth_session_force_refresh_requires_access_token() -> None:
    async def run() -> None:
        session = gateway_auth.OAuthSession(
            cast(gateway_auth.CimdOAuthClient, ConfigurableDeviceClient(device_start_response(), [])),
            gateway_auth.OAuthMetadata(
                authorization_endpoint='https://backend.example/authorize',
                token_endpoint='https://backend.example/token',
                device_authorization_endpoint='https://backend.example/device',
            ),
            resource='https://backend.example/proxy',
            scope='project:gateway_proxy',
        )

        async def refresh_without_token() -> None:
            pass

        setattr(session, 'refresh', refresh_without_token)
        await session.force_refresh()

    with pytest.raises(RuntimeError, match='refresh did not return an access token'):
        asyncio.run(run())


def test_gateway_auth_recover_after_reauth_failure() -> None:
    class FailingReauthSession(MockOAuthSession):
        async def device_flow(self) -> None:
            raise RuntimeError('reauth failed')

    async def run() -> bool:
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, FailingReauthSession()),
            redirect_uri='http://127.0.0.1/callback',
            flow='device',
        )
        return await auth.recover_after_rejection(use_reauth=True)

    assert asyncio.run(run()) is False


def test_gateway_auth_recover_after_rejection_handles_non_runtime_refresh_failure() -> None:
    class FailingRefreshSession(MockOAuthSession):
        async def force_refresh(self) -> str:
            raise ValueError('refresh response was invalid')

    async def run() -> bool:
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, FailingRefreshSession()),
            redirect_uri='http://127.0.0.1/callback',
            flow='device',
        )
        return await auth.recover_after_rejection(use_reauth=False)

    assert asyncio.run(run()) is False


def test_gateway_auth_recover_after_rejection_handles_browser_timeout() -> None:
    class TimeoutReauthSession(MockOAuthSession):
        async def auth_code_flow(self, bootstrap: gateway_auth.AuthBootstrap) -> None:
            raise asyncio.TimeoutError

    async def run() -> bool:
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, TimeoutReauthSession()),
            redirect_uri='http://127.0.0.1/callback',
            flow='browser',
        )
        return await auth.recover_after_rejection(use_reauth=True)

    assert asyncio.run(run()) is False


def test_gateway_auth_current_access_token_delegates_to_session() -> None:
    async def run() -> str:
        auth = gateway_auth.GatewayAuth(
            cast(gateway_auth.OAuthSession, MockOAuthSession()),
            redirect_uri='http://127.0.0.1/callback',
            flow='device',
        )
        return await auth.current_access_token()

    assert asyncio.run(run()) == 'access-token'


def test_gateway_safe_json_object_handles_invalid_and_non_object_json() -> None:
    safe_json_object = getattr(gateway_auth, '_safe_json_object')

    class InvalidJSONResponse:
        text = 'not-json'

        def json(self) -> Any:
            raise ValueError('invalid')

    class ListJSONResponse:
        text = ''

        def json(self) -> Any:
            return ['not', 'an', 'object']

    assert safe_json_object(InvalidJSONResponse()) == {'raw': 'not-json'}
    assert safe_json_object(ListJSONResponse()) == {'raw': ['not', 'an', 'object']}


class MockGatewayResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.headers = {'content-type': 'application/json'}

    async def aread(self) -> bytes:
        return b'{}'


class MockGatewayClient:
    def __init__(self, responses: list[MockGatewayResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, str]] = []

    async def request(self, _method: str, _url: str, *, headers: dict[str, str], content: bytes) -> MockGatewayResponse:
        assert content == b'{}'
        self.requests.append(headers)
        return self.responses.pop(0)


class MockGatewayStreamResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.headers = {'content-type': 'text/event-stream'}
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True

    async def aiter_raw(self) -> AsyncIterator[bytes]:
        yield b'data: done\n\n'


class MockGatewayStreamingClient:
    def __init__(self, responses: list[MockGatewayStreamResponse]) -> None:
        self.responses = responses
        self.requests: list[dict[str, str]] = []

    def build_request(self, _method: str, _url: str, *, headers: dict[str, str], content: bytes) -> dict[str, Any]:
        assert content == b'{"stream": true}'
        return {'headers': headers}

    async def send(self, request: dict[str, Any], *, stream: bool) -> MockGatewayStreamResponse:
        assert stream is True
        self.requests.append(cast(dict[str, str], request['headers']))
        return self.responses.pop(0)


class MockGatewayAuth:
    def __init__(self) -> None:
        self.tokens = ['token-1', 'token-2', 'token-3']
        self.recoveries: list[bool] = []
        self.recovery_result = True

    async def current_access_token(self) -> str:
        return self.tokens.pop(0)

    async def recover_after_rejection(self, *, use_reauth: bool) -> bool:
        self.recoveries.append(use_reauth)
        return self.recovery_result

    def complete_browser_callback(
        self, *, error: str | None, error_description: str | None, code: str | None, state: str | None
    ) -> Any:
        raise AssertionError('callback handling is not used by gateway forwarding')


def test_gateway_request_recovers_auth_rejections() -> None:
    gateway_request = cast(
        Callable[
            [gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, tuple[int, Any, bytes, str]]
        ],
        getattr(gateway_cli, '_gateway_request'),
    )
    auth = MockGatewayAuth()
    client = MockGatewayClient([MockGatewayResponse(401), MockGatewayResponse(401), MockGatewayResponse(200)])
    state = gateway_cli.ProxyState(
        deps=Mock(),
        auth=cast(gateway_auth.GatewayAuth, auth),
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    status, _headers, body, content_type = asyncio.run(
        gateway_request(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{}')
    )

    assert (status, body, content_type) == (200, b'{}', 'application/json')
    assert auth.recoveries == [False, True]
    assert [request['Authorization'] for request in client.requests] == [
        'Bearer token-1',
        'Bearer token-2',
        'Bearer token-3',
    ]


def test_gateway_request_stops_when_auth_recovery_fails() -> None:
    gateway_request = cast(
        Callable[
            [gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, tuple[int, Any, bytes, str]]
        ],
        getattr(gateway_cli, '_gateway_request'),
    )
    auth = MockGatewayAuth()
    auth.recovery_result = False
    client = MockGatewayClient([MockGatewayResponse(401)])
    state = gateway_cli.ProxyState(
        deps=Mock(),
        auth=cast(gateway_auth.GatewayAuth, auth),
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    status, _headers, _body, _content_type = asyncio.run(
        gateway_request(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{}')
    )

    assert status == 401
    assert auth.recoveries == [False]
    assert len(client.requests) == 1


def test_gateway_stream_recovers_auth_rejections_and_closes_rejected_streams() -> None:
    gateway_stream = cast(
        Callable[[gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, Any]],
        getattr(gateway_cli, '_gateway_stream'),
    )
    auth = MockGatewayAuth()
    first_response = MockGatewayStreamResponse(401)
    second_response = MockGatewayStreamResponse(401)
    final_response = MockGatewayStreamResponse(200)
    client = MockGatewayStreamingClient([first_response, second_response, final_response])
    state = gateway_cli.ProxyState(
        deps=Mock(),
        auth=cast(gateway_auth.GatewayAuth, auth),
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    response = asyncio.run(
        gateway_stream(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{"stream": true}')
    )

    assert response is final_response
    assert first_response.closed
    assert second_response.closed
    assert not final_response.closed
    assert auth.recoveries == [False, True]
    assert [request['Authorization'] for request in client.requests] == [
        'Bearer token-1',
        'Bearer token-2',
        'Bearer token-3',
    ]


def test_gateway_stream_stops_when_auth_recovery_fails() -> None:
    gateway_stream = cast(
        Callable[[gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, Any]],
        getattr(gateway_cli, '_gateway_stream'),
    )
    auth = MockGatewayAuth()
    auth.recovery_result = False
    response = MockGatewayStreamResponse(401)
    client = MockGatewayStreamingClient([response])
    state = gateway_cli.ProxyState(
        deps=Mock(),
        auth=cast(gateway_auth.GatewayAuth, auth),
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    result = asyncio.run(
        gateway_stream(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{"stream": true}')
    )

    assert result is response
    assert not response.closed
    assert auth.recoveries == [False]
    assert len(client.requests) == 1


def test_gateway_proxy_stream_decodes_compressed_upstream_chunks() -> None:
    handle_proxy = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_proxy'))

    class CapturedStreamingResponse:
        def __init__(
            self,
            body_iterator: AsyncIterator[bytes],
            *,
            status_code: int,
            headers: dict[str, str],
            media_type: str | None,
        ) -> None:
            self.body_iterator = body_iterator
            self.status_code = status_code
            self.headers = headers
            self.media_type = media_type

    class CompressedStreamResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {'content-type': 'text/event-stream', 'content-encoding': 'gzip'}
            self.closed = False
            self.raw_iterated = False
            self.bytes_iterated = False

        async def aclose(self) -> None:
            self.closed = True

        async def aiter_raw(self) -> AsyncIterator[bytes]:
            self.raw_iterated = True
            yield gzip.compress(b'data: done\n\n')

        async def aiter_bytes(self) -> AsyncIterator[bytes]:
            self.bytes_iterated = True
            yield b'data: done\n\n'

    async def run() -> tuple[CapturedStreamingResponse, CompressedStreamResponse, bytes]:
        upstream_response = CompressedStreamResponse()
        deps = gateway_cli.GatewayDeps(
            httpx=Mock(),
            uvicorn=Mock(),
            Starlette=Mock(),
            Route=Mock(),
            Response=Mock(),
            JSONResponse=Mock(),
            StreamingResponse=CapturedStreamingResponse,
        )
        state = gateway_cli.ProxyState(
            deps=deps,
            auth=cast(gateway_auth.GatewayAuth, Mock()),
            client=Mock(),
            gateway='https://gateway.example.com',
            region='us',
            local_token='local-token',
        )
        request = types.SimpleNamespace(
            app=types.SimpleNamespace(state=types.SimpleNamespace(logfire_gateway=state)),
            url=types.SimpleNamespace(path='/proxy/openai/v1/chat/completions', query=''),
            headers={'authorization': 'Bearer local-token'},
            method='POST',
        )

        async def body() -> bytes:
            return b'{"stream": true}'

        request.body = body

        async def fake_gateway_stream(
            _state: gateway_cli.ProxyState, _method: str, _upstream_url: str, _headers: dict[str, str], _body: bytes
        ) -> CompressedStreamResponse:
            return upstream_response

        with patch.object(gateway_cli, '_gateway_stream', fake_gateway_stream):
            response = cast(CapturedStreamingResponse, await handle_proxy(request))

        chunks = [chunk async for chunk in response.body_iterator]
        return response, upstream_response, b''.join(chunks)

    response, upstream_response, body = asyncio.run(run())

    assert response.status_code == 200
    assert response.media_type == 'text/event-stream'
    assert 'content-encoding' not in response.headers
    assert body == b'data: done\n\n'
    assert upstream_response.bytes_iterated
    assert not upstream_response.raw_iterated
    assert upstream_response.closed


def test_gateway_authorize_and_serve_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    authorize_and_serve = getattr(gateway_cli, '_authorize_and_serve')
    clients: list[object] = []
    authorized: list[tuple[str, str]] = []

    class MetadataResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                'authorization_endpoint': 'https://backend.example/authorize',
                'token_endpoint': 'https://backend.example/token',
                'device_authorization_endpoint': 'https://backend.example/device',
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout
            clients.append(self)

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_exc_info: object) -> None:
            pass

        async def get(self, url: str) -> MetadataResponse:
            assert url == 'https://backend.example/.well-known/oauth-authorization-server'
            return MetadataResponse()

    class FakeConfig:
        def __init__(self, app: object, *, host: str, port: int, log_level: str, access_log: bool) -> None:
            self.app = app
            self.host = host
            self.port = port
            self.log_level = log_level
            self.access_log = access_log

    class FakeServer:
        def __init__(self, config: FakeConfig) -> None:
            self.config = config
            self.started = False
            self.should_exit = False

        async def serve(self) -> None:
            self.started = True

    class FakeUvicorn:
        Config = FakeConfig
        Server = FakeServer

    class FakeStarlette:
        def __init__(self, *, routes: list[object]) -> None:
            self.routes = routes
            self.state = types.SimpleNamespace()

    class FakeGatewayAuth:
        def __init__(self, _session: gateway_auth.OAuthSession, *, redirect_uri: str, flow: str) -> None:
            self.redirect_uri = redirect_uri
            self.flow = flow

        async def authorize(self) -> None:
            authorized.append((self.redirect_uri, self.flow))

    def fake_route(
        path: str, endpoint: Callable[..., Any], methods: list[str] | None = None
    ) -> tuple[str, Callable[..., Any], list[str] | None]:
        return path, endpoint, methods

    def token_urlsafe(_length: int) -> str:
        return 'local-token'

    deps = gateway_cli.GatewayDeps(
        httpx=types.SimpleNamespace(AsyncClient=FakeAsyncClient),
        uvicorn=FakeUvicorn,
        Starlette=FakeStarlette,
        Route=fake_route,
        Response=Mock(),
        JSONResponse=Mock(),
        StreamingResponse=Mock(),
    )
    monkeypatch.setattr(gateway_cli, 'GatewayAuth', FakeGatewayAuth)
    monkeypatch.setattr(gateway_cli.secrets, 'token_urlsafe', token_urlsafe)

    async def run() -> tuple[gateway_cli.ProxyState, str]:
        async with authorize_and_serve(
            deps=deps,
            region='us',
            backend='https://backend.example',
            gateway='https://gateway.example/',
            client_id='client-id',
            scope='scope',
            port=9999,
            flow='device',
        ) as result:
            return result

    state, proxy_base = asyncio.run(run())

    assert [cast(Any, client).timeout for client in clients] == [30.0, 180.0]
    assert authorized == [('http://127.0.0.1:9999/callback', 'device')]
    assert state.gateway == 'https://gateway.example'
    assert state.region == 'us'
    assert state.local_token == 'local-token'
    assert proxy_base == 'http://127.0.0.1:9999'


def test_gateway_authorize_and_serve_fails_when_server_does_not_start() -> None:
    authorize_and_serve = getattr(gateway_cli, '_authorize_and_serve')

    class MetadataResponse:
        status_code = 200

        def json(self) -> dict[str, str]:
            return {
                'authorization_endpoint': 'https://backend.example/authorize',
                'token_endpoint': 'https://backend.example/token',
                'device_authorization_endpoint': 'https://backend.example/device',
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *_exc_info: object) -> None:
            pass

        async def get(self, _url: str) -> MetadataResponse:
            return MetadataResponse()

    class FakeServer:
        started = False
        should_exit = False

        def __init__(self, _config: object) -> None:
            pass

        async def serve(self) -> None:
            pass

    class FakeStarlette:
        def __init__(self, *, routes: list[object]) -> None:
            self.routes = routes
            self.state = types.SimpleNamespace()

    def fake_config(*_args: object, **_kwargs: object) -> object:
        return object()

    def fake_route(
        path: str, endpoint: Callable[..., Any], methods: list[str] | None = None
    ) -> tuple[str, Callable[..., Any], list[str] | None]:
        return path, endpoint, methods

    deps = gateway_cli.GatewayDeps(
        httpx=types.SimpleNamespace(AsyncClient=FakeAsyncClient),
        uvicorn=types.SimpleNamespace(
            Config=fake_config,
            Server=FakeServer,
        ),
        Starlette=FakeStarlette,
        Route=fake_route,
        Response=Mock(),
        JSONResponse=Mock(),
        StreamingResponse=Mock(),
    )

    async def run() -> None:
        async with authorize_and_serve(
            deps=deps,
            region='us',
            backend='https://backend.example',
            gateway='https://gateway.example',
            client_id='client-id',
            scope='scope',
            port=9999,
            flow='device',
        ):
            raise AssertionError('context should not be entered')

    with pytest.raises(RuntimeError, match='Logfire Gateway proxy failed to start'):
        asyncio.run(run())


def test_gateway_run_launch_config_only(capsys: pytest.CaptureFixture[str]) -> None:
    run_launch = getattr(gateway_cli, '_run_launch')
    context = gateway_cli.GatewayCommandContext(raw_args=['launch', 'codex', '--config'], region='eu', logfire_url=None)

    assert run_launch(['codex', '--config'], context) == 0

    err = capsys.readouterr().err
    assert 'OpenAI Codex (codex)' in err
    assert 'region: eu' in err
    assert 'OPENAI_API_KEY=<generated-local-gateway-token>' in err


def test_gateway_run_launch_config_only_opencode_creates_example_config(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_launch = getattr(gateway_cli, '_run_launch')
    context = gateway_cli.GatewayCommandContext(
        raw_args=['launch', 'opencode', '--config'], region='us', logfire_url=None
    )

    monkeypatch.setattr(gateway_cli.tempfile, 'gettempdir', lambda: str(tmp_path))

    assert run_launch(['opencode', '--config'], context) == 0

    assert (tmp_path / 'logfire-gateway-example' / 'opencode.jsonc').exists()
    assert 'OPENCODE_CONFIG=' in capsys.readouterr().err


def test_gateway_configure_only_prints_unset_env(capsys: pytest.CaptureFixture[str]) -> None:
    configure_only = getattr(gateway_cli, '_configure_only')
    integration = ai_tools.AiToolIntegration(
        name='test',
        display_name='Test Tool',
        binary='test-tool',
        env={'EMPTY_VALUE': ''},
    )

    configure_only(integration, region='us', model=None)

    assert 'unset EMPTY_VALUE' in capsys.readouterr().err


def test_gateway_interactive_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    interactive_integration = getattr(gateway_cli, '_interactive_integration')

    def missing_binary(_self: ai_tools.AiToolIntegration) -> None:
        return None

    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', missing_binary)

    with pytest.raises(SystemExit) as exc_info:
        interactive_integration()

    assert exc_info.value.code == 127

    def fake_ai_tool_names() -> tuple[str, ...]:
        return ('codex',)

    def fake_resolve_ai_tool(_name: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(binary_path=lambda: '/bin/codex')

    def fake_prompt_ask(_message: str, *, choices: list[str], default: str) -> str:
        assert choices == ['codex']
        assert default == 'codex'
        return 'codex'

    monkeypatch.setattr(gateway_cli, 'ai_tool_names', fake_ai_tool_names)
    monkeypatch.setattr(gateway_cli, 'resolve_ai_tool', fake_resolve_ai_tool)
    monkeypatch.setattr(gateway_cli.Prompt, 'ask', fake_prompt_ask)

    assert interactive_integration() == 'codex'


def test_gateway_run_launch_returns_127_for_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    run_launch = getattr(gateway_cli, '_run_launch')

    def missing_binary(_self: ai_tools.AiToolIntegration) -> None:
        return None

    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', missing_binary)

    code = run_launch(
        ['codex'], gateway_cli.GatewayCommandContext(raw_args=['launch', 'codex'], region=None, logfire_url=None)
    )

    assert code == 127


def test_gateway_run_launch_dispatches_parsed_options(monkeypatch: pytest.MonkeyPatch) -> None:
    run_launch = getattr(gateway_cli, '_run_launch')
    captured: dict[str, Any] = {}

    async def launch_async(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 17

    def binary_path(self: ai_tools.AiToolIntegration) -> str:
        return f'/bin/{self.binary}'

    def pick_next_port(port: int) -> int:
        return port + 1

    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', binary_path)
    monkeypatch.setattr(gateway_cli, 'load_gateway_deps', lambda: 'deps')
    monkeypatch.setattr(gateway_cli, '_pick_port', pick_next_port)
    monkeypatch.setattr(gateway_cli, '_launch_async', launch_async)

    code = run_launch(
        [
            'codex',
            '--model',
            'gpt-5',
            '--device-flow',
            '--port',
            '1234',
            '--gateway-url',
            'https://gateway.example/',
            '--',
            '--flag',
        ],
        gateway_cli.GatewayCommandContext(raw_args=[], region='eu', logfire_url='https://backend.example/'),
    )

    assert code == 17
    assert captured['deps'] == 'deps'
    assert captured['integration'].name == 'codex'
    assert captured['extra'] == ['--flag']
    assert captured['region'] == 'eu'
    assert captured['backend'] == 'https://backend.example'
    assert captured['gateway'] == 'https://gateway.example'
    assert captured['client_id'] == 'https://backend.example/clients/logfire-gateway.json'
    assert captured['port'] == 1235
    assert captured['model'] == 'gpt-5'
    assert captured['flow'] == 'device'


def test_gateway_launch_async_runs_child_with_gateway_env(monkeypatch: pytest.MonkeyPatch) -> None:
    launch_async = getattr(gateway_cli, '_launch_async')
    captured: dict[str, Any] = {}

    class FakeProcess:
        async def wait(self) -> int:
            return 23

    @asynccontextmanager
    async def authorize_and_serve(**_kwargs: Any) -> AsyncGenerator[tuple[gateway_cli.ProxyState, str], None]:
        state = gateway_cli.ProxyState(
            deps=Mock(),
            auth=cast(gateway_auth.GatewayAuth, Mock()),
            client=Mock(),
            gateway='https://gateway.example.com',
            region='us',
            local_token='local-token',
        )
        yield state, 'http://127.0.0.1:9999'

    async def create_subprocess_exec(binary: str, *args: str, env: dict[str, str]) -> FakeProcess:
        captured.update(binary=binary, args=args, env=env)
        return FakeProcess()

    def binary_path(self: ai_tools.AiToolIntegration) -> str:
        return f'/bin/{self.binary}'

    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', binary_path)
    monkeypatch.setattr(gateway_cli, '_authorize_and_serve', authorize_and_serve)
    monkeypatch.setattr(gateway_cli.asyncio, 'create_subprocess_exec', create_subprocess_exec)

    code = asyncio.run(
        launch_async(
            deps=Mock(),
            integration=ai_tools.resolve_ai_tool('codex'),
            extra=['--flag'],
            region='us',
            backend='https://backend.example',
            gateway='https://gateway.example',
            client_id='https://backend.example/clients/logfire-gateway.json',
            scope='scope',
            port=9999,
            model='gpt-5',
            flow='browser',
        )
    )

    assert code == 23
    assert captured['binary'] == '/bin/codex'
    assert captured['args'] == ('--flag',)
    assert captured['env']['OPENAI_BASE_URL'] == 'http://127.0.0.1:9999/proxy/openai/v1'
    assert captured['env']['OPENAI_API_KEY'] == 'local-token'
    assert captured['env']['OPENAI_MODEL'] == 'gpt-5'


def test_gateway_launch_async_handles_missing_binary_and_notice(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    launch_async = getattr(gateway_cli, '_launch_async')

    missing_integration = ai_tools.AiToolIntegration(
        name='missing', display_name='Missing Tool', binary='missing-tool', env={}
    )

    def missing_binary(_self: ai_tools.AiToolIntegration) -> None:
        return None

    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', missing_binary)

    assert (
        asyncio.run(
            launch_async(
                deps=Mock(),
                integration=missing_integration,
                extra=[],
                region='us',
                backend='https://backend.example',
                gateway='https://gateway.example',
                client_id='https://backend.example/clients/logfire-gateway.json',
                scope='scope',
                port=9999,
                model=None,
                flow='browser',
            )
        )
        == 127
    )

    class FakeProcess:
        async def wait(self) -> int:
            return 24

    @asynccontextmanager
    async def authorize_and_serve(**_kwargs: Any) -> AsyncGenerator[tuple[gateway_cli.ProxyState, str], None]:
        state = gateway_cli.ProxyState(
            deps=Mock(),
            auth=cast(gateway_auth.GatewayAuth, Mock()),
            client=Mock(),
            gateway='https://gateway.example.com',
            region='us',
            local_token='local-token',
        )
        yield state, 'http://127.0.0.1:9999'

    async def create_subprocess_exec(_binary: str, *_args: str, env: dict[str, str]) -> FakeProcess:
        assert env['OPENAI_API_KEY'] == 'local-token'
        return FakeProcess()

    def binary_path(_self: ai_tools.AiToolIntegration) -> str:
        return '/bin/noticed-tool'

    noticed_integration = ai_tools.AiToolIntegration(
        name='noticed',
        display_name='Noticed Tool',
        binary='noticed-tool',
        env={'OPENAI_API_KEY': '{local_token}'},
        notice='Use {base} with {local_token}',
    )
    monkeypatch.setattr(ai_tools.AiToolIntegration, 'binary_path', binary_path)
    monkeypatch.setattr(gateway_cli, '_authorize_and_serve', authorize_and_serve)
    monkeypatch.setattr(gateway_cli.asyncio, 'create_subprocess_exec', create_subprocess_exec)

    assert (
        asyncio.run(
            launch_async(
                deps=Mock(),
                integration=noticed_integration,
                extra=[],
                region='us',
                backend='https://backend.example',
                gateway='https://gateway.example',
                client_id='https://backend.example/clients/logfire-gateway.json',
                scope='scope',
                port=9999,
                model=None,
                flow='browser',
            )
        )
        == 24
    )
    assert 'Use http://127.0.0.1:9999 with local-token' in capsys.readouterr().err


def test_gateway_run_serve_async_returns_130_on_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    run_serve_async = getattr(gateway_cli, '_run_serve_async')

    @asynccontextmanager
    async def authorize_and_serve(**_kwargs: Any) -> AsyncGenerator[tuple[gateway_cli.ProxyState, str], None]:
        state = gateway_cli.ProxyState(
            deps=Mock(),
            auth=cast(gateway_auth.GatewayAuth, Mock()),
            client=Mock(),
            gateway='https://gateway.example.com',
            region='us',
            local_token='local-token',
        )
        yield state, 'http://127.0.0.1:9999'

    async def sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    def load_gateway_deps() -> Mock:
        return Mock()

    def pick_same_port(port: int) -> int:
        return port

    monkeypatch.setattr(gateway_cli, 'load_gateway_deps', load_gateway_deps)
    monkeypatch.setattr(gateway_cli, '_pick_port', pick_same_port)
    monkeypatch.setattr(gateway_cli, '_authorize_and_serve', authorize_and_serve)
    monkeypatch.setattr(gateway_cli.asyncio, 'sleep', sleep)

    code = asyncio.run(
        run_serve_async(
            argparse.Namespace(gateway_region='us', logfire_url=None, gateway_url=None, port=9999, device_flow=False)
        )
    )

    assert code == 130


def test_gateway_run_serve_dispatches_parsed_options(monkeypatch: pytest.MonkeyPatch) -> None:
    run_serve = getattr(gateway_cli, '_run_serve')
    captured: dict[str, Any] = {}

    async def run_serve_async(args: argparse.Namespace) -> int:
        captured.update(vars(args))
        return 19

    monkeypatch.setattr(gateway_cli, '_run_serve_async', run_serve_async)

    code = run_serve(
        ['--device-flow', '--port', '1234', '--gateway-url', 'https://gateway.example/'],
        gateway_cli.GatewayCommandContext(raw_args=[], region='eu', logfire_url='https://backend.example/'),
    )

    assert code == 19
    assert captured['device_flow'] is True
    assert captured['port'] == 1234
    assert captured['gateway_url'] == 'https://gateway.example/'
    assert captured['gateway_region'] == 'eu'
    assert captured['logfire_url'] == 'https://backend.example/'


def test_gateway_execute_command_handles_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def raise_config_error(_raw: list[str], _context: gateway_cli.GatewayCommandContext) -> int:
        raise LogfireConfigError('missing dependency')

    def raise_keyboard_interrupt(_raw: list[str], _context: gateway_cli.GatewayCommandContext) -> int:
        raise KeyboardInterrupt

    context = gateway_cli.GatewayCommandContext(raw_args=[], region=None, logfire_url=None)
    monkeypatch.setattr(gateway_cli, '_run_launch', raise_config_error)

    assert gateway_cli.execute_gateway_command(gateway_cli.GatewayCommand('launch', ()), context) == 1
    assert capsys.readouterr().err == 'missing dependency\n'

    monkeypatch.setattr(gateway_cli, '_run_launch', raise_keyboard_interrupt)
    assert gateway_cli.execute_gateway_command(gateway_cli.GatewayCommand('launch', ()), context) == 130


def test_instrumented_packages_text_filters_starlette_and_urllib3():
    # Both special cases: fastapi/starlette and requests/urllib3
    installed_otel_pkgs = {
        'opentelemetry-instrumentation-fastapi',
        'opentelemetry-instrumentation-starlette',
        'opentelemetry-instrumentation-requests',
        'opentelemetry-instrumentation-urllib3',
    }
    instrumented_packages = ['fastapi', 'starlette', 'requests', 'urllib3']
    installed_pkgs = {'fastapi', 'starlette', 'requests', 'urllib3'}

    text = instrumented_packages_text(installed_otel_pkgs, instrumented_packages, installed_pkgs)
    assert str(text) == snapshot(
        """\
Your instrumentation checklist:

✓ fastapi (installed and instrumented)
✓ requests (installed and instrumented)
"""
    )


def test_parse_run_no_script(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', Mock())

    with pytest.raises(SystemExit):
        main(['run', '--no-summary'])

    assert configure_mock.call_count == 1


def test_parse_run_script(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--no-summary', run_script_test.__file__, '-x', 'foo'])

    assert configure_mock.call_count == 1
    assert capsys.readouterr().out == 'hi from run_script_test.py\n'
    assert instrument_package_mock.call_args_list == [(('openai',),)]


def test_parse_run_script_with_summary(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--summary', run_script_test.__file__, '-x', 'foo'])

    assert configure_mock.call_count == 1
    out, err = capsys.readouterr()
    assert out == snapshot('hi from run_script_test.py\n')
    assert 'To hide this summary box, use: logfire run --no-summary.' in err
    assert instrument_package_mock.call_args_list == [(('openai',),)]


def test_parse_run_module(
    tmp_dir_cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_dir_cwd / 'main.py').write_text(Path(run_script_test.__file__).read_text())
    monkeypatch.setattr('logfire.configure', configure_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.instrument_package', instrument_package_mock := Mock())
    monkeypatch.setattr('logfire._internal.cli.run.OTEL_INSTRUMENTATION_MAP', {'openai': 'openai'})

    main(['run', '--no-summary', '-m', 'main', '-x', 'foo'])

    assert configure_mock.call_count == 1
    assert capsys.readouterr().out == snapshot('hi from run_script_test.py\n')
    assert instrument_package_mock.call_args_list == [(('openai',),)]


@pytest.fixture()
def prompt_http_calls() -> Generator[None]:
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/prompts',
            response_list=[
                {
                    'json': {'prompt': 'This is the prompt\n'},
                }
            ],
        )

        m.post(
            'https://logfire-us.pydantic.dev/v1/organizations/fake_org/projects/myproject/read-tokens',
            json={'token': 'fake_token'},
        )

        yield


def test_parse_prompt(prompt_http_calls: None, capsys: pytest.CaptureFixture[str]) -> None:
    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123'])

    assert capsys.readouterr().out == snapshot('This is the prompt\n')


def test_parse_prompt_without_project_errors(prompt_http_calls: None, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(['prompt'])

    assert capsys.readouterr().err == snapshot(
        'The --project option is required unless configuring an agent integration.\n'
    )


def test_ai_tool_names() -> None:
    from logfire._internal.cli.ai_tools import ai_tool_names

    assert ai_tool_names() == snapshot(('claude', 'codex', 'opencode'))


def test_resolve_ai_tool_unknown() -> None:
    from logfire._internal.cli.ai_tools import resolve_ai_tool

    with pytest.raises(SystemExit) as exc_info:
        resolve_ai_tool('unknown')

    assert str(exc_info.value) == snapshot("unknown AI tool integration: 'unknown'. Available: claude, codex, opencode")


def test_ai_tool_without_mcp_config_errors() -> None:
    from rich.console import Console

    from logfire._internal.cli.ai_tools import AiToolIntegration

    integration = AiToolIntegration(name='test', display_name='Test Tool', binary='test', env={})

    with pytest.raises(LogfireConfigError, match='Test Tool does not support Logfire MCP configuration.'):
        integration.configure_mcp_server(
            mcp_url='https://example.com/mcp', console=Console(file=io.StringIO()), update=False
        )


def test_parse_prompt_codex(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    codex_config_path.write_text('')

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex'])

    assert codex_config_path.read_text() == snapshot("""\

[mcp_servers.logfire]
url = "https://logfire-us.pydantic.dev/mcp"
""")
    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot("""\
Logfire MCP server added to Codex.
""")


def test_parse_prompt_codex_without_project(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    codex_config_path.write_text('')

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}):
        main(['prompt', '--codex'])

    assert codex_config_path.read_text() == snapshot("""\

[mcp_servers.logfire]
url = "https://logfire-us.pydantic.dev/mcp"
""")
    out, err = capsys.readouterr()
    assert out == ''
    assert err == snapshot("""\
Logfire MCP server added to Codex.
""")


def test_parse_prompt_codex_not_installed(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: False)  # type: ignore

    with pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex'])

    assert capsys.readouterr().err == snapshot("""\
codex is not installed. Install `codex`, or remove the `--codex` flag.
""")


def test_parse_prompt_codex_config_not_found(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}), pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex'])

    assert capsys.readouterr().err == snapshot(
        'Codex config file not found. Install `codex`, or remove the `--codex` flag.\n'
    )


def test_parse_prompt_codex_logfire_mcp_installed(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    existing = '[mcp_servers.logfire]\nurl = "https://old.example/mcp"\n'
    codex_config_path.write_text(existing)

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex'])

    assert codex_config_path.read_text() == existing
    assert capsys.readouterr().out == snapshot('This is the prompt\n')


def test_parse_prompt_codex_logfire_mcp_update(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    codex_config_path.write_text('[mcp_servers.logfire]\nurl = "https://old.example/mcp"\n')

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex', '--update'])

    assert codex_config_path.read_text() == snapshot("""\

[mcp_servers.logfire]
url = "https://logfire-us.pydantic.dev/mcp"
""")
    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot('Logfire MCP server updated in Codex.\n')


def test_parse_prompt_codex_invalid_toml(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    codex_config_path.write_text('this is = invalid [ toml')

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}), pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex'])

    out, err = capsys.readouterr()
    assert out == snapshot('')
    assert 'Failed to parse' in err
    assert 'TOML' in err


def test_parse_prompt_codex_logfire_mcp_update_legacy_stdio(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replacing a config written by the previous (stdio) CLI version must consume the full section,
    including TOML values that contain `[` (e.g. `args = ["logfire-mcp@latest"]`).
    """
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    codex_path = tmp_path / 'codex'
    codex_path.mkdir()
    codex_config_path = codex_path / 'config.toml'
    codex_config_path.write_text(
        '[other]\nfoo = "bar"\n'
        '\n[mcp_servers.logfire]\n'
        'command = "uvx"\n'
        'args = ["logfire-mcp@latest"]\n'
        'env = { "LOGFIRE_READ_TOKEN" = "fake_token" }\n'
        '\n[after]\nbaz = 1\n'
    )

    with patch.dict(os.environ, {'CODEX_HOME': str(codex_path)}):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--codex', '--update'])

    content = codex_config_path.read_text()
    assert 'logfire-mcp@latest' not in content
    assert 'LOGFIRE_READ_TOKEN' not in content
    assert 'url = "https://logfire-us.pydantic.dev/mcp"' in content
    assert '[other]' in content and '[after]' in content


def test_parse_prompt_claude(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    def logfire_mcp_installed(_: list[str]) -> bytes:
        return b'logfire: https://logfire-us.pydantic.dev/mcp\n'

    monkeypatch.setattr(subprocess, 'check_output', logfire_mcp_installed)
    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--claude'])

    assert capsys.readouterr().out == snapshot('This is the prompt\n')


def test_parse_prompt_claude_update(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    calls: list[list[str]] = []

    def check_output(cmd: list[str]) -> bytes:
        calls.append(cmd)
        if cmd[:3] == ['claude', 'mcp', 'list']:
            return b'logfire: https://old.example/mcp\n'
        return b''

    monkeypatch.setattr(subprocess, 'check_output', check_output)
    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--claude', '--update'])

    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot('Logfire MCP server updated in Claude.\n')
    assert ['claude', 'mcp', 'remove', 'logfire'] in calls
    assert [
        'claude',
        'mcp',
        'add',
        '--transport',
        'http',
        'logfire',
        'https://logfire-us.pydantic.dev/mcp',
    ] in calls


def test_parse_prompt_claude_not_installed(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: False)  # type: ignore

    with pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--claude'])

    assert capsys.readouterr().err == snapshot("""\
claude is not installed. Install `claude`, or remove the `--claude` flag.
""")


def test_parse_prompt_claude_no_mcp(
    prompt_http_calls: None, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore

    def logfire_mcp_installed(_: list[str]) -> bytes:
        return b'not installed'

    monkeypatch.setattr(subprocess, 'check_output', logfire_mcp_installed)
    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--claude'])

    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot("""\
Logfire MCP server added to Claude.
""")


def test_parse_prompt_opencode(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    out, err = capsys.readouterr()
    assert out == snapshot("""\
This is the prompt
""")
    assert err == snapshot("""\
Logfire MCP server added to OpenCode.
""")


def test_parse_prompt_opencode_no_git(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    def check_output(x: list[str]) -> bytes:
        raise subprocess.CalledProcessError(1, x)

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    out, err = capsys.readouterr()
    assert out == snapshot("""\
This is the prompt
""")
    assert err == snapshot("""\
Logfire MCP server added to OpenCode.
""")


def test_parse_prompt_opencode_not_installed(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: False)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    with pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    out, err = capsys.readouterr()
    assert out == snapshot('')
    assert err == snapshot("""\
opencode is not installed. Install `opencode`, or remove the `--opencode` flag.
""")


def test_parse_prompt_opencode_whitespace_only_config(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    (tmp_path / 'opencode.jsonc').write_text('   \n\t\n')

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    config = json.loads((tmp_path / 'opencode.jsonc').read_text())
    assert config == snapshot(
        {'mcp': {'logfire-mcp': {'type': 'remote', 'url': 'https://logfire-us.pydantic.dev/mcp'}}}
    )


def test_parse_prompt_opencode_invalid_jsonc(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    (tmp_path / 'opencode.jsonc').write_text('// JSONC comment\n{"mcp": {}}')

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    with pytest.raises(SystemExit):
        main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    out, err = capsys.readouterr()
    assert out == snapshot('')
    assert 'Failed to parse' in err
    assert 'JSONC' in err


def test_parse_prompt_opencode_logfire_mcp_installed(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    existing = json.dumps(
        {'mcp': {'logfire-mcp': {'type': 'remote', 'url': 'https://old.example/mcp'}}},
        indent=2,
    )
    (tmp_path / 'opencode.jsonc').write_text(existing)

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    assert (tmp_path / 'opencode.jsonc').read_text() == existing
    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot('')


def test_parse_prompt_opencode_logfire_mcp_update(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    (tmp_path / 'opencode.jsonc').write_text(
        json.dumps({'mcp': {'logfire-mcp': {'type': 'remote', 'url': 'https://old.example/mcp'}}})
    )

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode', '--update'])

    config = json.loads((tmp_path / 'opencode.jsonc').read_text())
    assert config == snapshot(
        {'mcp': {'logfire-mcp': {'type': 'remote', 'url': 'https://logfire-us.pydantic.dev/mcp'}}}
    )
    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot('Logfire MCP server updated in OpenCode.\n')


def test_parse_opencode_logfire_mcp_not_installed_with_existing_config(
    prompt_http_calls: None,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, 'which', lambda x: True)  # type: ignore
    monkeypatch.setattr(Path, 'cwd', lambda: tmp_path)

    (tmp_path / 'opencode.jsonc').write_text('{}')

    def check_output(x: list[str]) -> bytes:
        return tmp_path.as_posix().encode('utf-8')

    monkeypatch.setattr(subprocess, 'check_output', check_output)

    main(['prompt', '--project', 'fake_org/myproject', 'fix-span-issue:123', '--opencode'])

    out, err = capsys.readouterr()
    assert out == snapshot('This is the prompt\n')
    assert err == snapshot("""\
Logfire MCP server added to OpenCode.
""")


def test_base_url_and_logfire_url(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
):
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    with pytest.warns(
        DeprecationWarning, match='The `--logfire-url` argument is deprecated. Use `--base-url` instead.'
    ):
        main(['--logfire-url', 'https://logfire-us.pydantic.dev', 'whoami'])


def test_main_module() -> None:
    """Test that logfire.__main__ is importable for coverage."""
    assert subprocess.run([sys.executable, '-m', 'logfire', '--help'], check=True).returncode == 0
