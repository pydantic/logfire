from __future__ import annotations

import argparse
import asyncio
import gzip
import importlib
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Any, cast
from unittest.mock import Mock, call, patch
from urllib.parse import parse_qs, urlparse

import httpx
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
from logfire._internal.cli import (
    READ_TOKEN_TTL,
    STATUS_MAX_ROWS,
    OrgProjectAction,
    SplitArgs,
    _has_git_dir,  # pyright: ignore[reportPrivateUsage]
    _is_git_tracked,  # pyright: ignore[reportPrivateUsage]
    _load_saved_read_token,  # pyright: ignore[reportPrivateUsage]
    _organization_from_project_url,  # pyright: ignore[reportPrivateUsage]
    main,
)
from logfire._internal.cli.run import (
    InstrumentationRecommendation,
    collect_instrumentation_context,
    find_recommended_instrumentations_to_install,
    get_recommendation_texts,
    instrument_packages,
    instrumented_packages_text,
)
from logfire._internal.config import LogfireConfigWarning, LogfireCredentials, sanitize_project_name
from logfire._internal.utils import READ_TOKEN_FILENAME
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
    # argparse wraps the usage line, so match the parts rather than the layout.
    out = capsys.readouterr().out
    assert 'usage: logfire [-h] [--version] [--non-interactive]' in out
    assert '[--base-url BASE_URL |' in out
    assert '--region {us,eu}]' in out


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


def test_whoami_unknown_token_region(capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch.dict(os.environ, {'LOGFIRE_TOKEN': 'pylf_v1_unknownregion_foobar'}),
        requests_mock.Mocker() as request_mocker,
    ):
        request_mocker.get(
            'https://logfire-us.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        with pytest.warns(LogfireConfigWarning, match="Unknown region 'unknownregion'"):
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
            main(['--base-url=http://localhost:0', 'whoami', '--data-dir', str(tmp_dir_cwd)])

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

        main(['--base-url=http://localhost:0', 'whoami', '--data-dir', str(tmp_dir_cwd)])
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


def test_clean_then_write_creds_file_restores_gitignore(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO('y'))
    data_dir = tmp_dir_cwd / '.logfire'

    logfire_credentials.write_creds_file(data_dir)
    assert (data_dir / '.gitignore').read_text() == '*'

    main(shlex.split(f'clean --data-dir {str(data_dir)}'))
    assert not (data_dir / '.gitignore').exists()

    logfire_credentials.write_creds_file(data_dir)
    assert (data_dir / '.gitignore').read_text() == '*'


def test_write_creds_file_keeps_existing_gitignore(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials) -> None:
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    (data_dir / '.gitignore').write_text('logfire_credentials.json\n')

    logfire_credentials.write_creds_file(data_dir)
    assert (data_dir / '.gitignore').read_text() == 'logfire_credentials.json\n'


def test_write_creds_file_does_not_follow_gitignore_symlink(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials
) -> None:
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    outside = tmp_dir_cwd / 'outside'
    (data_dir / '.gitignore').symlink_to(outside)

    logfire_credentials.write_creds_file(data_dir)
    assert not outside.exists()


@pytest.mark.parametrize(
    'existing_files,gitignored',
    [
        ([], True),
        (['logfire_credentials.json'], True),
        (['main.py'], False),
    ],
)
def test_write_creds_file_gitignores_existing_data_dir(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    existing_files: list[str],
    gitignored: bool,
) -> None:
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    for name in existing_files:
        (data_dir / name).touch()

    logfire_credentials.write_creds_file(data_dir)
    assert (data_dir / '.gitignore').exists() is gitignored


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
│  ☐ urllib [*] (need to install opentelemetry-instrumentation-urllib)                                                                               │
│                                                                                                                                                    │
│  [*] `urllib` may not actually be used by your app, in which case you can ignore this recommendation                                               │
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
                    InstrumentationRecommendation('opentelemetry-instrumentation-fastapi', ('fastapi',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-urllib', ('urllib',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
                }
            ),
        ),
        (
            {
                'opentelemetry-instrumentation-fastapi': 'fastapi',
                'opentelemetry-instrumentation-starlette': 'starlette',
            },
            {'fastapi', 'starlette'},
            snapshot({InstrumentationRecommendation('opentelemetry-instrumentation-fastapi', ('fastapi',))}),
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
                    InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
                    InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
                }
            ),
        ),
        (
            {'opentelemetry-instrumentation-starlette': 'starlette'},
            {'starlette'},
            snapshot({InstrumentationRecommendation('opentelemetry-instrumentation-starlette', ('starlette',))}),
        ),
    ],
)
def test_recommended_packages_with_dependencies(
    otel_instrumentation_map: dict[str, str],
    installed: set[str],
    should_install: set[InstrumentationRecommendation],
) -> None:
    recommendations = find_recommended_instrumentations_to_install(otel_instrumentation_map, set(), installed)
    assert recommendations == should_install


HTTPX_OTEL_PACKAGE = 'opentelemetry-instrumentation-httpx'
PSYCOPG_OTEL_PACKAGES = {
    'opentelemetry-instrumentation-psycopg': 'psycopg',
    'opentelemetry-instrumentation-psycopg2': 'psycopg',
}


