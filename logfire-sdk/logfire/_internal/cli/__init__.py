"""The CLI for Pydantic Logfire."""

from __future__ import annotations

import argparse
import functools
import logging
import os
import platform
import sys
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import requests
from rich.console import Console

from logfire.exceptions import LogfireConfigError
from logfire.propagate import ContextCarrier, get_context

from ...version import VERSION
from ..auth import HOME_LOGFIRE
from ..client import LogfireClient
from ..config import REGIONS, LogfireCredentials, get_base_url_from_token
from ..config_params import ParamManager
from ..http_transport import install_connection_policy
from ..interactive import NonInteractiveError, is_non_interactive, require_answer, set_non_interactive
from ..logfire_info import logfire_info
from ..server_response import install_logfire_response_hook
from ..tracer import SDKTracerProvider
from ..utils import READ_TOKEN_FILENAME
from .auth import parse_auth, parse_logout
from .prompt import parse_prompt
from .run import collect_instrumentation_context, parse_run, print_otel_summary

BASE_OTEL_INTEGRATION_URL = 'https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/'
BASE_DOCS_URL = 'https://logfire.pydantic.dev/docs'
INTEGRATIONS_DOCS_URL = f'{BASE_DOCS_URL}/integrations/'
LOGFIRE_LOG_FILE = HOME_LOGFIRE / 'log.txt'

logger = logging.getLogger(__name__)
__all__ = 'main', 'logfire_info'


def version_callback() -> None:
    """Show the version and exit."""
    py_impl = platform.python_implementation()
    py_version = platform.python_version()
    system = platform.system()
    print(f'Running Logfire {VERSION} with {py_impl} {py_version} on {system}.')


def _parse_gateway(args: argparse.Namespace) -> None:
    """Run a local OAuth proxy for the Logfire AI Gateway."""
    from .gateway import parse_gateway

    parse_gateway(args)


def parse_whoami(args: argparse.Namespace) -> None:
    """Show user authenticated username and the URL to your Logfire project."""
    data_dir = Path(args.data_dir)
    param_manager = ParamManager.create(data_dir)
    base_url: str | None = param_manager.load_param('base_url', args.logfire_url)
    tokens = param_manager.load_param('token')

    if tokens:
        # Display info for all configured tokens
        any_succeeded = False
        for i, token in enumerate(tokens):
            if len(tokens) > 1:
                if i > 0:
                    sys.stderr.write('\n')
                sys.stderr.write(f'Token {i + 1} of {len(tokens)}:\n')
            token_base_url = base_url or get_base_url_from_token(token)
            credentials = LogfireCredentials.from_token(token, args._session, token_base_url)
            if credentials:
                credentials.print_token_summary()
                any_succeeded = True
        if any_succeeded:
            return
        # If no tokens yielded credentials, fall through to try creds file

    try:
        client = LogfireClient.from_url(base_url)
    except LogfireConfigError:
        sys.stderr.write('Not logged in. Run `logfire auth` to log in.\n')
    else:
        current_user = client.get_user_information()
        username = current_user['name']
        sys.stderr.write(f'Logged in as: {username}\n')

    credentials = _load_credentials_or_exit(data_dir)
    sys.stderr.write(f'Credentials loaded from data dir: {data_dir.resolve()}\n\n')
    credentials.print_token_summary()


def parse_clean(args: argparse.Namespace) -> None:
    """Remove the contents of the Logfire data directory."""
    files_to_delete: list[Path] = []
    if args.logs and LOGFIRE_LOG_FILE.exists():
        files_to_delete.append(LOGFIRE_LOG_FILE)

    data_dir = Path(args.data_dir)
    if not data_dir.exists() or not data_dir.is_dir():
        sys.stderr.write(f'No Logfire data found in {data_dir.resolve()}\n')
        sys.exit(1)

    files_to_delete.append(data_dir / '.gitignore')
    files_to_delete.append(data_dir / 'logfire_credentials.json')
    # The saved read token is a credential too, and leaving it behind would mean a
    # "cleaned" data directory still holds something that can read the whole project.
    files_to_delete.append(data_dir / READ_TOKEN_FILENAME)

    files_to_display = '\n'.join([str(file) for file in files_to_delete if file.exists()])
    if not args.yes:
        require_answer(
            f'This would delete:\n{files_to_display}',
            'logfire clean --yes',
        )
    confirm = (
        'y' if args.yes else input(f'The following files will be deleted:\n{files_to_display}\nAre you sure? [N/y]')
    )
    if confirm.lower() in ('yes', 'y'):
        for file in files_to_delete:
            file.unlink(missing_ok=True)
        sys.stderr.write('Cleaned Logfire data.\n')
    else:
        sys.stderr.write('Clean aborted.\n')


