import platform
import shutil
from pathlib import Path

from rich.console import Console
from typer import Exit, Option, Typer, confirm, echo

from logfire.config import LogfireCredentials
from logfire.version import VERSION

app = Typer(help='The CLI for Logfire. 🚀')

# NOTE: If the app is divided into multiple files, use the typer.Context to share the Console object.
console = Console()


def version_callback(value: bool) -> None:
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
    ...


@app.command(help='Get your dashboard url and project name.')
def whoami(logfire_dir: Path = Path('.logfire')):
    credentials = LogfireCredentials.load_creds_file(logfire_dir)

    if credentials is None:
        console.print('Data not found.')
    else:
        credentials.print_existing_token_summary(logfire_dir, from_cli=True)


@app.command(help='Clean logfire data.')
def clean(logfire_dir: Path = Path('.logfire')):
    if confirm(f'The folder {logfire_dir} will be deleted. Are you sure?'):
        shutil.rmtree(logfire_dir)
        echo('Cleaned logfire data.')
    else:
        echo('Clean aborted.')
