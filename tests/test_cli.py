import io
import json
import os
import re
import shlex
import sys
import webbrowser
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import call, patch

import pytest
import requests
import requests_mock
from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire._internal.cli
from logfire import VERSION
from logfire._internal.cli import OTEL_PACKAGES, main
from logfire._internal.config import LogfireCredentials, sanitize_project_name
from logfire.exceptions import LogfireConfigError


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        project_url='https://dashboard.logfire.dev',
        logfire_api_url='https://logfire-api.pydantic.dev',
    )


def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    assert 'usage: logfire [-h] [--version]  ...' in capsys.readouterr().out


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
            'https://logfire-api.pydantic.dev/v1/info',
            json={'project_name': 'myproject', 'project_url': 'fake_project_url'},
        )

        main(['whoami'])

        assert len(request_mocker.request_history) == 1
        assert capsys.readouterr().err == 'Logfire project URL: fake_project_url\n'


def test_whoami(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]) -> None:
    with patch.dict(os.environ, {'LOGFIRE_TOKEN': 'foobar'}), requests_mock.Mocker() as request_mocker:
        # Also test LOGFIRE_TOKEN being set but the API being healthy, so it can't be checked
        request_mocker.get('http://localhost/v1/info', status_code=500)

        logfire_credentials.write_creds_file(tmp_dir_cwd)

        with pytest.warns(
            UserWarning, match='Logfire API returned status code 500, you may have trouble sending data.'
        ):
            main(shlex.split(f'--logfire-url=http://localhost:0 whoami --data-dir {tmp_dir_cwd}'))

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
        main(['--logfire-url=http://localhost:0', 'whoami'])
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
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value='123'))

        m = requests_mock.Mocker()
        stack.enter_context(m)

        m.get('http://localhost/v1/account/me', json={'name': 'test-user'})

        main(shlex.split(f'--logfire-url=http://localhost:0 whoami --data-dir {tmp_dir_cwd}'))
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
    main(['--logfire-url=http://localhost:0', 'whoami'])
    assert capsys.readouterr().err.splitlines() == snapshot(
        [
            'Not logged in. Run `logfire auth` to log in.',
            IsStr(regex=r'^Credentials loaded from data dir: .*/\.logfire$'),
            '',
            'Logfire project URL: https://dashboard.logfire.dev',
        ]
    )


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
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['inspect'])
    assert capsys.readouterr().err.startswith('The following packages')


def test_inspect_drop_dependant_packages(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    with ExitStack() as stack:
        find_spec = stack.enter_context(patch('importlib.util.find_spec'))
        find_spec.side_effect = [True, None] * len(OTEL_PACKAGES)

        main(['inspect'])
        output = capsys.readouterr().err
        assert 'opentelemetry-instrumentation-fastapi' in output
        assert 'opentelemetry-instrumentation-starlette' not in output


@pytest.mark.parametrize('webbrowser_error', [False, True])
def test_auth(tmp_path: Path, webbrowser_error: bool) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.cli.DEFAULT_FILE', auth_file))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        webbrowser_open = stack.enter_context(
            patch('webbrowser.open', side_effect=webbrowser.Error if webbrowser_error is True else None)
        )

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-api.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-api.pydantic.dev/v1/device-auth/wait/DC',
            [
                dict(text='null'),
                dict(text='{"token": "fake_token", "expiration": "fake_exp"}'),
            ],
        )

        main(['auth'])

        assert auth_file.read_text() == snapshot(
            """\
[tokens."https://logfire-api.pydantic.dev"]
token = "fake_token"
expiration = "fake_exp"
"""
        )

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == snapshot(
            [
                IsStr(regex=r'^\(file=.*'),
                'print()',
                "print('Welcome to Logfire! :fire:')",
                "print('Before you can send data to Logfire, we need to authenticate you.')",
                'print()',
                "input('Press [bold]Enter[/] to open example.com in your browser...')",
                'print("Please open [bold]http://example.com/auth[/] in your browser to authenticate if it hasn\'t already.")',
                "print('Waiting for you to authenticate with Logfire...')",
                "print('Successfully authenticated!')",
                'print()',
                IsStr(regex=r"^print\('Your Logfire credentials are stored in \[bold\].*/default.toml\[/\]'\)"),
            ]
        )

        webbrowser_open.assert_called_once_with('http://example.com/auth', new=2)


