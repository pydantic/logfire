"""The CLI for Logfire. 🚀"""  # noqa: D415
import platform
import shutil
from pathlib import Path
from typing import Iterator

import httpx
from rich.console import Console
from typer import Exit, Option, Typer, confirm, echo

import logfire._config
from logfire._config import LogfireCredentials
from logfire.version import VERSION

app = Typer(help='The CLI for Logfire. 🚀')

# NOTE: If the app is divided into multiple files, use the typer.Context to share the Console object.
console = Console()


def version_callback(value: bool) -> None:
    """Show the version and exit.

    Args:
        value: The value of the `--version` option.
    """
    if value:
        py_impl = platform.python_implementation()
        py_version = platform.python_version()
        system = platform.system()
        echo(f'Running Logfire {VERSION} with {py_impl} {py_version} on {system}.')
        raise Exit(0)


@app.callback()
def main(
    version: bool = Option(
        None,
        '--version',
        callback=version_callback,
        is_eager=True,
        help='Show version and exit.',
    ),
):
    """The main entrypoint for the CLI."""


@app.command()
def whoami(data_dir: Path = Path('.logfire')):
    """Get your dashboard url and project name."""
    credentials = LogfireCredentials.load_creds_file(data_dir)

    if credentials is None:
        console.print('Data not found.')
    else:
        credentials.print_token_summary()


@app.command()
def clean(data_dir: Path = Path('.logfire')):
    """Clean logfire data."""
    if confirm(f'The folder {data_dir} will be deleted. Are you sure?'):
        shutil.rmtree(data_dir)
        echo('Cleaned logfire data.')
    else:
        echo('Clean aborted.')


@app.command()
def backfill(data_dir: Path = Path('.logfire'), file: Path = Path('logfire_spans.bin')) -> None:
    """Bulk load logfire data."""
    logfire._config.configure(data_dir=data_dir)
    config = logfire._config.GLOBAL_CONFIG
    config.initialize()
    token, _ = config.load_token()
    assert token is not None  # if no token was available a new project should have been created
    with open(file, 'rb') as f:
        with httpx.Client(headers={'Authorization': token}) as client:

            def reader() -> Iterator[bytes]:
                while True:
                    data = f.read(1024 * 1024)
                    if not data:
                        return
                    yield data

            response = client.post(f'{config.base_url}/backfill/traces', content=reader())
            response.raise_for_status()
            echo('Backfill done.')