@pytest.mark.parametrize(
    ('installed_clients', 'otel_version', 'expected'),
    [
        (
            {'httpx'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx',)),
        ),
        (
            {'httpx2'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0'),
        ),
        (
            {'httpx', 'httpx2'},
            None,
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx', 'httpx2'), '0.65b0'),
        ),
        ({'httpx'}, '0.64b0', None),
        (
            {'httpx2'},
            '0.64b0',
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0', already_installed=True),
        ),
        (
            {'httpx', 'httpx2'},
            '0.64b0',
            InstrumentationRecommendation(HTTPX_OTEL_PACKAGE, ('httpx2',), '0.65b0', already_installed=True),
        ),
        ({'httpx2'}, '0.65b0', None),
        ({'httpx', 'httpx2'}, '0.65b0', None),
    ],
)
def test_httpx_recommendations(
    installed_clients: set[str],
    otel_version: str | None,
    expected: InstrumentationRecommendation | None,
) -> None:
    installed_otel: set[str] = {HTTPX_OTEL_PACKAGE} if otel_version else set()
    installed_versions = {HTTPX_OTEL_PACKAGE: otel_version} if otel_version else {}

    recommendations = find_recommended_instrumentations_to_install(
        {HTTPX_OTEL_PACKAGE: 'httpx'},
        installed_otel,
        installed_clients,
        installed_versions,
    )

    assert recommendations == ({expected} if expected else set())


@pytest.mark.parametrize('excluded_client', ['httpx', 'httpx2'])
def test_httpx_exclude_aliases(excluded_client: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logfire._internal.cli.run, 'installed_packages', lambda: {'httpx2'})

    context = collect_instrumentation_context({excluded_client})

    assert HTTPX_OTEL_PACKAGE not in context.instrument_pkg_map
    assert all(HTTPX_OTEL_PACKAGE != recommendation.package_name for recommendation in context.recommendations)


@pytest.mark.parametrize(
    ('installed_clients', 'expected'),
    [
        (
            {'psycopg'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg', ('psycopg',))},
        ),
        (
            {'psycopg2'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',))},
        ),
        (
            {'psycopg2-binary'},
            {InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',))},
        ),
        (
            {'psycopg', 'psycopg2-binary'},
            {
                InstrumentationRecommendation('opentelemetry-instrumentation-psycopg', ('psycopg',)),
                InstrumentationRecommendation('opentelemetry-instrumentation-psycopg2', ('psycopg2',)),
            },
        ),
    ],
)
def test_psycopg_recommendations(installed_clients: set[str], expected: set[InstrumentationRecommendation]) -> None:
    recommendations = find_recommended_instrumentations_to_install(
        PSYCOPG_OTEL_PACKAGES,
        set(),
        installed_clients,
    )

    assert recommendations == expected


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


def test_auth_non_interactive_completes_without_a_keypress(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`logfire --region us auth` works with no terminal attached.

    The device flow needs no keypress: the URL is printed and the poll simply waits, so a
    caller can surface the link and the login completes when the user opens it. The
    "Press Enter to open ... in your browser" prompt was the only thing in the way, and it
    turned every non-interactive invocation -- CI, containers, coding agents -- into an
    EOFError traceback.
    """
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        # No stdin: reading raises EOFError, exactly as it does under `< /dev/null`.
        stack.enter_context(patch('logfire._internal.cli.auth.input', side_effect=EOFError))
        webbrowser_open = stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/device-auth/wait/DC',
            text='{"token": "fake_token", "expiration": "fake_exp"}',
        )

        main(['--region', 'us', 'auth'])

    # It may try to read -- that is fine and is how it detects there is nothing there.
    # What must not happen is a crash, or a browser opened for an audience of nobody.
    webbrowser_open.assert_not_called()
    assert 'fake_token' in auth_file.read_text()
    # With no browser to open, the printed URL is the ONLY way the caller can surface the
    # login to a person -- so it is the feature here, not incidental output.
    assert 'http://example.com/auth' in capsys.readouterr().err


def test_auth_non_interactive_without_a_region_says_what_to_do(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Which region holds your data is not ours to guess, so it stays a required choice.

    It is answerable ahead of time with `--region`, and saying so beats raising EOFError
    from a prompt the caller cannot reply to.
    """
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.input', side_effect=EOFError))

        # A clean exit, not an exception: anything escaping `main()` reaches the user as
        # a traceback.
        with pytest.raises(SystemExit) as exc_info:
            main(['auth'])
        assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert 'no region was selected' in err
    # Each suggestion must be runnable as printed. `--region us|eu` is a shell pipeline.
    assert '  logfire --region us auth' in err
    assert '  logfire --region eu auth' in err
    assert 'us|eu' not in err


def test_auth_reads_piped_answers_even_though_a_pipe_is_not_a_tty(tmp_path: Path) -> None:
    """`printf '1\\n\\n' | logfire auth` must keep working.

    Piping answers is how scripts have always driven this command. An earlier version of
    this fix gated the prompts on `sys.stdin.isatty()`, which is a different question --
    a pipe is not a tty -- and so refused input that was sitting right there, turning a
    working setup script into a hard error. Found by running the real CLI in a container
    with its stdin on a pipe.
    """
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        # '1' selects the first region; '' is the Enter keypress before the browser opens.
        stack.enter_context(patch('logfire._internal.cli.auth.input', side_effect=['1', '']))
        stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/device-auth/wait/DC',
            text='{"token": "fake_token", "expiration": "fake_exp"}',
        )

        main(['auth'])

    assert 'fake_token' in auth_file.read_text()


def test_read_line_returns_none_when_stdin_is_unavailable() -> None:
    """Every way stdin can be missing means the same thing: no answer is available.

    `input()` raises RuntimeError when `sys.stdin` is None (pythonw, some embedded
    runtimes) and ValueError on a closed stream. The docstring claimed these were handled
    before they actually were.
    """
    from logfire._internal.cli.auth import _read_line  # pyright: ignore[reportPrivateUsage]

    for exc in (EOFError, RuntimeError, ValueError, AttributeError):
        with patch('logfire._internal.cli.auth.input', side_effect=exc):
            assert _read_line('prompt') is None, exc

    # And the real thing, not a mock of it: `sys.stdin = None` is exactly what pythonw and
    # some embedded runtimes leave behind, and it is what makes `input()` raise
    # RuntimeError rather than any of the others.
    original = sys.stdin
    try:
        sys.stdin = None
        assert _read_line('prompt') is None
    finally:
        sys.stdin = original


def test_non_interactive_refuses_the_region_without_reading_stdin(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--non-interactive` fails BEFORE reading, which is the whole point.

    Handling EOF only helps when a read returns. Stdin can be open and silent -- a CI
    runner or a supervisor holding an idle pipe -- and then `input()` waits forever with
    no output at all. Declaring intent up front is the only thing that catches that, so
    this asserts nothing is read rather than asserting on the error alone.
    """
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        mock_input = stack.enter_context(patch('logfire._internal.cli.auth.input'))

        with pytest.raises(SystemExit) as exc_info:
            main(['--non-interactive', 'auth'])
        assert exc_info.value.code == 1

    mock_input.assert_not_called()
    err = capsys.readouterr().err
    assert 'no region was selected' in err
    assert '--non-interactive' in err
    # Each suggestion must be runnable as printed.
    assert '  logfire --region us auth' in err
    assert '  logfire --region eu auth' in err


def test_non_interactive_with_a_region_never_reads_stdin(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The path the flag exists for, and the one my own tests missed.

    With `--region` supplied the region prompt is skipped, so "Press Enter to open ... in
    your browser" is the next stop. It read unconditionally, so an open, silent stdin hung
    there -- the exact failure this flag is meant to prevent, in the command it is most
    likely to be used with. Asserting `input` is never called is the only assertion that
    catches it; an EOF-based test passes either way.
    """
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.auth.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.auth.DEFAULT_FILE', auth_file))
        # Not EOFError: a stdin that BLOCKS forever cannot be simulated, so instead this
        # fails loudly if anything reads at all.
        mock_input = stack.enter_context(
            patch('logfire._internal.cli.auth.input', side_effect=AssertionError('read stdin'))
        )
        webbrowser_open = stack.enter_context(patch('logfire._internal.cli.auth.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-us.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-us.pydantic.dev/v1/device-auth/wait/DC',
            text='{"token": "fake_token", "expiration": "fake_exp"}',
        )

        main(['--non-interactive', '--region', 'us', 'auth'])

    mock_input.assert_not_called()
    webbrowser_open.assert_not_called()
    assert 'fake_token' in auth_file.read_text()
    # The URL is still printed: with no browser opened it is the only way to surface the
    # login to a person.
    assert 'http://example.com/auth' in capsys.readouterr().err


def test_non_interactive_clean_refuses_instead_of_deleting(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`logfire clean` must not guess an answer either way.

    Assuming its default (N) would do nothing while reporting success; assuming Y would
    delete credentials nobody confirmed. So it refuses, and `--yes` is how a caller says
    yes ahead of time.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    (data_dir / 'logfire_credentials.json').write_text('{}')

    with patch('logfire._internal.cli.input', side_effect=AssertionError('read stdin')):
        with pytest.raises(SystemExit) as exc_info:
            main(['--non-interactive', 'clean'])
    assert exc_info.value.code == 1

    err = capsys.readouterr().err
    assert 'logfire clean --yes' in err
    # Refused means refused: the file is still there.
    assert (data_dir / 'logfire_credentials.json').exists()


def test_clean_yes_deletes_without_prompting(tmp_dir_cwd: Path) -> None:
    """`--yes` is the way through, and it must not read stdin to get there."""
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    (data_dir / 'logfire_credentials.json').write_text('{}')

    with patch('logfire._internal.cli.input', side_effect=AssertionError('read stdin')):
        main(['--non-interactive', 'clean', '--yes'])

    assert not (data_dir / 'logfire_credentials.json').exists()


def test_non_interactive_switch_is_restored_after_main_returns() -> None:
    """`main()` is importable, so the switch must not outlive the call.

    An application that shells through `logfire.cli.main([...])` would otherwise lose
    prompting everywhere afterwards -- including in `logfire.configure()`, which this flag
    does not govern at all.
    """
    from logfire._internal.interactive import is_non_interactive

    assert is_non_interactive() is False
    main(['--non-interactive', '--version'])
    assert is_non_interactive() is False, 'the switch outlived the CLI invocation'


def test_non_interactive_gateway_refuses_instead_of_prompting() -> None:
    """The gateway refusal, which 100% line coverage did not prove was exercised.

    `require_answer(...)` is one statement, so it counts as covered the moment the
    surrounding code runs with the flag OFF -- the refusal it performs lives inside the
    helper. Coverage cannot tell those apart; only driving it with the flag on can.
    """
    from logfire._internal.cli.gateway import _interactive_integration  # pyright: ignore[reportPrivateUsage]
    from logfire._internal.interactive import NonInteractiveError, set_non_interactive

    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.cli.gateway.ai_tool_names', return_value=['claude', 'codex']))
        stack.enter_context(
            patch('logfire._internal.cli.gateway.resolve_ai_tool', return_value=Mock(binary_path=lambda: '/x'))
        )
        prompt = stack.enter_context(patch('logfire._internal.cli.gateway.Prompt.ask'))

        set_non_interactive(True)
        try:
            with pytest.raises(NonInteractiveError) as exc_info:
                _interactive_integration()
        finally:
            set_non_interactive(False)

    prompt.assert_not_called()
    message = str(exc_info.value)
    assert 'Installed: claude, codex' in message
    assert 'logfire gateway claude' in message
    assert 'logfire gateway codex' in message


def test_non_interactive_gateway_message_matches_how_many_are_installed() -> None:
    """With one integration the prompt is still reached -- it has a default -- so the
    refusal must not claim several are available."""
    from logfire._internal.cli.gateway import _interactive_integration  # pyright: ignore[reportPrivateUsage]
    from logfire._internal.interactive import NonInteractiveError, set_non_interactive

    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.cli.gateway.ai_tool_names', return_value=['claude']))
        stack.enter_context(
            patch('logfire._internal.cli.gateway.resolve_ai_tool', return_value=Mock(binary_path=lambda: '/x'))
        )
        set_non_interactive(True)
        try:
            with pytest.raises(NonInteractiveError) as exc_info:
                _interactive_integration()
        finally:
            set_non_interactive(False)

    assert 'claude is installed.' in str(exc_info.value)


def test_non_interactive_remedies_are_pasteable() -> None:
    """Every suggestion must survive being pasted into a shell.

    `<name>` is input redirection and `a|b` is a pipeline, so guidance containing them
    fails or silently does something else. Both mistakes have already been made once in
    this PR, which is why this asserts on the whole message rather than one command.
    """
    from logfire._internal.interactive import NonInteractiveError, require_answer, set_non_interactive

    set_non_interactive(True)
    try:
        with pytest.raises(NonInteractiveError) as exc_info:
            require_answer('question', 'logfire projects new PROJECT_NAME --org ORGANIZATION')
    finally:
        set_non_interactive(False)

    for suggestion in str(exc_info.value).splitlines():
        if not suggestion.startswith('  logfire'):
            continue
        assert not set(suggestion) & set('<>|&;$`()'), f'not pasteable: {suggestion!r}'


def _status_credentials(tmp_dir_cwd: Path, *, read_token: bool = True) -> Path:
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                'project_url': 'https://logfire-us.pydantic.dev/test-org/orders',
                'logfire_api_url': 'https://logfire-us.pydantic.dev',
            }
        )
    )
    if read_token:
        _save_fake_read_token(data_dir)
    return data_dir


def _save_fake_read_token(
    data_dir: Path,
    *,
    token: str = 'fake_read_token',
    base_url: str = 'https://logfire-us.pydantic.dev',
    organization: str = 'test-org',
    project_name: str = 'orders',
    expires_at: str | None = None,
) -> Path:
    """The file `read-tokens create --save` writes, which `projects status` now reads."""
    path = data_dir / READ_TOKEN_FILENAME
    path.write_text(
        json.dumps(
            {
                'token': token,
                'base_url': base_url,
                'organization': organization,
                'project_name': project_name,
                'expires_at': expires_at or (datetime.now(tz=timezone.utc) + timedelta(days=30)).isoformat(),
            }
        )
    )
    return path


def _mock_status_backend(m: requests_mock.Mocker, rows: list[dict[str, Any]]) -> None:
    """The only call `projects status` makes: the query itself.

    It deliberately does NOT mock the read-tokens endpoint. `projects status` must use the
    saved token rather than creating one, and a mock here would hide a regression back to
    minting per invocation -- requests_mock raises `NoMockAddress` for the unregistered
    POST, so that regression fails loudly instead of passing.

    The response is the WIRE shape -- `{"schema": {...}, "data": [...]}` -- not the
    columns/rows shape the query client maps it to. Returning the mapped shape would make
    the test pass against a body the server never sends.
    """
    m.post(
        'https://logfire-us.pydantic.dev/v2/query',
        json={
            # Mirrors the real body, verified against staging: fields carry `nullable`
            # and the schema carries `metadata`, even though this command reads neither.
            'schema': {
                'fields': [{'name': k, 'data_type': 'Utf8', 'nullable': False} for k in (rows[0] if rows else {})],
                'metadata': {},
            },
            'data': rows,
        },
    )


def test_projects_status_reports_what_arrived(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """One row per service, so a partly-instrumented system is visible as such.

    This is the case the command exists for: an agent that instrumented the web app and
    forgot the worker sees `orders-worker` missing, which no amount of "no errors in the
    log" would have told it.
    """
    _status_credentials(tmp_dir_cwd)
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
        _mock_status_backend(
            m,
            [
                {'service_name': 'orders-web', 'records': 12, 'last_seen': '2026-08-18T20:00:00Z'},
                {'service_name': 'orders-worker', 'records': 3, 'last_seen': '2026-08-18T20:00:05Z'},
            ],
        )

        main(['projects', 'status'])

    query = next(r for r in m.request_history if r.path.endswith('/v2/query'))
    body = query.json()
    sql = body['sql']
    assert 'GROUP BY service_name' in sql, sql
    assert 'count(*)' in sql, sql
    # A time bound, so a long-lived project does not scan its whole history.
    assert body.get('min_timestamp'), body
    # And a ceiling, so this cannot become an enormous query on a busy project.
    assert body['limit'] == STATUS_MAX_ROWS, body

    err = capsys.readouterr().err
    assert 'test-org/orders' in err
    assert 'orders-web' in err
    assert 'orders-worker' in err
    assert '12' in err
    # The read token is minted to run the query and must never be shown: putting a live
    # credential in the caller's output is the thing this command exists to avoid.
    assert 'fake_read_token' not in err


def test_projects_status_works_from_a_saved_read_token_alone(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No write credentials at all -- only a saved read token -- must still work.

    `read-tokens --project ORGANIZATION/PROJECT_NAME create --save` never touches
    `logfire_credentials.json`; a directory that only ever ran that command (never
    `projects use`) is a legitimate, real user-reported state, not an edge case. Before
    this, `projects status` insisted on write credentials it had no actual use for, and
    sent a read-only user looking for `projects use` instead of the read-tokens command
    that would have actually gotten them unstuck.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    _save_fake_read_token(data_dir, organization='alexmojaki', project_name='test38')

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
        _mock_status_backend(m, [{'service_name': 'orders-web', 'records': 5, 'last_seen': '2026-08-18T20:00:00Z'}])

        main(['projects', 'status'])

    err = capsys.readouterr().err
    assert 'alexmojaki/test38' in err
    assert 'orders-web' in err
    # The read token is minted to run the query and must never be shown: putting a live
    # credential in the caller's output is the thing this command exists to avoid.
    assert 'fake_read_token' not in err


def test_projects_status_says_nothing_yet_rather_than_failing(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No data during setup usually means "not yet", not "broken"."""
    _status_credentials(tmp_dir_cwd)
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
        _mock_status_backend(m, [])

        main(['projects', 'status'])

    err = capsys.readouterr().err
    assert 'No telemetry' in err
    assert 'Run the application' in err


def test_projects_status_json_is_machine_readable(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--json` on stdout, so an agent can branch on it without parsing a table."""
    _status_credentials(tmp_dir_cwd)
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
        _mock_status_backend(m, [{'service_name': 'orders-web', 'records': 12, 'last_seen': '2026-08-18T20:00:00Z'}])

        main(['projects', 'status', '--json'])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload['organization'] == 'test-org'
    assert payload['project_name'] == 'orders'
    assert payload['services'] == [{'service_name': 'orders-web', 'records': 12, 'last_seen': '2026-08-18T20:00:00Z'}]
    assert 'fake_read_token' not in captured.out
    assert 'fake_read_token' not in captured.err


def test_projects_status_without_credentials_says_what_to_run(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No write credentials and no saved read token: point at minting a read token
    directly, not at `projects use` -- this command never needs write credentials, so
    telling a read-only user to go get some would be pointing them at the wrong fix.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(['projects', 'status'])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert 'No usable read token' in err
    # Runnable as printed: `<name>` would be shell input redirection.
    assert 'logfire read-tokens --project ORGANIZATION/PROJECT_NAME create --save' in err
    assert 'logfire projects use PROJECT_NAME --org ORGANIZATION' in err


@pytest.mark.parametrize(
    ('project_url', 'expected'),
    [
        # The shape the CLI actually writes into the credentials file.
        ('https://logfire-us.pydantic.dev/test-org/orders', 'test-org'),
        ('https://logfire-eu.pydantic.dev/test-org/orders', 'test-org'),
        # Self-hosted, where the deployment lives under a path prefix.
        ('https://logfire.example.com/logfire/acme/orders', 'acme'),
        # A trailing slash must not shift the answer by one segment.
        ('https://logfire-us.pydantic.dev/test-org/orders/', 'test-org'),
        # Hyphens and digits are legal in both names.
        ('https://logfire-us.pydantic.dev/acme-2/orders-api', 'acme-2'),
        # Not enough path to name an organization.
        ('https://logfire-us.pydantic.dev/orders', None),
        ('https://logfire-us.pydantic.dev/', None),
        ('https://logfire-us.pydantic.dev', None),
        ('', None),
    ],
)
def test_organization_from_project_url(project_url: str, expected: str | None) -> None:
    """The organization is the second-to-last path segment, or nothing.

    Pure, so every shape is enumerable here rather than through a command with four
    mocked collaborators. The `None` cases matter: the credentials file is user-editable
    and `projects status` must say something useful rather than raise IndexError.
    """
    assert _organization_from_project_url(project_url) == expected


def test_projects_status_when_the_project_url_names_no_organization(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A credentials file that cannot name an organization exits cleanly.

    Reachable in practice: the file is plain JSON in the repo and people edit it. Before
    this it was the one uncovered branch in the command.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                'project_url': 'https://logfire-us.pydantic.dev/',
                'logfire_api_url': 'https://logfire-us.pydantic.dev',
            }
        )
    )

    with pytest.raises(SystemExit) as exc_info:
        main(['projects', 'status'])
    assert exc_info.value.code == 1
    assert 'Cannot tell which organization' in capsys.readouterr().err


def test_projects_status_reports_a_failed_query(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A rejected query says what the server said, rather than raising.

    Reachable whenever the read token is refused or the backend is unhappy, and the
    status code plus body is the only thing that tells someone which it was.
    """
    _status_credentials(tmp_dir_cwd)
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
        # No read-tokens mock: `_status_credentials`'s default `read_token=True` already
        # saves one, so `projects status` uses that and never mints -- registering a
        # read-tokens mock here would sit dead, and a regression back to minting per
        # invocation would pass this test instead of failing it.
        m.post(
            'https://logfire-us.pydantic.dev/v2/query',
            status_code=401,
            text='Invalid read token',
        )

        with pytest.raises(SystemExit) as exc_info:
            main(['projects', 'status'])

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert 'Could not read the project' in err
    assert '401' in err
    assert 'Invalid read token' in err


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
    assert capsys.readouterr().out.splitlines()[0] == 'usage: logfire projects [-h] {list,new,status,use} ...'


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


def test_projects_list_json(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """`--json` goes to STDOUT so it can be piped, and is sorted like the table."""
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
                {'organization_name': 'test-org', 'project_name': 'zulu'},
                {'organization_name': 'test-org', 'project_name': 'alpha'},
            ],
        )

        main(['projects', 'list', '--json'])

        captured = capsys.readouterr()
        assert json.loads(captured.out) == snapshot(
            [
                {'organization_name': 'test-org', 'project_name': 'alpha'},
                {'organization_name': 'test-org', 'project_name': 'zulu'},
            ]
        )
        # Nothing on stderr: a caller redirecting only stdout must get clean JSON, with no
        # banner or table interleaved.
        assert captured.err == ''


def test_projects_list_json_no_projects(default_credentials: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Empty is `[]`, not the prose message.

    A caller parsing this should not have to special-case "no projects" by matching
    English, and `logfire projects list` exits 0 either way, so the text was the only
    signal available.
    """
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

        main(['projects', 'list', '--json'])

        captured = capsys.readouterr()
        assert json.loads(captured.out) == []
        assert captured.err == ''


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

    # Without `--save` the token is printed and NOT given an expiry: it is being pasted
    # into something we do not control, and silently breaking that later is worse than
    # leaving it.
    assert 'expires_at' not in m.request_history[-1].json()


def _read_token_backend(m: requests_mock.Mocker, token: str = 'saved_read_token') -> None:
    m.post(
        'https://logfire-us.pydantic.dev/v1/organizations/test-org/projects/orders/read-tokens',
        json={'token': token},
    )


def test_projects_status_ignores_a_malicious_logfire_api_url(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The read token must go to the host it was minted against, never wherever the repo
    file says.

    `logfire_credentials.json` lives inside the project this command runs in, so a
    malicious or tampered repository can set `logfire_api_url` to anything. If that value
    controlled where the read token is sent, checking out an untrusted repo and running
    `projects status` in it would hand the token straight to an attacker.

    The query host comes from the SAVED token file's own `base_url` instead, recorded when
    the token was created from a trusted source (CLI flags or `~/.logfire/default.toml`,
    never from anything inside the project) -- see `_save_read_token`. An earlier version
    derived the host from the token's own region prefix, which also closed this hole but
    broke self-hosted deployments; see `test_projects_status_uses_a_self_hosted_read_token`.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                'project_url': 'https://logfire-us.pydantic.dev/test-org/orders',
                # The attack: a tampered repo pointing this at a server it controls.
                'logfire_api_url': 'https://attacker.example.com',
            }
        )
    )
    # Saved with the REAL host, as it would be by a legitimate `--save` run -- proving the
    # query follows this recorded value rather than the credentials file.
    _save_fake_read_token(data_dir)

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
        # Only the REAL host is registered. If the code used `logfire_api_url` instead,
        # the POST would target `attacker.example.com` and requests_mock would raise
        # `NoMockAddress` -- so this test fails loudly rather than passing if the
        # vulnerability comes back.
        _mock_status_backend(m, [{'service_name': 'orders-web', 'records': 1, 'last_seen': '2026-08-18T20:00:00Z'}])

        main(['projects', 'status'])

    query = next(r for r in m.request_history if r.path.endswith('/v2/query'))
    assert query.hostname == 'logfire-us.pydantic.dev'
    assert 'attacker.example.com' not in {r.hostname for r in m.request_history}
    assert 'orders-web' in capsys.readouterr().err


def test_projects_status_uses_a_self_hosted_read_token(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A self-hosted deployment's read token must go to the self-hosted host.

    Self-hosted instances (`logfire --base-url=https://logfire.example.com auth`) use an
    arbitrary URL that cannot be recovered from a token's shape -- an earlier version of
    the exfiltration fix derived the query host from the token's own region prefix, which
    would have silently sent a self-hosted token to the hosted US service instead: the
    right server for nobody, and a leak to a real host, not just a broken command.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                'project_url': 'https://logfire.example.com/test-org/orders',
                'logfire_api_url': 'https://logfire.example.com',
            }
        )
    )
    _save_fake_read_token(data_dir, base_url='https://logfire.example.com')

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire.example.com', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire.example.com/v2/query',
            json={
                'schema': {'fields': [{'name': 'service_name', 'data_type': 'Utf8', 'nullable': False}]},
                'data': [{'service_name': 'orders-web', 'records': 1, 'last_seen': '2026-08-18T20:00:00Z'}],
            },
        )

        main(['projects', 'status'])

    query = next(r for r in m.request_history if r.path.endswith('/v2/query'))
    assert query.hostname == 'logfire.example.com'
    assert 'orders-web' in capsys.readouterr().err


def test_projects_status_displays_the_host_it_actually_queried(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The displayed project URL must name the host the query actually went to.

    Matching organization and project name does not guarantee a matching host --
    `logfire_credentials.json` and a saved read token are two separate files, and nothing
    stops them naming different deployments for what happens to be the same org/project
    pair. The query always goes to `saved.base_url`; showing `credentials.project_url`
    instead would tell the user a host their request never touched.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                'project_url': 'https://logfire-us.pydantic.dev/test-org/orders',
                'logfire_api_url': 'https://logfire-us.pydantic.dev',
            }
        )
    )
    _save_fake_read_token(data_dir, base_url='https://logfire.example.com')

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
            'https://logfire.example.com/v2/query',
            json={
                'schema': {'fields': [{'name': 'service_name', 'data_type': 'Utf8', 'nullable': False}]},
                'data': [],
            },
        )

        main(['projects', 'status', '--json'])

    payload = json.loads(capsys.readouterr().out)
    assert payload['project_url'] == 'https://logfire.example.com/test-org/orders'


