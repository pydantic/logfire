"""The CLI for Pydantic Logfire."""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import platform
import shutil
import sys
import warnings
import webbrowser
from pathlib import Path
from typing import Iterator, cast

import requests
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

import logfire._config
from logfire._auth import DEFAULT_FILE, HOME_LOGFIRE, DefaultFile, is_logged_in, poll_for_token, request_device_code
from logfire._config import LogfireCredentials
from logfire._constants import LOGFIRE_BASE_URL
from logfire._utils import read_toml_file
from logfire.version import VERSION

BASE_OTEL_INTEGRATION_URL = 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/'
BASE_DOCS_URL = 'https://docs.logfire.dev'
INTEGRATIONS_DOCS_URL = f'{BASE_DOCS_URL}/guide/integrations/'


def version_callback() -> None:
    """Show the version and exit."""
    py_impl = platform.python_implementation()
    py_version = platform.python_version()
    system = platform.system()
    print(f'Running Logfire {VERSION} with {py_impl} {py_version} on {system}.')


# TODO(Marcelo): Needs to be updated to reflect `logfire auth`.
def parse_whoami(args: argparse.Namespace) -> None:
    """Get your dashboard url and project name."""
    data_dir = Path(args.data_dir)
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write(f'No Logfire credentials found in {data_dir.resolve()}\n')
        sys.exit(1)
    else:
        sys.stderr.write(f'Credentials loaded from data dir: {data_dir.resolve()}\n\n')
        credentials.print_token_summary()


def parse_clean(args: argparse.Namespace) -> None:
    """Clean Logfire data."""
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        sys.stderr.write(f'No Logfire data found in {data_dir.resolve()}\n')
        sys.exit(1)

    confirm = input(f'The folder {data_dir.resolve()} will be deleted. Are you sure? [N/y]')
    if confirm.lower() in ('yes', 'y'):
        if data_dir.exists() and data_dir.is_dir():
            shutil.rmtree(data_dir)
        sys.stderr.write('Cleaned Logfire data.\n')
    else:
        sys.stderr.write('Clean aborted.\n')


def parse_backfill(args: argparse.Namespace) -> None:
    """Bulk load Logfire data."""
    data_dir = Path(args.data_dir)
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write(f'No Logfire credentials found in {data_dir.resolve()}\n')
        sys.exit(1)

    file = Path(args.file)
    if not file.exists():
        sys.stderr.write(f'No backfill file found at {file.resolve()}\n')
        sys.exit(1)

    logfire_url = cast(str, args.logfire_url)
    logfire.configure(data_dir=data_dir, base_url=logfire_url, collect_system_metrics=False)
    config = logfire._config.GLOBAL_CONFIG
    config.initialize()
    token, _ = config.load_token()
    assert token is not None  # if no token was available a new project should have been created
    console = Console(file=sys.stderr)
    with Progress(console=console) as progress:
        total = os.path.getsize(file)
        task = progress.add_task('Backfilling...', total=total)
        with file.open('rb') as f:

            def reader() -> Iterator[bytes]:
                while True:
                    data = f.read(1024 * 1024)
                    if not data:
                        return
                    yield data
                    progress.update(task, completed=f.tell())

            response = requests.post(
                f'{config.base_url}/backfill/traces',
                data=reader(),
                headers={'Content-Length': str(total)},
            )
            if response.status_code != 200:
                try:
                    data = response.json()
                except requests.JSONDecodeError:
                    data = response.text
                console.print(data)
                sys.exit(1)


# TODO(Marcelo): Automatically check if this list should be updated.
# NOTE: List of packages from https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation.
OTEL_PACKAGES: set[str] = {
    'aio_pika',
    'aiohttp',
    'aiopg',
    'asyncpg',
    'boto',
    'celery',
    'confluent_kafka',
    'django',
    'elasticsearch',
    'falcon',
    'fastapi',
    'flask',
    'grpc',
    'httpx',
    'jinja2',
    'kafka_python',
    'mysql',
    'mysqlclient',
    'pika',
    'psycopg2',
    'pymemcache',
    'pymongo',
    'pymysql',
    'pyramid',
    'remoulade',
    'requests',
    'sklearn',
    'sqlalchemy',
    'sqlite3',
    'starlette',
    'tornado',
    'tortoise_orm',
    'urllib',
    'urllib3',
}
OTEL_PACKAGE_LINK = {'aiohttp': 'aiohttp-client', 'tortoise_orm': 'tortoiseorm'}


