"""The CLI for Logfire."""
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
from urllib.parse import urljoin

import requests
from rich.console import Console
from rich.progress import Progress
from rich.prompt import Confirm
from rich.table import Table

import logfire._config
from logfire._config import LogfireCredentials
from logfire._constants import LOGFIRE_BASE_URL
from logfire._login import DEFAULT_FILE, HOME_LOGFIRE, DefaultFile, is_logged_in, poll_for_token, request_device_code
from logfire._utils import read_toml_file
from logfire.version import VERSION

BASE_OTEL_INTEGRATION_URL = 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/'
BASE_DOCS_URL = 'https://docs.logfire.dev/'
INTEGRATIONS_DOCS_URL = f'{BASE_DOCS_URL}/integrations/'
GITHUB_CLIENT_ID = '8cb77606ce18f76d36ce'
"""GitHub client ID used to authenticate with Logfire."""


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
    else:
        credentials.print_token_summary()


def parse_clean(args: argparse.Namespace) -> None:
    """Clean logfire data."""
    data_dir = Path(args.data_dir)
    confirm = input(f'The folder {data_dir} will be deleted. Are you sure? [N/y]')
    if confirm.lower() in ('yes', 'y'):
        if data_dir.exists() and data_dir.is_dir():
            shutil.rmtree(data_dir)
        sys.stderr.write('Cleaned logfire data.\n')
    else:
        sys.stderr.write('Clean aborted.\n')


def parse_backfill(args: argparse.Namespace) -> None:
    """Bulk load logfire data."""
    data_dir = Path(args.data_dir)
    file = Path(args.file)
    logfire._config.configure(data_dir=data_dir)
    config = logfire._config.GLOBAL_CONFIG
    config.initialize()
    token, _ = config.load_token()
    assert token is not None  # if no token was available a new project should have been created
    console = Console(file=sys.stderr)
    with Progress(console=console) as progress:
        with open(file, 'rb') as f:
            total = os.path.getsize(file)

            task = progress.add_task('Backfilling...', total=total)

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
    table.add_column('Opentelemetry package')

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

    console.print('The following packages are installed, but not their opentelemetry package:')
    console.print(table)

    if packages:
        otel_packages_to_install = ' '.join(
            f'opentelemetry-instrumentation-{pkg.replace(".", "-")}' for pkg in packages.values()
        )
        install_command = f'pip install {otel_packages_to_install}'
        console.print('\n[bold green]Command to install missing OpenTelemetry packages:[/bold green]\n')
        console.print(f'[bold]$[/bold] [cyan]{install_command}[/cyan]', justify='center')
        console.print('\n[bold blue]For further information, check our documentation:[/bold blue]', end=' ')
        console.print(f'[link={INTEGRATIONS_DOCS_URL}]https://logfire.dev/docs[/link]')


def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This command will authenticate the user with Logfire, and store the credentials.
    """
    console = Console(file=sys.stderr)
    logfire_url = cast(str, args.logfire_url)
    github_client_id = cast(str, args.github_client_id)

    if DEFAULT_FILE.is_file():
        data = cast(DefaultFile, read_toml_file(DEFAULT_FILE))
        if is_logged_in(data, logfire_url):
            console.print(f'You are already logged in. Credentials are stored in [bold]{DEFAULT_FILE}[/]')
            return
    else:
        data: DefaultFile = {'tokens': {}}

    with requests.Session() as session:
        session.headers.update({'Accept': 'application/json'})
        res = request_device_code(session, github_client_id)

        console.print()
        console.print('Welcome to Logfire! :fire:')
        console.print('Before you can send data to Logfire, we need to authenticate you.')
        console.print()
        user_agreed_with_terms = Confirm.ask(
            'Please confirm that you agree to our Terms of Service '
            '(https://docs.logfire.dev/legal/terms_of_service/) '
            'and Privacy Policy (https://docs.logfire.dev/legal/privacy/)',
            default=True,
        )
        if not user_agreed_with_terms:
            console.print()
            console.print('You must agree to the terms of service and privacy policy to use Logfire.')
            exit(1)
        console.print()
        console.print('We use GitHub for authentication.')
        console.print(f"You'll be prompted for this one-time code: [bold]{res['user_code']}[/]")
        console.print()
        console.input('Press [bold]Enter[/] to open github.com in your browser...')
        try:
            webbrowser.open(res['verification_uri'], new=2)
        except webbrowser.Error:
            console.print(f'Please open [bold]{res["verification_uri"]}[/] in your browser to authenticate.')
        console.print('Waiting for you to authenticate with GitHub...')

        access_token = poll_for_token(
            session, client_id=github_client_id, interval=res['interval'], device_code=res['device_code']
        )
        console.print('Successfully authenticated!')

        login_endpoint = urljoin(logfire_url, '/v1/login/')
        machine_name = platform.uname()[1]
        res = session.post(
            login_endpoint,
            headers={'Authorization': f'{access_token}'},
            params={'machine_name': machine_name},
        )
        res.raise_for_status()
        data['tokens'][logfire_url] = res.json()

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
    parser = argparse.ArgumentParser(prog='Logfire', description='The CLI for Logfire.', add_help=True)
    parser.add_argument('--version', action='store_true', help='Show version and exit.')
    parser.set_defaults(func=lambda _: parser.print_help())  # type: ignore
    subparsers = parser.add_subparsers(title='commands', metavar='')

    cmd_whoami = subparsers.add_parser('whoami', help='Get your dashboard url and project name.')
    cmd_whoami.add_argument('--data-dir', default='.logfire')
    cmd_whoami.set_defaults(func=parse_whoami)

    cmd_cleanup = subparsers.add_parser('clean', help='Clean logfire data.')
    cmd_cleanup.add_argument('--data-dir', default='.logfire')
    cmd_cleanup.set_defaults(func=parse_clean)

    cmd_backfill = subparsers.add_parser('backfill', help='Bulk load logfire data.')
    cmd_backfill.add_argument('--data-dir', default='.logfire')
    cmd_backfill.add_argument('--file', default='logfire_spans.bin')
    cmd_backfill.set_defaults(func=parse_backfill)

    cmd_inspect = subparsers.add_parser(
        'inspect', help='Inspect installed packages, and recommend OTel package that can be used with it.'
    )
    cmd_inspect.set_defaults(func=parse_inspect)

    cmd_login = subparsers.add_parser('auth', help='Authenticate with Logfire.')
    cmd_login.add_argument('--logfire-url', default=LOGFIRE_BASE_URL, help='Logfire API URL.')
    cmd_login.add_argument('--github-client-id', default=GITHUB_CLIENT_ID, help='GitHub client ID.')
    cmd_login.set_defaults(func=parse_auth)

    namespace = parser.parse_args(args)
    if namespace.version:
        version_callback()
    else:
        namespace.func(namespace)