def test_read_token_save_writes_the_file_and_prints_nothing(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--save` exists so the credential never reaches a terminal or a transcript.

    The measured failure it fixes: agents told to verify their own work ran
    `read-tokens create`, which writes the token to stdout, and every one of them ended up
    with a live credential in the transcript that ships to a model provider.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
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
        _read_token_backend(m)

        # No `--project`: it should fall back to the linked project, which is the whole
        # point of the no-argument form.
        main(['read-tokens', 'create', '--save'])

    captured = capsys.readouterr()
    assert captured.out == '', 'the token must never reach stdout'
    assert 'saved_read_token' not in captured.err, 'nor stderr'
    assert 'test-org/orders' in captured.err

    saved = json.loads((data_dir / READ_TOKEN_FILENAME).read_text())
    assert saved['token'] == 'saved_read_token'
    assert saved['organization'] == 'test-org'
    assert saved['project_name'] == 'orders'
    # The host the CREATE request actually used, not read back from anywhere in the
    # project -- this is what lets `projects status` trust it later. See
    # test_projects_status_ignores_a_malicious_logfire_api_url.
    assert saved['base_url'] == 'https://logfire-us.pydantic.dev'

    # An expiry, because the CLI cannot revoke a token it has written to disk.
    requested = m.request_history[-1].json()
    assert requested['expires_at'], requested
    expiry = datetime.fromisoformat(saved['expires_at'])
    assert timedelta(days=READ_TOKEN_TTL.days - 1) < expiry - datetime.now(tz=timezone.utc) <= READ_TOKEN_TTL

    # Owner-only: this file holds a credential that can read the whole project.
    assert (data_dir / READ_TOKEN_FILENAME).stat().st_mode & 0o077 == 0


def test_read_token_save_with_explicit_project_needs_no_linked_directory(tmp_dir_cwd: Path) -> None:
    """`--project` bypasses the linked-directory fallback entirely.

    Every other `--save` test relies on `_status_credentials` linking the directory.
    `--project` is the OTHER way to reach `parse_create_read_token`'s org/project
    resolution -- no `logfire_credentials.json` needed at all -- and that branch was
    otherwise never exercised for the `--save` path, only for plain `create`.
    """
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
            'https://logfire-us.pydantic.dev/v1/organizations/other-org/projects/other-project/read-tokens',
            json={'token': 'explicit_project_token'},
        )

        main(['read-tokens', '--project', 'other-org/other-project', 'create', '--save'])

    saved = json.loads((tmp_dir_cwd / '.logfire' / READ_TOKEN_FILENAME).read_text())
    assert saved['organization'] == 'other-org'
    assert saved['project_name'] == 'other-project'
    assert saved['token'] == 'explicit_project_token'


def test_read_token_create_without_project_or_linked_directory_says_what_to_run(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No `--project` and nothing linked: the remedy must name both ways out.

    `parse_create_read_token` falls back to the linked directory when `--project` is
    omitted, sharing `_load_credentials_or_exit` with `whoami` and (formerly) `projects
    status` for that. `projects status` reads write credentials directly now, so this is
    the only remaining caller that passes `_load_credentials_or_exit` a `remedy` -- and
    without a test here, that branch would go uncovered.
    """
    with pytest.raises(SystemExit) as exc_info:
        main(['read-tokens', 'create'])
    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert 'No Logfire credentials found' in err
    assert '--project' in err
    assert 'logfire projects use PROJECT_NAME --org ORGANIZATION' in err


def test_read_token_create_without_save_writes_no_file(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Printed mode must not ALSO persist a copy to disk.

    `--save` is what makes a token durable; without it, nothing should be left behind for
    `projects status` to pick up later, since the caller asked for the token in hand, not
    stored.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
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
        _read_token_backend(m, token='printed_token')

        main(['read-tokens', 'create'])

    assert capsys.readouterr().out == 'printed_token\n'
    assert not (data_dir / READ_TOKEN_FILENAME).exists()


def test_read_token_save_rotates_a_previously_saved_token(tmp_dir_cwd: Path) -> None:
    """Running `--save` again must replace the old token, not merge with it.

    The realistic workflow is re-running this to get a fresh token before an old one
    expires; a loader that somehow preferred stale data over the new file would silently
    defeat that.

    The stale token is padded far longer than the fresh one on purpose: writing without
    truncating (no `O_TRUNC`) would leave the old file's tail bytes after the new, shorter
    JSON document, and a same-or-shorter stale value would not expose that -- this makes a
    dropped `O_TRUNC` produce genuinely invalid JSON instead of silently still parsing.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    _save_fake_read_token(data_dir, token='stale_token_' + 'x' * 200)

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
        _read_token_backend(m, token='fresh_token')

        main(['read-tokens', 'create', '--save'])

    saved = json.loads((data_dir / READ_TOKEN_FILENAME).read_text())
    assert saved['token'] == 'fresh_token'
    loaded = _load_saved_read_token(data_dir, organization='test-org', project_name='orders')
    assert loaded is not None and loaded.token == 'fresh_token'


def test_projects_status_json_output_escapes_control_characters(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` is safe for the same attacker-controlled service name, but for a different
    reason than the table is.

    The table needs `_printable` to strip control characters explicitly. `--json` does not
    call it -- `json.dumps` already escapes control characters inside a JSON string
    (`\\u001b`, not a literal ESC byte), so the raw value is safe by construction. This
    pins that: nobody should "fix" this by routing JSON output through `_printable` too
    (which would mangle legitimate unicode service names for no reason), and if the output
    ever moves off `json.dumps` the replacement needs the same guarantee.
    """
    _status_credentials(tmp_dir_cwd)
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
        _mock_status_backend(
            m, [{'service_name': 'evil\x1b[2K\rorders-web', 'records': 1, 'last_seen': '2026-08-18T20:00:00Z'}]
        )

        main(['projects', 'status', '--json'])

    out = capsys.readouterr().out
    assert '\x1b' not in out
    assert '\\u001b' in out
    payload = json.loads(out)
    assert payload['services'][0]['service_name'] == 'evil\x1b[2K\rorders-web'


def test_read_token_save_keeps_the_data_dir_gitignored(tmp_dir_cwd: Path) -> None:
    """The saved token must not be the thing that leaves a data directory untracked-but-visible.

    `ensure_data_dir_exists` only seeds `.gitignore` when the directory holds nothing but
    the files Logfire writes itself, so a filename missing from `DATA_DIR_FILENAMES`
    would silently stop that rule being restored -- for a directory that now contains a
    read token.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    (data_dir / '.gitignore').unlink(missing_ok=True)
    _save_fake_read_token(data_dir)

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
        _read_token_backend(m)
        main(['read-tokens', 'create', '--save'])

    assert (data_dir / '.gitignore').read_text() == '*'


def test_projects_status_without_a_saved_token_says_what_to_run(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No token: one message naming the command, and no silent minting.

    The command used to create a read token per invocation. Those are permanent and the
    CLI cannot revoke them, so a user polling "has my data arrived yet?" four times left
    four live credentials behind.
    """
    _status_credentials(tmp_dir_cwd, read_token=False)
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
        # Nothing registered at all: any request whatsoever fails the test.
        with pytest.raises(SystemExit) as exc_info:
            main(['projects', 'status'])

    assert exc_info.value.code == 1
    assert m.request_history == [], 'it must not call the API without a token'
    err = capsys.readouterr().err
    assert 'read-tokens create --save' in err


_REMOVE_KEY = object()
"""Marker for "delete this field", which a plain override dict cannot express."""


@pytest.mark.parametrize(
    'override,reason',
    [
        ({'organization': 'other-org'}, 'issued for a different organization'),
        ({'project_name': 'other-project'}, 'issued for a different project'),
        ({'organization': ''}, 'empty organization'),
        ({'organization': 123}, 'organization is not a string'),
        ({'organization': _REMOVE_KEY}, 'no organization key -- an older saved-token file'),
        ({'project_name': ''}, 'empty project_name'),
        ({'project_name': _REMOVE_KEY}, 'no project_name key -- an older saved-token file'),
        ({'expires_at': (datetime.now(tz=timezone.utc) - timedelta(days=1)).isoformat()}, 'already expired'),
        ({'expires_at': 'not a timestamp'}, 'unparseable expiry'),
        ({'token': ''}, 'empty token'),
        ({'token': 123}, 'token is not a string'),
        ({'token': _REMOVE_KEY}, 'no token key'),
        ({'base_url': ''}, 'empty base_url'),
        ({'base_url': _REMOVE_KEY}, 'no base_url key -- an older saved-token file'),
    ],
)
def test_saved_read_token_is_rejected_when_unusable(tmp_dir_cwd: Path, override: dict[str, Any], reason: str) -> None:
    """A saved token is only used for the project it was issued for, and only while valid.

    `logfire projects use` repoints a directory; a token left from the previous project
    would otherwise be sent for the new one and produce a baffling 401 -- or, if the two
    happened to be in the same org, somebody else's data.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    path = _save_fake_read_token(data_dir)
    data: dict[str, Any] = json.loads(path.read_text())
    for key, value in override.items():
        if value is _REMOVE_KEY:
            data.pop(key, None)
        else:
            data[key] = value
    path.write_text(json.dumps(data))

    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None, reason


def test_load_saved_read_token_refuses_a_symlink(tmp_dir_cwd: Path) -> None:
    """A symlinked `read_token.json` must not be trusted, even with valid-looking content.

    `_save_read_token` refuses to write through a symlink, but that only protects writes
    THIS command makes -- a symlink planted some other way (committed to the repo, dropped
    in by another tool) never goes through that check. Following it here would hand
    whatever `base_url` and `token` the symlink target holds straight into the next
    request's URL and `Authorization` header: an attacker who can plant the symlink chooses
    where this command sends that token.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    victim = tmp_dir_cwd / 'victim.json'
    victim.write_text(
        json.dumps(
            {
                'token': 'read-token',
                'base_url': 'http://169.254.169.254',
                'organization': 'test-org',
                'project_name': 'orders',
            }
        )
    )
    (data_dir / READ_TOKEN_FILENAME).symlink_to(victim)

    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None


def test_load_saved_read_token_refuses_a_git_tracked_file(tmp_dir_cwd: Path) -> None:
    """A `read_token.json` already in the git index must not be trusted either.

    `.gitignore` only stops an untracked file from being added -- it does nothing for one
    already in the index, so an attacker with commit access (or a malicious PR) can ship a
    tracked `read_token.json` naming their own `base_url`. `_save_read_token` refuses to
    write through a tracked path, but a file that arrived via a commit was never written by
    this command at all, so that check never ran against it.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    path = _save_fake_read_token(data_dir, base_url='http://169.254.169.254')
    subprocess.run(['git', 'init', '--quiet'], cwd=tmp_dir_cwd, check=True)
    subprocess.run(['git', 'add', '--force', str(path)], cwd=tmp_dir_cwd, check=True)

    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None


def test_load_saved_read_token_treats_unconfirmed_tracking_as_unusable(tmp_dir_cwd: Path) -> None:
    """An ambiguous git-tracking check must fail this call closed too, but by returning
    "no usable token" rather than raising -- unlike `_save_read_token`, where the safe
    outcome is to BLOCK. Here the safe outcome is to fall back to the same "no token saved"
    path an absent file already takes, which the caller turns into one clean message
    naming `read-tokens create --save`, not a crash.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    _save_fake_read_token(data_dir)

    with patch(
        'logfire._internal.cli._is_git_tracked',
        side_effect=LogfireConfigError('could not confirm'),
    ):
        assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None


@pytest.mark.parametrize('kwargs', [{'organization': 'test-org'}, {'project_name': 'orders'}])
def test_load_saved_read_token_rejects_exactly_one_filter(tmp_dir_cwd: Path, kwargs: dict[str, str]) -> None:
    """Passing only one of `organization`/`project_name` must not check the token against
    half a project identity.

    A token whose organization matches but whose project does not (or vice versa) would
    otherwise pass -- matching a same-named project in a different organization, or a
    different project in the same organization -- neither of which is "the linked
    project". Both together (a real match check) or neither (trust the token's own
    identity) are the only valid calls; one alone is a caller bug, not a valid filter.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    _save_fake_read_token(data_dir, organization='test-org', project_name='orders')

    assert _load_saved_read_token(data_dir, **kwargs) is None


def test_saved_read_token_survives_a_naive_expiry(tmp_dir_cwd: Path) -> None:
    """A timestamp without a timezone must not blow up the comparison.

    This file is always written with an aware timestamp, but it is a plain JSON file a
    user can edit, and `datetime` raises rather than coerces when comparing naive to
    aware.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    _save_fake_read_token(
        data_dir, expires_at=(datetime.now(tz=timezone.utc) + timedelta(days=1)).replace(tzinfo=None).isoformat()
    )
    loaded = _load_saved_read_token(data_dir, organization='test-org', project_name='orders')
    assert loaded is not None and loaded.token == 'fake_read_token'


def test_read_token_save_refuses_to_follow_a_symlink(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A symlink at the destination must not be followed, and the refusal must be clean.

    The data directory lives inside the user's repository, so a symlink can arrive by
    being committed to it. Following one would apply `O_TRUNC` and an ownership-only mode
    change to whatever it points at -- destroying that file and handing the write to
    somewhere the user did not choose. The refusal itself must not ALSO be a raw
    traceback: `_save_read_token` raises `LogfireConfigError` for this, and an earlier
    version of `parse_create_read_token` let that escape uncaught -- worse than most such
    bugs, because it happens AFTER a token has already been minted, leaving the caller
    unsure whether anything happened.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    victim = tmp_dir_cwd / 'victim.txt'
    victim.write_text('important')
    (data_dir / READ_TOKEN_FILENAME).symlink_to(victim)

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
        _read_token_backend(m)

        with pytest.raises(SystemExit) as exc_info:
            main(['read-tokens', 'create', '--save'])

    assert exc_info.value.code == 1
    assert victim.read_text() == 'important', 'the symlink target was written through'


def test_read_token_save_refuses_a_git_tracked_destination(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`.gitignore` does not protect an already-tracked file.

    A `read_token.json` committed before this feature existed -- or by mistake, since
    `.gitignore` only stops NEW files from being added -- would otherwise get a live,
    permanent credential written straight into it, and the next `git commit -am` would
    publish it. Refuse rather than write.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    path = data_dir / READ_TOKEN_FILENAME
    path.write_text('{}')
    subprocess.run(['git', 'init', '--quiet'], cwd=tmp_dir_cwd, check=True)
    subprocess.run(['git', 'add', '--force', str(path)], cwd=tmp_dir_cwd, check=True)

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
        _read_token_backend(m)

        with pytest.raises(SystemExit) as exc_info:
            main(['read-tokens', 'create', '--save'])

    assert exc_info.value.code == 1
    assert 'already tracked by git' in capsys.readouterr().err
    assert path.read_text() == '{}', 'the tracked file was written through'


def test_is_git_tracked_treats_no_git_binary_and_no_repo_as_untracked(tmp_dir_cwd: Path) -> None:
    """No `git` binary, and no `.git` anywhere in the path's ancestry either.

    The threat this check guards against -- a path already in git's index -- is
    categorically impossible without a repository, so a machine with neither must still be
    able to save a read token rather than being blocked over an unrelated environment gap.
    """
    with patch('logfire._internal.cli.shutil.which', return_value=None):
        assert _is_git_tracked(tmp_dir_cwd / READ_TOKEN_FILENAME) is False


def test_is_git_tracked_fails_closed_when_git_binary_is_missing_but_a_repo_exists(tmp_dir_cwd: Path) -> None:
    """No `git` binary is not proof that no repository exists.

    A repository's index is just files on disk, and can already track this path on a
    machine where `git` itself is missing or off `PATH` for this one call -- exactly the
    condition `shutil.which` alone cannot distinguish from "no repository at all". Once a
    `.git` is visibly present, that gap must fail closed, not silently permit the write.
    """
    (tmp_dir_cwd / '.git').mkdir()
    with (
        patch('logfire._internal.cli.shutil.which', return_value=None),
        pytest.raises(LogfireConfigError, match='Could not confirm whether'),
    ):
        _is_git_tracked(tmp_dir_cwd / READ_TOKEN_FILENAME)


def test_has_git_dir_fails_closed_on_a_real_permission_error(tmp_dir_cwd: Path) -> None:
    """`Path.exists()` swallows a permission-denied ancestor and reports "not found" --
    confirmed empirically against this Python's actual behavior, not merely assumed from
    its docs. `_has_git_dir` must not inherit that through a plain `.exists()` call: an
    inaccessible ancestor reading as "no repository" is exactly the state most likely on a
    machine that has been tampered with, not evidence that no repository is there.
    """
    locked = tmp_dir_cwd / 'locked'
    locked.mkdir()
    inner = locked / 'inner'
    inner.mkdir()
    os.chmod(locked, 0o000)
    try:
        # Running as root, or with CAP_DAC_OVERRIDE, bypasses permission bits entirely --
        # confirming the lock actually took effect before relying on it, rather than
        # asserting straight into `_has_git_dir`, is what keeps this a real test of the
        # fix instead of a false failure wherever it does not.
        try:
            inner.stat()
        except PermissionError:
            pass
        else:
            pytest.skip('permission bits are not enforced in this environment (root or CAP_DAC_OVERRIDE)')
        with pytest.raises(PermissionError):
            _has_git_dir(inner)
    finally:
        os.chmod(locked, 0o755)


def test_is_git_tracked_fails_closed_when_the_repository_walk_itself_fails(tmp_dir_cwd: Path) -> None:
    """A filesystem error while looking for `.git` must not escape as a raw traceback.

    Walking up for a repository can hit a permission-denied intermediate directory or a
    symlink loop `.resolve()` cannot settle -- `OSError`, not a clean "no repository here".
    Letting that propagate unchanged would break the one contract every other failure mode
    in this function honors: a clean `LogfireConfigError`, not a bare traceback, and it
    would do so on exactly the kind of filesystem state most likely to be the OS itself
    refusing to answer, not proof of anything about the file's tracked status.
    """
    with (
        patch('logfire._internal.cli.shutil.which', return_value=None),
        patch('logfire._internal.cli._has_git_dir', side_effect=PermissionError('denied')),
        pytest.raises(LogfireConfigError, match='Could not confirm whether'),
    ):
        _is_git_tracked(tmp_dir_cwd / READ_TOKEN_FILENAME)


def test_is_git_tracked_fails_closed_when_git_exists_but_cannot_answer(tmp_dir_cwd: Path) -> None:
    """git present but unable to answer must NOT be treated the same as "untracked".

    Silently proceeding here would defeat the whole check on exactly the machine states an
    attacker aiming at this file is best positioned to engineer -- the check itself timing
    out, or some other OS-level failure -- so this raises and blocks the write instead of
    guessing safe.
    """
    with (
        patch('logfire._internal.cli.shutil.which', return_value='/usr/bin/git'),
        patch('logfire._internal.cli.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd='git', timeout=5)),
        pytest.raises(LogfireConfigError, match='Could not confirm whether'),
    ):
        _is_git_tracked(tmp_dir_cwd / READ_TOKEN_FILENAME)


def test_read_token_save_narrows_an_existing_permissive_file(tmp_dir_cwd: Path) -> None:
    """An existing world-readable file must be restricted BEFORE the token is written.

    The mode passed to `os.open` applies only when it creates the file, so without an
    explicit `fchmod` the token would be written into a file others can read and only
    locked down afterwards.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    path = data_dir / READ_TOKEN_FILENAME
    path.write_text('{}')
    path.chmod(0o644)

    observed: list[int] = []
    real_fdopen = os.fdopen

    def spy(fd: int, *args: Any, **kwargs: Any) -> IO[Any]:
        # The mode at the moment the file becomes writable, which is what matters.
        observed.append(os.fstat(fd).st_mode & 0o777)
        return cast('IO[Any]', real_fdopen(fd, *args, **kwargs))

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                'logfire._internal.auth.UserTokenCollection.get_token',
                return_value=UserToken(
                    token='', base_url='https://logfire-us.pydantic.dev', expiration='2099-12-31T23:59:59'
                ),
            )
        )
        stack.enter_context(patch('logfire._internal.cli.os.fdopen', spy))
        m = requests_mock.Mocker()
        stack.enter_context(m)
        _read_token_backend(m)
        main(['read-tokens', 'create', '--save'])

    assert observed == [0o600], 'the token was written while the file was still permissive'
    assert path.stat().st_mode & 0o077 == 0