def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend packages that might be useful."""
    console = Console(file=sys.stderr)

    ctx = collect_instrumentation_context(set(args.ignore))

    if ctx.recommendations:
        print_otel_summary(console=console, recommendations=ctx.recommendations)
        sys.exit(1)
    else:
        console.print('No recommended packages found. You are all set!', style='green')  # pragma: no cover


def _load_credentials_or_exit(data_dir: Path) -> LogfireCredentials:
    """The project this folder is linked to, or a clean exit saying so."""
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write(f'No Logfire credentials found in {data_dir.resolve()}\n')
        sys.exit(1)
    return credentials


def parse_info(_args: argparse.Namespace) -> None:
    """Show versions of logfire, OS and related packages."""
    sys.stderr.writelines(logfire_info())


def _get_logfire_url(logfire_url: str | None, region: str | None) -> str | None:
    if logfire_url is not None:
        return logfire_url
    if region is not None:
        return REGIONS[region]['base_url']
    return os.environ.get('LOGFIRE_BASE_URL') or None


class SplitArgs(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ):
        if isinstance(values, str):  # pragma: no branch
            values = values.split(',')
        namespace_value: list[str] = getattr(namespace, self.dest) or []
        setattr(namespace, self.dest, namespace_value + list(values or []))


class OrgProjectAction(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ):
        if isinstance(values, str) and '/' in values:
            try:
                organization, project = values.split('/')
                if not organization or not project:
                    parser.error(f'Invalid format: {values}. Expected <org>/<project>')
                setattr(namespace, 'organization', organization)
                setattr(namespace, self.dest, project)
            except ValueError:
                parser.error(f'Invalid format: {values}. Expected <org>/<project>')
        else:
            parser.error(f'Invalid format: {values}. Expected <org>/<project>')


def _main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='logfire',
        description='The CLI for Pydantic Logfire.',
        epilog='See https://logfire.pydantic.dev/docs/reference/cli/ for more detailed documentation.',
    )

    parser.add_argument('--version', action='store_true', help='show the version and exit')
    global_opts = parser.add_argument_group(title='global options')
    global_opts.add_argument(
        '--non-interactive',
        action='store_true',
        help='never prompt; fail with guidance if an answer would be required',
    )
    url_or_region_grp = global_opts.add_mutually_exclusive_group()
    url_or_region_grp.add_argument(
        '--base-url', help='the base URL for self-hosted Logfire instances (e.g., http://localhost:8080)'
    )
    url_or_region_grp.add_argument('--region', choices=REGIONS, help='the region to use')
    parser.set_defaults(func=lambda _: parser.print_help())  # pyright: ignore[reportUnknownLambdaType]
    subparsers = parser.add_subparsers(title='commands', metavar='')

    # NOTE(DavidM): Let's try to keep the commands listed in alphabetical order if we can
    cmd_auth = subparsers.add_parser('auth', help=parse_auth.__doc__.split('\n', 1)[0], description=parse_auth.__doc__)  # pyright: ignore[reportOptionalMemberAccess]
    cmd_auth.set_defaults(func=parse_auth)
    auth_subparsers = cmd_auth.add_subparsers()

    cmd_logout = auth_subparsers.add_parser('logout', help=parse_logout.__doc__, description=parse_logout.__doc__)
    cmd_logout.set_defaults(func=parse_logout)

    cmd_clean = subparsers.add_parser('clean', help=parse_clean.__doc__)
    cmd_clean.set_defaults(func=parse_clean)
    cmd_clean.add_argument('--data-dir', default='.logfire')
    cmd_clean.add_argument('--logs', action='store_true', default=False, help='remove the Logfire logs')
    cmd_clean.add_argument('--yes', '-y', action='store_true', default=False, help='do not ask for confirmation')

    cmd_gateway = subparsers.add_parser('gateway', help=_parse_gateway.__doc__)
    cmd_gateway.add_argument('gateway_args', nargs=argparse.REMAINDER)
    cmd_gateway.set_defaults(func=_parse_gateway)

    cmd_inspect = subparsers.add_parser('inspect', help=parse_inspect.__doc__)
    cmd_inspect.set_defaults(func=parse_inspect)
    cmd_inspect.add_argument('--ignore', action=SplitArgs, default=(), help='ignore a package')

    cmd_whoami = subparsers.add_parser('whoami', help=parse_whoami.__doc__)
    cmd_whoami.set_defaults(func=parse_whoami)
    cmd_whoami.add_argument('--data-dir', default='.logfire')

    cmd_prompt = subparsers.add_parser('prompt', help=parse_prompt.__doc__)
    agent_code_argument_group = cmd_prompt.add_argument_group(title='code agentic specific options')
    agent_code_group = agent_code_argument_group.add_mutually_exclusive_group()
    agent_code_group.add_argument('--claude', action='store_true', help='verify the Claude Code setup')
    agent_code_group.add_argument('--codex', action='store_true', help='verify the Cursor setup')
    agent_code_group.add_argument('--opencode', action='store_true', help='verify the OpenCode setup')
    cmd_prompt.add_argument(
        '--update', action='store_true', help='replace any existing Logfire MCP server configuration'
    )
    cmd_prompt.add_argument('--project', action=OrgProjectAction, help='project in the format <org>/<project>')
    cmd_prompt.add_argument('issue', nargs='?', help='the issue to get a prompt for')
    cmd_prompt.set_defaults(func=parse_prompt)

    cmd_info = subparsers.add_parser('info', help=parse_info.__doc__)
    cmd_info.set_defaults(func=parse_info)

    cmd_run = subparsers.add_parser('run', help='Run Python scripts/modules with Logfire instrumentation')
    cmd_run.add_argument('--summary', action=argparse.BooleanOptionalAction, default=True, help='hide the summary box')
    cmd_run.add_argument('--exclude', action=SplitArgs, default=(), help='exclude a package from instrumentation')
    cmd_run.add_argument('-m', '--module', help='Run module as script')
    cmd_run.add_argument(
        'script_and_args', nargs=argparse.REMAINDER, help='Script path and arguments, or module arguments when using -m'
    )
    cmd_run.set_defaults(func=parse_run)

    # We first try to parse everything, and if it's not the `parse_run` command, we parse again to raise an error on
    # unknown args. This is to allow the `parse_run` command to forward unknown args to the script/module.
    namespace, unknown_args = parser.parse_known_args(args)
    if namespace.func == parse_run:
        namespace.script_and_args = unknown_args + (namespace.script_and_args or [])
    else:
        namespace = parser.parse_args(args)
    set_non_interactive(namespace.non_interactive)

    namespace.logfire_url = _get_logfire_url(namespace.base_url, namespace.region)

    tracer = SDKTracerProvider().get_tracer(__name__)

    def log_trace_id(response: requests.Response, context: ContextCarrier, *args: Any, **kwargs: Any) -> None:
        logger.debug('context=%s url=%s', context, response.url)

    if namespace.version:
        version_callback()
    elif namespace.func in (parse_info, parse_run):
        namespace.func(namespace)
    else:
        with _cli_logging(), tracer.start_as_current_span('logfire._internal.cli'), requests.Session() as session:
            install_connection_policy(session)
            context = get_context()
            session.hooks = {'response': [functools.partial(log_trace_id, context=context)]}
            session.headers.update(context)
            install_logfire_response_hook(session)
            namespace._session = session
            namespace.func(namespace)


@contextmanager
def _cli_logging() -> Generator[None]:
    """Keep CLI HTTP diagnostics without configuring application logging."""
    HOME_LOGFIRE.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(LOGFIRE_LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    cli_loggers = (logger, logging.getLogger('urllib3'))
    previous_levels = [cli_logger.level for cli_logger in cli_loggers]
    try:
        for cli_logger in cli_loggers:
            cli_logger.addHandler(file_handler)
            cli_logger.setLevel(logging.DEBUG)
        yield
    finally:
        for cli_logger, previous_level in zip(cli_loggers, previous_levels):
            cli_logger.removeHandler(file_handler)
            cli_logger.setLevel(previous_level)
        file_handler.close()


def main(args: list[str] | None = None) -> None:
    """Run the CLI."""
    previous_non_interactive = is_non_interactive()
    try:
        _main(args)
    except KeyboardInterrupt:
        sys.stderr.write('User cancelled.\n')
        sys.exit(1)
    except NonInteractiveError as e:
        # The whole point is guidance instead of a traceback, so it must not escape.
        sys.stderr.write(f'{e}\n')
        sys.exit(1)
    finally:
        # Restore rather than clear: `main()` is importable and an application may call it
        # in-process, where leaving the switch set would silently stop prompts in later
        # interactive CLI invocations.
        set_non_interactive(previous_non_interactive)