def test_auth_temp_failure(tmp_path: Path) -> None:
    auth_file = tmp_path / 'default.toml'
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.cli.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-api.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get(
            'https://logfire-api.pydantic.dev/v1/device-auth/wait/DC',
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
        stack.enter_context(patch('logfire._internal.cli.DEFAULT_FILE', auth_file))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.webbrowser.open'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.post(
            'https://logfire-api.pydantic.dev/v1/device-auth/new/',
            text='{"device_code": "DC", "frontend_auth_url": "http://example.com/auth"}',
        )
        m.get('https://logfire-api.pydantic.dev/v1/device-auth/wait/DC', text='Error', status_code=500)

        with pytest.warns(UserWarning, match=r'^Failed to poll for token\. Retrying\.\.\.$'):
            with pytest.raises(LogfireConfigError, match='Failed to poll for token.'):
                main(['auth'])


def test_auth_on_authenticated_user(default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.cli.DEFAULT_FILE', default_credentials))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        main(['auth'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            f"print('You are already logged in. (Your credentials are stored in [bold]{default_credentials}[/])')",
        ]


def test_projects_help(capsys: pytest.CaptureFixture[str]) -> None:
    main(['projects'])
    assert capsys.readouterr().out.splitlines()[0] == 'usage: logfire projects [-h] {list,new,use} ...'