def test_projects_status_rejects_a_non_200_response(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """204 is not an error by `response.ok`, but it has no body to parse.

    Without an exact status check this failed with a JSON decode error instead of the
    command's own message.
    """
    _status_credentials(tmp_dir_cwd)
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
        m.post('https://logfire-us.pydantic.dev/v2/query', status_code=204, text='')

        with pytest.raises(SystemExit) as exc_info:
            main(['projects', 'status'])

    assert exc_info.value.code == 1
    assert 'Could not read the project: 204' in capsys.readouterr().err


def test_projects_status_reports_a_network_failure_cleanly(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A timeout, DNS failure, or refused connection must not print a raw traceback.

    `requests.post` raises `RequestException` for these rather than returning a response,
    so the non-200 branch alone does not catch them.
    """
    _status_credentials(tmp_dir_cwd)
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
        m.post('https://logfire-us.pydantic.dev/v2/query', exc=requests.exceptions.ConnectTimeout)

        with pytest.raises(SystemExit) as exc_info:
            main(['projects', 'status'])

    assert exc_info.value.code == 1
    assert 'Could not reach https://logfire-us.pydantic.dev' in capsys.readouterr().err


@pytest.mark.parametrize(
    'body,reason',
    [
        ('not json at all', 'not JSON -- a proxy or WAF page instead of the real backend'),
        ('{"no_data_key": []}', 'JSON but missing "data"'),
        ('{"data": "not a list"}', '"data" is a string, not a list'),
        ('{"data": ["not", "objects"]}', '"data" is a list of strings, not row objects'),
    ],
)
def test_projects_status_rejects_a_malformed_200_response(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str], body: str, reason: str
) -> None:
    """A 200 whose body does not look like the query response must not crash.

    A 200 status does not guarantee the real backend produced the body -- a proxy or WAF
    can intercept the request and answer with its own page. Without this, a malformed body
    fails several lines further down with a raw `JSONDecodeError`, `KeyError`, or
    `AttributeError` instead of this command's own message.
    """
    _status_credentials(tmp_dir_cwd)
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
        m.post('https://logfire-us.pydantic.dev/v2/query', status_code=200, text=body)

        with pytest.raises(SystemExit) as exc_info:
            main(['projects', 'status'])

    assert exc_info.value.code == 1, reason
    assert 'Could not read the project: unexpected response shape' in capsys.readouterr().err, reason


def test_projects_status_strips_control_characters_from_service_names(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A service name is submitted telemetry, so it is attacker-controlled text.

    Written raw to a terminal it could clear the screen or forge rows in the very table
    someone is reading to decide whether their setup worked.
    """
    _status_credentials(tmp_dir_cwd)
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
        _mock_status_backend(
            m,
            [{'service_name': 'evil\x1b[2K\rorders-web', 'records': 1, 'last_seen': '2026-08-18T20:00:00Z'}],
        )
        main(['projects', 'status'])

    err = capsys.readouterr().err
    assert '\x1b' not in err, 'an ANSI escape reached the terminal'
    assert '\r' not in err


def test_projects_status_strips_control_characters_from_the_header(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`organization`/`project_name`/`project_url` come from `logfire_credentials.json`,
    a file inside the project this command runs in -- the same threat model
    `_save_read_token`'s docstring covers for the read token itself. Written raw to the
    `Project  <org>/<name>` header they are just as attacker-controlled as a service name.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir()
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'evil\x1b[2Korders',
                'project_url': 'https://logfire-us.pydantic.dev/evil\x1b[2Korg/evil\x1b[2Korders',
                'logfire_api_url': 'https://logfire-us.pydantic.dev',
            }
        )
    )
    # Matches what `_organization_from_project_url` derives from the malicious
    # `project_url` above -- the saved token is scoped to org/project, and a mismatch
    # would fail with "no usable read token" before the header is ever printed.
    _save_fake_read_token(data_dir, organization='evil\x1b[2Korg', project_name='evil\x1b[2Korders')

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
        _mock_status_backend(m, [])
        main(['projects', 'status'])

    assert '\x1b' not in capsys.readouterr().err, 'an ANSI escape reached the terminal'


