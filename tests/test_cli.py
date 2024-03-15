import io
import os
import re
import shlex
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest
import requests
import requests_mock
from dirty_equals import IsStr

from logfire import VERSION
from logfire._config import LogfireCredentials
from logfire.cli import main
from logfire.exceptions import LogfireConfigError


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://api.logfire.dev',
    )


def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert 'usage: logfire [-h] [--version]  ...' in capsys.readouterr().out


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    main(['--version'])
    assert VERSION in capsys.readouterr().out.strip()


def test_whoami(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'whoami --data-dir {tmp_dir_cwd}'))
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == (
        f'Credentials loaded from data dir: {tmp_dir_cwd}\n' '\n' 'Logfire project URL: https://dashboard.logfire.dev\n'
    )


def test_whoami_without_data(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # Change to the temp dir so the test doesn't fail if executed from a folder containing logfire credentials.
    current_dir = os.getcwd()
    os.chdir(tmp_dir_cwd)
    try:
        main(['whoami'])
        # insert_assert(capsys.readouterr().err)
        assert capsys.readouterr().err == f'No Logfire credentials found in {tmp_dir_cwd}/.logfire\n'
    except SystemExit as e:
        assert e.code == 1
    finally:
        os.chdir(current_dir)


def test_whoami_default_dir(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['whoami'])
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == (
        f'Credentials loaded from data dir: {tmp_dir_cwd}/.logfire\n'
        '\n'
        'Logfire project URL: https://dashboard.logfire.dev\n'
    )


def test_clean(
    tmp_dir_cwd: Path,
    logfire_credentials: LogfireCredentials,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, 'stdin', io.StringIO('y'))
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'clean --data-dir {str(tmp_dir_cwd)}'))
    assert capsys.readouterr().err == 'Cleaned Logfire data.\n'


def test_inspect(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['inspect'])
    assert capsys.readouterr().err.startswith('The following packages')


def test_auth(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire.cli.DEFAULT_FILE', auth_file))
        console = stack.enter_context(mock.patch('logfire.cli.Console'))
        webbrowser_open = stack.enter_context(mock.patch('webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://api.logfire.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "FE_URL"}',
        )
        m.get(
            'https://api.logfire.dev/v1/device-auth/wait/DC',
            [
                dict(text='null'),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
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
        'print("Please open [bold]FE_URL[/] in your browser to authenticate if it hasn\'t already.")',
        "print('Waiting for you to authenticate with Logfire...')",
        "print('Successfully authenticated!')",
        'print()',
        f"print('Your Logfire credentials are stored in [bold]{auth_file}[/]')",
    ]

    webbrowser_open.assert_called_once_with('FE_URL', new=2)


def test_auth_temp_failure(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire.cli.DEFAULT_FILE', auth_file))
        stack.enter_context(mock.patch('logfire.cli.Console'))
        stack.enter_context(mock.patch('logfire.cli.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://api.logfire.dev/v1/device-auth/new/', text='{"device_code": "DC", "frontend_auth_url": "FE_URL"}'
        )
        m.get(
            'https://api.logfire.dev/v1/device-auth/wait/DC',
            [
                dict(exc=requests.exceptions.ConnectTimeout),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
        )

        with pytest.warns(UserWarning, match=r'^Failed to poll for token\. Retrying\.\.\.$'):
            main(['auth'])


def test_auth_permanent_failure(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(mock.patch('logfire.cli.DEFAULT_FILE', auth_file))
        stack.enter_context(mock.patch('logfire.cli.Console'))
        stack.enter_context(mock.patch('logfire.cli.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://api.logfire.dev/v1/device-auth/new/', text='{"device_code": "DC", "frontend_auth_url": "FE_URL"}'
        )
        m.get('https://api.logfire.dev/v1/device-auth/wait/DC', text='Error', status_code=500)

        with pytest.warns(UserWarning, match=r'^Failed to poll for token\. Retrying\.\.\.$'):
            with pytest.raises(LogfireConfigError, match='Failed to poll for token.'):
                main(['auth'])