def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend the opentelemetry package that can be used with it."""
    console = Console(file=sys.stderr)
    table = Table()
    table.add_column('Package')
    table.add_column('OpenTelemetry instrumentation package')

    # Ignore warnings from packages that we don't control.
    warnings.simplefilter('ignore', category=UserWarning)

    packages: dict[str, str] = {}
    for name in OTEL_PACKAGES:
        # Check if the package can be imported (without actually importing it).
        if importlib.util.find_spec(name) is None:
            continue

        otel_package = OTEL_PACKAGE_LINK.get(name, name)
        otel_package_import = f'opentelemetry.instrumentation.{otel_package}'

        if importlib.util.find_spec(otel_package_import) is None:
            packages[name] = otel_package

    # Drop packages that are dependencies of other packages.
    if packages.get('starlette') and packages.get('fastapi'):
        del packages['starlette']

    for name, otel_package in sorted(packages.items()):
        package_name = otel_package.replace('.', '-')
        import_name = otel_package.replace('-', '_')
        link = f'[link={BASE_OTEL_INTEGRATION_URL}/{import_name}/{import_name}.html]opentelemetry-instrumentation-{package_name}[/link]'
        table.add_row(name, link)

    console.print(
        'The following packages from your environment have an OpenTelemetry instrumentation that is not installed:'
    )
    console.print(table)

    if packages:
        otel_packages_to_install = ' '.join(
            f'opentelemetry-instrumentation-{pkg.replace(".", "-")}' for pkg in packages.values()
        )
        install_command = f'pip install {otel_packages_to_install}'
        console.print('\n[bold green]To install these packages, run:[/bold green]\n')
        console.print(f'[bold]$[/bold] [cyan]{install_command}[/cyan]', justify='center')
        console.print('\n[bold blue]For further information, visit[/bold blue]', end=' ')
        console.print(f'[link={INTEGRATIONS_DOCS_URL}]{INTEGRATIONS_DOCS_URL}[/link]')


def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This command will authenticate you with Logfire, and store the credentials.
    """
    console = Console(file=sys.stderr)
    logfire_url = cast(str, args.logfire_url)

    if DEFAULT_FILE.is_file():
        data = cast(DefaultFile, read_toml_file(DEFAULT_FILE))
        if is_logged_in(data, logfire_url):
            console.print(f'You are already logged in. (Your credentials are stored in [bold]{DEFAULT_FILE}[/])')
            return
    else:
        data: DefaultFile = {'tokens': {}}

    console.print()
    console.print('Welcome to Logfire! :fire:')
    console.print('Before you can send data to Logfire, we need to authenticate you.')
    console.print()

    with requests.Session() as session:
        device_code, frontend_auth_url = request_device_code(session, logfire_url)
        console.input('Press [bold]Enter[/] to open logfire.dev in your browser...')
        try:
            webbrowser.open(frontend_auth_url, new=2)
        except webbrowser.Error:
            pass
        console.print(f"Please open [bold]{frontend_auth_url}[/] in your browser to authenticate if it hasn't already.")
        console.print('Waiting for you to authenticate with Logfire...')

        data['tokens'][logfire_url] = poll_for_token(session, device_code, logfire_url)
        console.print('Successfully authenticated!')

    HOME_LOGFIRE.mkdir(exist_ok=True)
    # There's no standard library package to write TOML files, so we'll write it manually.
    with DEFAULT_FILE.open('w') as f:
        for url, info in data['tokens'].items():
            f.write(f'[tokens."{url}"]\n')
            f.write(f'token = "{info["token"]}"\n')
            f.write(f'expiration = "{info["expiration"]}"\n')

    console.print()
    console.print(f'Your Logfire credentials are stored in [bold]{DEFAULT_FILE}[/]')
    # TODO(Marcelo): Add a message to inform which commands can be used.


def main(args: list[str] | None = None) -> None:
    """Run the CLI."""
    parser = argparse.ArgumentParser(
        prog='logfire',
        description='The CLI for Pydantic Logfire.',
        add_help=True,
        epilog='See https://docs.logfire.dev/guide/cli/ for more detailed documentation.',
    )

    parser.add_argument('--version', action='store_true', help='show the version and exit')
    parser.set_defaults(func=lambda _: parser.print_help())  # type: ignore
    subparsers = parser.add_subparsers(title='commands', metavar='')

    # Note(DavidM): Let's try to keep the commands listed in alphabetical order if we can
    cmd_auth = subparsers.add_parser('auth', help='Authenticate with Logfire')
    cmd_auth.add_argument('--logfire-url', default=LOGFIRE_BASE_URL, help=argparse.SUPPRESS)
    cmd_auth.set_defaults(func=parse_auth)

    cmd_backfill = subparsers.add_parser('backfill', help='Bulk ingest backfill data')
    cmd_backfill.add_argument('--data-dir', default='.logfire')
    cmd_backfill.add_argument('--file', default='logfire_spans.bin')
    cmd_backfill.add_argument('--logfire-url', default=LOGFIRE_BASE_URL, help=argparse.SUPPRESS)
    cmd_backfill.set_defaults(func=parse_backfill)

    cmd_clean = subparsers.add_parser('clean', help='Remove the contents of the Logfire data directory')
    cmd_clean.add_argument('--data-dir', default='.logfire')
    cmd_clean.set_defaults(func=parse_clean)

    cmd_inspect = subparsers.add_parser(
        'inspect',
        help="Suggest opentelemetry instrumentations based on your environment's installed packages",
    )
    cmd_inspect.set_defaults(func=parse_inspect)

    cmd_whoami = subparsers.add_parser('whoami', help='Display the URL to your Logfire project')
    cmd_whoami.add_argument('--data-dir', default='.logfire')
    cmd_whoami.set_defaults(func=parse_whoami)

    namespace = parser.parse_args(args)
    if namespace.version:
        version_callback()
    else:
        namespace.func(namespace)