def test_saved_read_token_without_an_expiry_is_still_usable(tmp_dir_cwd: Path) -> None:
    """No `expires_at` means unbounded, not invalid.

    This CLI always writes one, so a file without it was written by a different version
    or edited by hand. Refusing it would break a working setup over a field we added;
    the expiry exists to bound a leak, not to gate the happy path.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    path = _save_fake_read_token(data_dir)
    data: dict[str, Any] = json.loads(path.read_text())
    del data['expires_at']
    path.write_text(json.dumps(data))

    loaded = _load_saved_read_token(data_dir, organization='test-org', project_name='orders')
    assert loaded is not None and loaded.token == 'fake_read_token'


def test_read_token_save_when_the_project_url_names_no_organization(
    tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--save` needs an organization, and the credentials file does not store one.

    It is recovered from the project URL, so a URL that does not carry one has to fail
    with something better than an `IndexError`.
    """
    data_dir = tmp_dir_cwd / '.logfire'
    data_dir.mkdir(exist_ok=True)
    (data_dir / 'logfire_credentials.json').write_text(
        json.dumps(
            {
                'token': 'fake_write_token',
                'project_name': 'orders',
                # One path segment, so there is no organization to take.
                'project_url': 'https://logfire-us.pydantic.dev/orders',
                'logfire_api_url': 'https://logfire-us.pydantic.dev',
            }
        )
    )

    with pytest.raises(SystemExit) as exc_info:
        main(['read-tokens', 'create', '--save'])

    assert exc_info.value.code == 1
    assert 'Cannot tell which organization' in capsys.readouterr().err