def test_projects_list(default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        table_add_row = stack.enter_context(patch('logfire._internal.cli.Table.add_row'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[{'organization_name': 'test-org', 'project_name': 'test-pr'}],
        )

        main(['projects', 'list'])

        assert "call('test-org', 'test-pr')" == str(table_add_row.mock_calls[0])


def test_projects_list_no_project(default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])

        main(['projects', 'list'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('No projects found for the current user. You can create a new project with `logfire projects new`')",
        ]


def test_projects_new_with_project_name_and_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--org', 'fake_org'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_with_project_name_without_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_with_project_name_and_wrong_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--org', 'wrong_org'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_with_project_name_and_default_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--default-org'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_with_project_name_multiple_organizations(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['fake_org']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get(
            'https://logfire-api.pydantic.dev/v1/organizations/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get(
            'https://logfire-api.pydantic.dev/v1/account/me',
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
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
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

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_with_project_name_and_default_org_multiple_organizations(
    tmp_dir_cwd: Path, default_credentials: Path
) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get(
            'https://logfire-api.pydantic.dev/v1/organizations/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get(
            'https://logfire-api.pydantic.dev/v1/account/me',
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
            'https://logfire-api.pydantic.dev/v1/projects/fake_default_org',
            [create_project_response],
        )

        main(['projects', 'new', 'myproject', '--default-org'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_without_project_name(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new', '--default-org'])

        assert prompt_mock.mock_calls == [
            call('Enter the project name', default=sanitize_project_name(tmp_dir_cwd.name))
        ]
        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_invalid_project_name(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
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
        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        with pytest.raises(LogfireConfigError, match='Invalid credentials, when initializing project:'):
            main(['projects', 'new', 'myproject', '--org', 'fake_org'])


def test_projects_without_project_name_without_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        confirm_mock = stack.enter_context(patch('rich.prompt.Confirm.ask', side_effect=[True]))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['myproject', '']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        create_project_response = {
            'json': {
                'project_name': 'myproject',
                'token': 'fake_token',
                'project_url': 'fake_project_url',
            }
        }
        m.post(
            'https://logfire-api.pydantic.dev/v1/projects/fake_org',
            [create_project_response],
        )

        main(['projects', 'new'])

        assert confirm_mock.mock_calls == [
            call('The project will be created in the organization "fake_org". Continue?', default=True),
        ]
        assert prompt_mock.mock_calls == [
            call('Enter the project name', default=sanitize_project_name(tmp_dir_cwd.name))
        ]
        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project created successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_new_get_organizations_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error retrieving list of organizations.'):
            main(['projects', 'new'])


def test_projects_new_get_user_info_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get(
            'https://logfire-api.pydantic.dev/v1/organizations/',
            json=[{'organization_name': 'fake_org'}, {'organization_name': 'fake_default_org'}],
        )
        m.get('https://logfire-api.pydantic.dev/v1/account/me', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error retrieving user information.'):
            main(['projects', 'new'])


def test_projects_new_create_project_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get('https://logfire-api.pydantic.dev/v1/projects/', json=[])
        m.get('https://logfire-api.pydantic.dev/v1/organizations/', json=[{'organization_name': 'fake_org'}])
        m.post('https://logfire-api.pydantic.dev/v1/projects/fake_org', text='Error', status_code=500)

        with pytest.raises(LogfireConfigError, match='Error creating new project.'):
            main(['projects', 'new', 'myproject', '--org', 'fake_org'])


def test_projects_use(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project configured successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_use_without_project_name(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use'])

        assert prompt_mock.mock_calls == [
            call(
                (
                    'Please select one of the following projects by number:\n'
                    '1. fake_org/myproject\n'
                    '2. fake_org/otherproject\n'
                ),
                choices=['1', '2'],
                default='1',
            )
        ]

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project configured successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_use_multiple(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        config_console = stack.enter_context(patch('logfire._internal.config.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project configured successfully. You will be able to view it at: fake_project_url')",
        ]

        config_console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in config_console.mock_calls]
        assert config_console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Found multiple projects with name `myproject`.')",
        ]

        assert prompt_mock.mock_calls == [
            call(
                (
                    'Please select one of the following projects by number:\n'
                    '1. fake_org/myproject\n'
                    '2. other_org/myproject\n'
                ),
                choices=['1', '2'],
                default='1',
            )
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_use_multiple_with_org(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        main(['projects', 'use', 'myproject', '--org', 'fake_org'])

        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project configured successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_use_wrong_project(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['y', '1']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
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
                'Please select one of the following projects by number:\n1. fake_org/myproject\n',
                choices=['1'],
                default='1',
            ),
        ]
        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('Project configured successfully. You will be able to view it at: fake_project_url')",
        ]

        assert json.loads((tmp_dir_cwd / '.logfire/logfire_credentials.json').read_text()) == {
            **create_project_response['json'],
            'logfire_api_url': 'https://logfire-api.pydantic.dev',
        }


def test_projects_use_wrong_project_give_up(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        console = stack.enter_context(patch('logfire._internal.cli.Console'))
        config_console = stack.enter_context(patch('logfire._internal.config.Console'))
        prompt_mock = stack.enter_context(patch('rich.prompt.Prompt.ask', side_effect=['n']))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
        console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in console.mock_calls]
        assert console_calls == [
            IsStr(regex=r'^\(file=.*'),
        ]
        config_console_calls = [re.sub(r'^call(\(\).)?', '', str(call)) for call in config_console.mock_calls]
        assert config_console_calls == [
            IsStr(regex=r'^\(file=.*'),
            "print('You can create a new project in organization `fake_org` with `logfire projects new --org fake_org`')",
        ]


def test_projects_use_without_projects(tmp_dir_cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[],
        )

        main(['projects', 'use', 'myproject'])

        assert (
            re.sub(r'\s+', ' ', capsys.readouterr().err).strip()
            == 'No projects found for the current user. You can create a new project with `logfire projects new`'
        )


def test_projects_use_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
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
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            [create_project_response],
        )

        with pytest.raises(LogfireConfigError, match='Invalid credentials, when initializing project:'):
            main(['projects', 'use', 'myproject', '--org', 'fake_org'])


def test_projects_use_write_token_error(tmp_dir_cwd: Path, default_credentials: Path) -> None:
    with ExitStack() as stack:
        stack.enter_context(patch('logfire._internal.config.LogfireCredentials._get_user_token', return_value=''))
        stack.enter_context(patch('logfire._internal.cli.Console'))
        stack.enter_context(patch('logfire._internal.cli.LogfireCredentials.write_creds_file', side_effect=TypeError))

        m = requests_mock.Mocker()
        stack.enter_context(m)
        m.get(
            'https://logfire-api.pydantic.dev/v1/projects/',
            json=[{'organization_name': 'fake_org', 'project_name': 'myproject'}],
        )
        m.post(
            'https://logfire-api.pydantic.dev/v1/organizations/fake_org/projects/myproject/write-tokens/',
            text='Error',
            status_code=500,
        )

        with pytest.raises(LogfireConfigError, match='Error creating project write token.'):
            main(['projects', 'use', 'myproject', '--org', 'fake_org'])


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    main(['info'])
    output = capsys.readouterr().err.strip()
    assert output.startswith('logfire="')
    assert '[related_packages]' in output
