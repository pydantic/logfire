"""The CLI for Logfire."""
import argparse
import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Iterator

import requests
from rich.console import Console
from rich.progress import Progress

import logfire._config
from logfire._config import LogfireCredentials
from logfire.version import VERSION

console = Console()


def version_callback() -> None:
    """Show the version and exit."""
    py_impl = platform.python_implementation()
    py_version = platform.python_version()
    system = platform.system()
    print(f'Running Logfire {VERSION} with {py_impl} {py_version} on {system}.')


def parse_whoami(args: argparse.Namespace) -> None:
    """Get your dashboard url and project name."""
    data_dir = Path(args.data_dir)
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write('Data not found.\n')
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


def main(args: 'list[str] | None' = None) -> None:
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

    namespace = parser.parse_args(args)
    if namespace.version:
        version_callback()
    else:
        namespace.func(namespace)