def test_clean_removes_the_saved_read_token(tmp_dir_cwd: Path) -> None:
    """`logfire clean` must not leave a credential behind.

    It deletes the write credentials, so a data directory that still held a read token
    afterwards would be "cleaned" while retaining something that can read the whole
    project.
    """
    data_dir = _status_credentials(tmp_dir_cwd)
    assert (data_dir / READ_TOKEN_FILENAME).exists()

    main(['clean', '--yes'])

    assert not (data_dir / READ_TOKEN_FILENAME).exists()
    assert not (data_dir / 'logfire_credentials.json').exists()


def test_saved_read_token_survives_a_corrupt_file(tmp_dir_cwd: Path) -> None:
    """Unreadable is treated as absent, so the caller gives the one useful instruction."""
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    (data_dir / READ_TOKEN_FILENAME).write_text('{not json')
    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None

    (data_dir / READ_TOKEN_FILENAME).write_text('["a list"]')
    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None


def test_saved_read_token_rejects_a_non_string_expiry(tmp_dir_cwd: Path) -> None:
    """A PRESENT but wrongly-typed `expires_at` must not be treated as absent.

    Absence means unbounded -- this CLI always writes the key, so a missing one came from
    an older version or a hand-edited file, and the expiry exists to bound a leak rather
    than to gate the happy path. `null`/a number/etc. are different: this file always
    writes a string, so a non-string value did not come from a normal run, and treating it
    the same as absence (as `isinstance(expires_at, str)` alone does) lets a tampered file
    defeat the TTL entirely instead of merely losing it.
    """
    data_dir = _status_credentials(tmp_dir_cwd, read_token=False)
    (data_dir / READ_TOKEN_FILENAME).write_text(
        json.dumps(
            {
                'token': 'fake_read_token',
                'base_url': 'https://logfire-us.pydantic.dev',
                'organization': 'test-org',
                'project_name': 'orders',
                'expires_at': None,
            }
        )
    )
    assert _load_saved_read_token(data_dir, organization='test-org', project_name='orders') is None


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


def test_instrument_packages_with_only_httpx2(monkeypatch: pytest.MonkeyPatch) -> None:
    instrument_httpx = Mock()
    monkeypatch.setattr(logfire._internal.cli.run, 'logfire', types.SimpleNamespace(instrument_httpx=instrument_httpx))
    monkeypatch.setattr(
        logfire._internal.cli.run,
        'installed_packages',
        lambda: {HTTPX_OTEL_PACKAGE, 'httpx2'},
    )
    monkeypatch.setattr(
        logfire._internal.cli.run,
        '_installed_package_versions',
        Mock(return_value={HTTPX_OTEL_PACKAGE: '0.65b0'}),
    )

    context = collect_instrumentation_context(())
    result = instrument_packages(context.installed_otel_pkgs, context.instrument_pkg_map)
    summary = instrumented_packages_text(
        context.installed_otel_pkgs,
        result,
        context.installed_pkgs,
        context.installed_versions,
    )

    assert result == ['httpx']
    instrument_httpx.assert_called_once_with()
    assert '✓ httpx2 (installed and instrumented)' in summary


def test_instrument_packages_targets_each_psycopg_family(monkeypatch: pytest.MonkeyPatch) -> None:
    instrument_psycopg = Mock()
    monkeypatch.setattr(
        logfire._internal.cli.run,
        'logfire',
        types.SimpleNamespace(instrument_psycopg=instrument_psycopg),
    )

    result = instrument_packages(set(PSYCOPG_OTEL_PACKAGES), PSYCOPG_OTEL_PACKAGES)

    assert result == ['psycopg', 'psycopg2']
    assert instrument_psycopg.call_args_list == [call('psycopg'), call('psycopg2')]


