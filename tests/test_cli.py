import io
import os
import re
import shlex
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest
import requests_mock
from dirty_equals import IsStr

from logfire import VERSION
from logfire._config import LogfireCredentials
from logfire.cli import main


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://api.logfire.dev',
    )


@pytest.fixture
def tmp_dir_cwd(tmp_path: Path):
    """Change the working directory to a temporary directory."""
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(os.path.dirname(__file__))  # Reset to the original directory after the test


def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert 'usage: Logfire [-h] [--version]  ...' in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    main(['--version'])
    assert VERSION in capsys.readouterr().out.strip()


def test_whoami(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'whoami --data-dir {str(tmp_dir_cwd)}'))
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == 'Logfire project: https://dashboard.logfire.dev\n'


def test_whoami_without_data(capsys: pytest.CaptureFixture[str]) -> None:
    main(['whoami'])
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == f'No Logfire credentials found in {os.getcwd()}/.logfire\n'


def test_whoami_default_dir(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['whoami'])
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == 'Logfire project: https://dashboard.logfire.dev\n'


def test_clean(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO('y'))
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'clean --data-dir {str(tmp_dir_cwd)}'))
    assert capsys.readouterr().err == 'Cleaned logfire data.\n'


def test_inspect(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['inspect'])
    # insert_assert(capsys.readouterr().err.splitlines()[0])
    assert (
        capsys.readouterr().err.splitlines()[0]
        == 'The following packages are installed, but not their opentelemetry package:'
    )


def test_auth(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire.cli.DEFAULT_FILE', auth_file))
        console = stack.enter_context(mock.patch('logfire.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://api.logfire.dev/v1/device-auth/new/', text='{"device_code": "DC", "frontend_auth_url": "FE_URL"}'
        )
        m.get(
            'https://api.logfire.dev/v1/device-auth/wait/DC', text='{"token": "fake_token", "expiration": "fake_exp"}'
        )

        main(['auth'])

    # insert_assert(auth_file.read_text())
    assert (
        auth_file.read_text() == '[tokens."https://api.logfire.dev"]\ntoken = "fake_token"\nexpiration = "fake_exp"\n'
    )

    console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
    # insert_assert(console_calls)
    assert console_calls == [
        IsStr(regex=r'^\(file=.*'),
        'print()',
        "print('Welcome to Logfire! :fire:')",
        "print('Before you can send data to Logfire, we need to authenticate you.')",
        'print()',
        "input('Press [bold]Enter[/] to open logfire.dev in your browser...')",
        "print('Waiting for you to authenticate with Logfire...')",
        "print('Successfully authenticated!')",
        'print()',
        f"print('Your Logfire credentials are stored in [bold]{auth_file}[/]')",
    ]
