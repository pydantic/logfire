from pathlib import Path

import pytest
from typer.testing import CliRunner

from logfire._config import LogfireCredentials
from logfire.cli import app
from logfire.version import VERSION


@pytest.fixture
def logfire_credentials() -> LogfireCredentials:
    return LogfireCredentials(
        token='token',
        project_name='my-project',
        dashboard_url='https://dashboard.logfire.dev',
        logfire_api_url='https://api.logfire.dev',
    )


def test_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ['--version'])
    assert result.exit_code == 0
    assert VERSION in result.stdout


def test_whoami(logfire_credentials: LogfireCredentials) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp_dir:
        logfire_credentials.write_creds_file(Path(tmp_dir))
        result = runner.invoke(app, ['whoami', '--credentials-dir', tmp_dir])
        assert result.exit_code == 0
        assert logfire_credentials.dashboard_url in result.stdout
        assert logfire_credentials.project_name in result.stdout


def test_whoami_without_data() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp_dir:
        result = runner.invoke(app, ['whoami', '--credentials-dir', tmp_dir])
        assert result.exit_code == 0
        assert 'Data not found.' in result.stdout


def test_whoami_default_dir(logfire_credentials: LogfireCredentials) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp_dir:
        logfire_credentials.write_creds_file(Path(tmp_dir) / '.logfire')
        result = runner.invoke(app, ['whoami'])
        assert result.exit_code == 0
        assert logfire_credentials.dashboard_url in result.stdout
        assert logfire_credentials.project_name in result.stdout


def test_clean(logfire_credentials: LogfireCredentials) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp_dir:
        logfire_credentials.write_creds_file(Path(tmp_dir))
        assert Path(tmp_dir).exists()
        result = runner.invoke(app, ['clean', '--credentials-dir', tmp_dir], input='y')
        assert result.exit_code == 0, result.stdout
        assert 'Cleaned logfire data.' in result.stdout
        assert not Path(tmp_dir).exists()