@pytest.mark.parametrize(
    ('installed_clients', 'otel_version', 'instrumented', 'expected_lines'),
    [
        ({'httpx'}, '0.64b0', ['httpx'], ['✓ httpx (installed and instrumented)']),
        ({'httpx2'}, '0.65b0', ['httpx'], ['✓ httpx2 (installed and instrumented)']),
        (
            {'httpx', 'httpx2'},
            '0.65b0',
            ['httpx'],
            ['✓ httpx (installed and instrumented)', '✓ httpx2 (installed and instrumented)'],
        ),
        ({'httpx2'}, '0.64b0', [], ['⚠️ httpx2 (installed but not automatically instrumented)']),
        (
            {'httpx', 'httpx2'},
            '0.64b0',
            ['httpx'],
            ['✓ httpx (installed and instrumented)', '⚠️ httpx2 (installed but not automatically instrumented)'],
        ),
    ],
)
def test_httpx_instrumented_packages_text(
    installed_clients: set[str],
    otel_version: str,
    instrumented: list[str],
    expected_lines: list[str],
) -> None:
    text = instrumented_packages_text(
        {HTTPX_OTEL_PACKAGE},
        instrumented,
        installed_clients,
        {HTTPX_OTEL_PACKAGE: otel_version},
    )

    assert [line for line in str(text).splitlines() if line] == ['Your instrumentation checklist:', *expected_lines]


def test_instrumented_packages_text_basic():
    installed_otel_pkgs = {'opentelemetry-instrumentation-foo', 'opentelemetry-instrumentation-bar'}
    instrumented_packages = ['foo']
    installed_pkgs = {'foo', 'bar'}
    text = instrumented_packages_text(installed_otel_pkgs.copy(), instrumented_packages, installed_pkgs)
    assert '✓ foo' in text
    assert '⚠️ bar' in text


def test_get_recommendation_texts(monkeypatch: pytest.MonkeyPatch):
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-foo', ('foo',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-bar', ('bar',)),
    }
    recommended, install = get_recommendation_texts(recs)
    assert 'uv add opentelemetry-instrumentation-bar opentelemetry-instrumentation-foo' in install
    assert 'need to install opentelemetry-instrumentation-bar' in recommended
    assert 'need to install opentelemetry-instrumentation-foo' in recommended

    monkeypatch.setattr(logfire._internal.cli.run, 'is_uv_installed', lambda: False)
    _, install = get_recommendation_texts(recs)
    assert 'pip install opentelemetry-instrumentation-bar opentelemetry-instrumentation-foo' in install


def test_get_recommendation_texts_httpx2_upgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    recs = {
        InstrumentationRecommendation(
            HTTPX_OTEL_PACKAGE,
            ('httpx2',),
            '0.65b0',
            already_installed=True,
        )
    }

    recommended, install = get_recommendation_texts(recs)

    assert 'httpx2 (need to upgrade opentelemetry-instrumentation-httpx>=0.65b0)' in recommended
    assert "uv add 'opentelemetry-instrumentation-httpx>=0.65b0'" in install

    monkeypatch.setattr(logfire._internal.cli.run, 'is_uv_installed', lambda: False)
    _, install = get_recommendation_texts(recs)
    assert "pip install -U 'logfire[httpx]' 'opentelemetry-instrumentation-httpx>=0.65b0'" in install


@pytest.mark.parametrize(
    ('targets', 'formatted_targets'),
    [
        (('foo', 'bar'), 'foo and bar'),
        (('foo', 'bar', 'baz'), 'foo, bar, and baz'),
    ],
)
def test_get_recommendation_texts_formats_multiple_targets(targets: tuple[str, ...], formatted_targets: str) -> None:
    recommended, _ = get_recommendation_texts(
        {InstrumentationRecommendation('opentelemetry-instrumentation-foo', targets)}
    )

    assert f'{formatted_targets} (need to install opentelemetry-instrumentation-foo)' in recommended


def test_get_recommendation_texts_marks_ambiguous_packages():
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-foo', ('foo',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-urllib', ('urllib',)),
    }
    recommended, _ = get_recommendation_texts(recs)

    assert '☐ foo (need to install opentelemetry-instrumentation-foo)' in recommended
    assert '☐ requests [*] (need to install opentelemetry-instrumentation-requests)' in recommended
    assert '☐ sqlite3 [*] (need to install opentelemetry-instrumentation-sqlite3)' in recommended
    assert '☐ urllib [*] (need to install opentelemetry-instrumentation-urllib)' in recommended
    assert (
        '[*] `requests`, `sqlite3`, and `urllib` may not actually be used by your app, '
        'in which case you can ignore these recommendations'
    ) in recommended


def test_get_recommendation_texts_formats_two_ambiguous_packages():
    recs = {
        InstrumentationRecommendation('opentelemetry-instrumentation-requests', ('requests',)),
        InstrumentationRecommendation('opentelemetry-instrumentation-sqlite3', ('sqlite3',)),
    }
    recommended, _ = get_recommendation_texts(recs)

    assert (
        '[*] `requests` and `sqlite3` may not actually be used by your app, '
        'in which case you can ignore these recommendations'
    ) in recommended


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
    real_import = __import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'httpx' or name.startswith('starlette') or name == 'uvicorn':
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr('builtins.__import__', fake_import)
    sys.modules.pop('logfire._internal.cli.gateway', None)

    with pytest.raises(ImportError, match=r'pip install "logfire\[gateway\]"'):
        importlib.import_module('logfire._internal.cli.gateway')

    sys.modules.pop('logfire._internal.cli.gateway', None)


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


