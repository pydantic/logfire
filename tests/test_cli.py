import io
import os
import shlex
import sys
from pathlib import Path

import pytest

from logfire import VERSION
from logfire._config import LogfireCredentials
from logfire.cli import main


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        dashboard_url='https://dashboard.logfire.dev',
        logfire_api_url='https://api.logfire.dev',
    )


@pytest.fixture
def tmp_dir_cwd(tmp_path: Path):
    """Change the working directory to a temporary directory."""
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(os.path.dirname(__file__))  # Reset to the original directory after the test


@pytest.mark.skipif(sys.version_info < (3, 10), reason='output message is slightly different in lower versions')
def test_no_args(capsys: pytest.CaptureFixture[str]) -> None:
    main([])
    # insert_assert(capsys.readouterr().out.splitlines())
    assert capsys.readouterr().out.splitlines() == [
        'usage: Logfire [-h] [--version]  ...',
        '',
        'The CLI for Logfire.',
        '',
        'options:',
        '  -h, --help  show this help message and exit',
        '  --version   Show version and exit.',
        '',
        'commands:',
        '  ',
        '    whoami    Get your dashboard url and project name.',
        '    clean     Clean logfire data.',
        '    backfill  Bulk load logfire data.',
        '    inspect   Inspect installed packages, and recommend OTel package that can be used with it.',
    ]


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    main(['--version'])
    assert VERSION in capsys.readouterr().out.strip()


def test_whoami(tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd)
    main(shlex.split(f'whoami --data-dir {str(tmp_dir_cwd)}'))
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == 'Logfire dashboard: https://dashboard.logfire.dev\n'


def test_whoami_without_data(capsys: pytest.CaptureFixture[str]) -> None:
    main(['whoami'])
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == 'Data not found.\n'


def test_whoami_default_dir(
    tmp_dir_cwd: Path, logfire_credentials: LogfireCredentials, capsys: pytest.CaptureFixture[str]
) -> None:
    logfire_credentials.write_creds_file(tmp_dir_cwd / '.logfire')
    main(['whoami'])
    # insert_assert(capsys.readouterr().err)
    assert capsys.readouterr().err == 'Logfire dashboard: https://dashboard.logfire.dev\n'


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