def test_gateway_handle_proxy_rejects_unknown_route_and_unauthorized_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle_proxy = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_proxy'))

    class CapturedJSONResponse:
        def __init__(self, content: dict[str, Any], *, status_code: int) -> None:
            self.content = content
            self.status_code = status_code

    monkeypatch.setattr(gateway_cli, 'JSONResponse', CapturedJSONResponse)
    state = gateway_cli.ProxyState(
        auth=Mock(),
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


def test_gateway_handle_proxy_forwards_non_streaming_request(monkeypatch: pytest.MonkeyPatch) -> None:
    handle_proxy = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_proxy'))

    class CapturedResponse:
        def __init__(
            self, *, content: bytes, status_code: int, headers: dict[str, str], media_type: str | None
        ) -> None:
            self.content = content
            self.status_code = status_code
            self.headers = headers
            self.media_type = media_type

    monkeypatch.setattr(gateway_cli, 'Response', CapturedResponse)
    state = gateway_cli.ProxyState(
        auth=Mock(),
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


def test_gateway_oauth_callback_and_favicon_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    handle_oauth_callback = cast(
        Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_oauth_callback')
    )
    handle_favicon = cast(Callable[[Any], Coroutine[Any, Any, Any]], getattr(gateway_cli, '_handle_favicon'))

    class CapturedResponse:
        def __init__(self, content: str = '', *, status_code: int, media_type: str | None = None) -> None:
            self.content = content
            self.status_code = status_code
            self.media_type = media_type

    calls: list[dict[str, str | None]] = []

    def complete_browser_callback(
        *, error: str | None, error_description: str | None, code: str | None, state: str | None
    ) -> gateway_auth.OAuthCallbackResult:
        calls.append({'error': error, 'error_description': error_description, 'code': code, 'state': state})
        return gateway_auth.OAuthCallbackResult('Authorization failed', '<bad>', status_code=400)

    auth = Mock(spec=gateway_auth.GatewayAuth)
    auth.complete_browser_callback = complete_browser_callback
    monkeypatch.setattr(gateway_cli, 'Response', CapturedResponse)
    state = gateway_cli.ProxyState(
        auth=auth,
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

    assert calls == [{'error': 'access_denied', 'error_description': 'nope', 'code': 'code', 'state': 'state'}]
    assert response.status_code == 400
    assert response.media_type == 'text/html'
    assert '&lt;bad&gt;' in response.content
    assert favicon.status_code == 204


def test_gateway_build_app_registers_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    class CapturedApp:
        def __init__(self, *, routes: list[Any]) -> None:
            self.routes = routes
            self.state = types.SimpleNamespace()

    def route(path: str, endpoint: Any, *, methods: list[str]) -> tuple[str, Any, list[str]]:
        return path, endpoint, methods

    monkeypatch.setattr(gateway_cli, 'Starlette', CapturedApp)
    monkeypatch.setattr(gateway_cli, 'Route', route)
    state = gateway_cli.ProxyState(
        auth=Mock(),
        client=Mock(),
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    app = gateway_cli.build_app(state)

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

    with pytest.raises(gateway_auth.GatewayError, match='OAuth discovery failed'):
        asyncio.run(run(Response(500, {})))
    with pytest.raises(gateway_auth.GatewayError, match="missing field 'device_authorization_endpoint'"):
        asyncio.run(run(Response(200, {'authorization_endpoint': 'a', 'token_endpoint': 't'})))
    with pytest.raises(gateway_auth.GatewayError, match='Expected JSON object response, got list'):
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

    with pytest.raises(gateway_auth.GatewayError, match='authorization failed: access_denied'):
        asyncio.run(run(callback_error='access_denied'))
    with pytest.raises(gateway_auth.GatewayError, match='authorization completed without a code'):
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

    with pytest.raises(gateway_auth.GatewayError, match=r'Device authorization failed \(500\): response-text'):
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

    with pytest.raises(gateway_auth.GatewayError, match='Device flow failed'):
        asyncio.run(
            run_device_flow(
                ConfigurableDeviceClient(device_start_response(interval=0), [device_token_error('invalid_grant')])
            )
        )

    with pytest.raises(gateway_auth.GatewayError, match='Device flow timed out'):
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
        with pytest.raises(gateway_auth.GatewayError, match=r'token exchange failed \(500\): response-text'):
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

    with pytest.raises(gateway_auth.GatewayError, match=r'token refresh failed \(500\): response-text'):
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


def make_mock_request_client(responses: list[MockGatewayResponse], captured: list[dict[str, str]]) -> httpx.AsyncClient:
    client = Mock(spec=httpx.AsyncClient)

    async def request(_method: str, _url: str, *, headers: dict[str, str], content: bytes) -> MockGatewayResponse:
        assert content == b'{}'
        captured.append(headers)
        return responses.pop(0)

    client.request = request
    return client


class MockGatewayStreamResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.headers = {'content-type': 'text/event-stream'}
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True

    async def aiter_raw(self) -> AsyncIterator[bytes]:
        yield b'data: done\n\n'


def make_mock_stream_client(
    responses: list[MockGatewayStreamResponse], captured: list[dict[str, str]]
) -> httpx.AsyncClient:
    client = Mock(spec=httpx.AsyncClient)

    def build_request(_method: str, _url: str, *, headers: dict[str, str], content: bytes) -> dict[str, Any]:
        assert content == b'{"stream": true}'
        return {'headers': headers}

    async def send(request: dict[str, Any], *, stream: bool) -> MockGatewayStreamResponse:
        assert stream is True
        captured.append(cast(dict[str, str], request['headers']))
        return responses.pop(0)

    client.build_request = build_request
    client.send = send
    return client


def make_mock_gateway_auth(
    tokens: list[str], recoveries: list[bool], recovery_result: bool = True
) -> gateway_auth.GatewayAuth:
    auth = Mock(spec=gateway_auth.GatewayAuth)

    async def current_access_token() -> str:
        return tokens.pop(0)

    async def recover_after_rejection(*, use_reauth: bool) -> bool:
        recoveries.append(use_reauth)
        return recovery_result

    auth.current_access_token = current_access_token
    auth.recover_after_rejection = recover_after_rejection
    return auth


def test_gateway_request_recovers_auth_rejections() -> None:
    gateway_request = cast(
        Callable[
            [gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, tuple[int, Any, bytes, str]]
        ],
        getattr(gateway_cli, '_gateway_request'),
    )
    recoveries: list[bool] = []
    auth = make_mock_gateway_auth(['token-1', 'token-2', 'token-3'], recoveries)
    captured: list[dict[str, str]] = []
    client = make_mock_request_client(
        [MockGatewayResponse(401), MockGatewayResponse(401), MockGatewayResponse(200)], captured
    )
    state = gateway_cli.ProxyState(
        auth=auth,
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    status, _headers, body, content_type = asyncio.run(
        gateway_request(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{}')
    )

    assert (status, body, content_type) == (200, b'{}', 'application/json')
    assert recoveries == [False, True]
    assert [request['Authorization'] for request in captured] == [
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
    recoveries: list[bool] = []
    auth = make_mock_gateway_auth(['token-1'], recoveries, recovery_result=False)
    captured: list[dict[str, str]] = []
    client = make_mock_request_client([MockGatewayResponse(401)], captured)
    state = gateway_cli.ProxyState(
        auth=auth,
        client=client,
        gateway='https://gateway.example.com',
        region='us',
        local_token='local-token',
    )

    status, _headers, _body, _content_type = asyncio.run(
        gateway_request(state, 'POST', 'https://gateway.example.com/proxy/openai/v1', {}, b'{}')
    )

    assert status == 401
    assert recoveries == [False]
    assert len(captured) == 1


def test_gateway_stream_recovers_auth_rejections_and_closes_rejected_streams() -> None:
    gateway_stream = cast(
        Callable[[gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, Any]],
        getattr(gateway_cli, '_gateway_stream'),
    )
    recoveries: list[bool] = []
    auth = make_mock_gateway_auth(['token-1', 'token-2', 'token-3'], recoveries)
    first_response = MockGatewayStreamResponse(401)
    second_response = MockGatewayStreamResponse(401)
    final_response = MockGatewayStreamResponse(200)
    captured: list[dict[str, str]] = []
    client = make_mock_stream_client([first_response, second_response, final_response], captured)
    state = gateway_cli.ProxyState(
        auth=auth,
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
    assert recoveries == [False, True]
    assert [request['Authorization'] for request in captured] == [
        'Bearer token-1',
        'Bearer token-2',
        'Bearer token-3',
    ]


def test_gateway_stream_stops_when_auth_recovery_fails() -> None:
    gateway_stream = cast(
        Callable[[gateway_cli.ProxyState, str, str, dict[str, str], bytes], Coroutine[Any, Any, Any]],
        getattr(gateway_cli, '_gateway_stream'),
    )
    recoveries: list[bool] = []
    auth = make_mock_gateway_auth(['token-1'], recoveries, recovery_result=False)
    response = MockGatewayStreamResponse(401)
    captured: list[dict[str, str]] = []
    client = make_mock_stream_client([response], captured)
    state = gateway_cli.ProxyState(
        auth=auth,
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
    assert recoveries == [False]
    assert len(captured) == 1


def test_gateway_proxy_stream_decodes_compressed_upstream_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(gateway_cli, 'StreamingResponse', CapturedStreamingResponse)

    async def run() -> tuple[CapturedStreamingResponse, CompressedStreamResponse, bytes]:
        upstream_response = CompressedStreamResponse()
        state = gateway_cli.ProxyState(
            auth=Mock(),
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
    servers: list[object] = []

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
            servers.append(self)

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

    monkeypatch.setattr(gateway_cli, 'httpx', types.SimpleNamespace(AsyncClient=FakeAsyncClient))
    monkeypatch.setattr(gateway_cli, 'uvicorn', FakeUvicorn)
    monkeypatch.setattr(gateway_cli, 'Starlette', FakeStarlette)
    monkeypatch.setattr(gateway_cli, 'Route', fake_route)
    monkeypatch.setattr(gateway_cli, 'GatewayAuth', FakeGatewayAuth)
    monkeypatch.setattr(gateway_cli.secrets, 'token_urlsafe', token_urlsafe)

    async def run() -> tuple[gateway_cli.ProxyState, str]:
        async with authorize_and_serve(
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
    # uvicorn's signal capture is replaced so Ctrl-C interrupts the OAuth wait instead of
    # being swallowed by the server's handle_exit (which would only set should_exit=True).
    assert len(servers) == 1
    assert getattr(servers[0], 'capture_signals') is gateway_cli._no_capture_signals  # type: ignore[attr-defined]


@pytest.mark.skipif(sys.platform == 'win32', reason='loop.add_signal_handler is not supported on Windows')
def test_gateway_await_or_signal_raises_keyboard_interrupt_on_sigint() -> None:
    import signal as _signal

    await_or_signal = getattr(gateway_cli, '_await_or_signal')

    async def run() -> str:
        asyncio.get_running_loop().call_later(0.05, _signal.raise_signal, _signal.SIGINT)
        try:
            return await await_or_signal(asyncio.sleep(60, result='unreached'))
        except KeyboardInterrupt:
            return 'interrupted'

    assert asyncio.run(run()) == 'interrupted'


@pytest.mark.skipif(sys.platform == 'win32', reason='loop.add_signal_handler is not supported on Windows')
def test_gateway_await_or_signal_returns_value_when_no_signal() -> None:
    await_or_signal = getattr(gateway_cli, '_await_or_signal')

    async def run() -> str:
        return await await_or_signal(asyncio.sleep(0, result='done'))

    assert asyncio.run(run()) == 'done'


def test_gateway_no_capture_signals_is_a_noop_context_manager() -> None:
    with gateway_cli._no_capture_signals() as value:  # type: ignore[attr-defined]
        assert value is None


@pytest.mark.skipif(sys.platform == 'win32', reason='loop.add_signal_handler is not supported on Windows')
def test_gateway_await_or_signal_ignores_repeat_signal() -> None:
    import signal as _signal

    await_or_signal = getattr(gateway_cli, '_await_or_signal')

    async def run() -> str:
        loop = asyncio.get_running_loop()
        handlers: list[Any] = []
        real_add_signal_handler = loop.add_signal_handler

        def capture(sig: int, callback: Any, *args: Any) -> None:
            if sig == _signal.SIGINT:
                handlers.append(callback)
            real_add_signal_handler(sig, callback, *args)

        loop.add_signal_handler = capture

        async def fire_twice() -> None:
            await asyncio.sleep(0)
            handlers[0]()  # first SIGINT -> sets stop
            handlers[0]()  # second SIGINT -> stop.done() is True, branch covered
            await asyncio.sleep(60)

        try:
            return await await_or_signal(fire_twice())
        except KeyboardInterrupt:
            return 'interrupted'

    assert asyncio.run(run()) == 'interrupted'


def test_gateway_await_or_signal_handles_unsupported_add_signal_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await_or_signal = getattr(gateway_cli, '_await_or_signal')

    async def run() -> str:
        loop = asyncio.get_running_loop()

        def _raise(*_args: Any, **_kwargs: Any) -> None:
            raise NotImplementedError

        monkeypatch.setattr(loop, 'add_signal_handler', _raise)
        return await await_or_signal(asyncio.sleep(0, result='done'))

    assert asyncio.run(run()) == 'done'


def test_gateway_authorize_and_serve_fails_when_server_does_not_start(monkeypatch: pytest.MonkeyPatch) -> None:
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

    monkeypatch.setattr(gateway_cli, 'httpx', types.SimpleNamespace(AsyncClient=FakeAsyncClient))
    monkeypatch.setattr(gateway_cli, 'uvicorn', types.SimpleNamespace(Config=fake_config, Server=FakeServer))
    monkeypatch.setattr(gateway_cli, 'Starlette', FakeStarlette)
    monkeypatch.setattr(gateway_cli, 'Route', fake_route)

    async def run() -> None:
        async with authorize_and_serve(
            region='us',
            backend='https://backend.example',
            gateway='https://gateway.example',
            client_id='client-id',
            scope='scope',
            port=9999,
            flow='device',
        ):
            raise AssertionError('context should not be entered')

    with pytest.raises(gateway_auth.GatewayError, match='Logfire Gateway proxy failed to start'):
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
            auth=Mock(),
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
            auth=Mock(),
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
            auth=Mock(),
            client=Mock(),
            gateway='https://gateway.example.com',
            region='us',
            local_token='local-token',
        )
        yield state, 'http://127.0.0.1:9999'

    async def sleep(_seconds: float) -> None:
        raise KeyboardInterrupt

    def pick_same_port(port: int) -> int:
        return port

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

    def raise_gateway_error(_raw: list[str], _context: gateway_cli.GatewayCommandContext) -> int:
        raise gateway_auth.GatewayError('authorization failed: access_denied')

    def raise_keyboard_interrupt(_raw: list[str], _context: gateway_cli.GatewayCommandContext) -> int:
        raise KeyboardInterrupt

    context = gateway_cli.GatewayCommandContext(raw_args=[], region=None, logfire_url=None)
    monkeypatch.setattr(gateway_cli, '_run_launch', raise_config_error)

    assert gateway_cli.execute_gateway_command(gateway_cli.GatewayCommand('launch', ()), context) == 1
    assert 'missing dependency' in capsys.readouterr().err

    monkeypatch.setattr(gateway_cli, '_run_launch', raise_gateway_error)
    assert gateway_cli.execute_gateway_command(gateway_cli.GatewayCommand('launch', ()), context) == 1
    err = capsys.readouterr().err
    assert 'authorization failed: access_denied' in err
    assert 'Traceback' not in err

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
