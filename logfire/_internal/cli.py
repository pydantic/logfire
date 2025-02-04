"""The CLI for Pydantic Logfire."""

from __future__ import annotations

import argparse
import functools
import importlib
import importlib.metadata
import importlib.util
import logging
import platform
import sys
import warnings
import webbrowser
from operator import itemgetter
from pathlib import Path
from typing import Any, Sequence, cast
from urllib.parse import urlparse

import requests
from opentelemetry import trace

from logfire.exceptions import LogfireConfigError
from logfire.propagate import ContextCarrier, get_context

from ..version import VERSION
from .auth import DEFAULT_FILE, HOME_LOGFIRE, DefaultFile, is_logged_in, poll_for_token, request_device_code
from .config import LogfireCredentials
from .config_params import ParamManager
from .constants import LOGFIRE_BASE_URL
from .tracer import SDKTracerProvider
from .utils import read_toml_file

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


def parse_whoami(args: argparse.Namespace) -> None:
    """Show user authenticated username and the URL to your Logfire project."""
    data_dir = Path(args.data_dir)
    param_manager = ParamManager.create(data_dir)
    base_url = param_manager.load_param('base_url', args.logfire_url)
    token = param_manager.load_param('token')

    if token:
        credentials = LogfireCredentials.from_token(token, args._session, base_url)
        if credentials:
            credentials.print_token_summary()
            return

    current_user = LogfireCredentials.get_current_user(session=args._session, logfire_api_url=base_url)
    if current_user is None:
        sys.stderr.write('Not logged in. Run `logfire auth` to log in.\n')
    else:
        username = current_user['name']
        sys.stderr.write(f'Logged in as: {username}\n')
    credentials = LogfireCredentials.load_creds_file(data_dir)
    if credentials is None:
        sys.stderr.write(f'No Logfire credentials found in {data_dir.resolve()}\n')
        sys.exit(1)
    else:
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

    files_to_display = '\n'.join([str(file) for file in files_to_delete if file.exists()])
    confirm = input(f'The following files will be deleted:\n{files_to_display}\nAre you sure? [N/y]')
    if confirm.lower() in ('yes', 'y'):
        for file in files_to_delete:
            file.unlink(missing_ok=True)
        sys.stderr.write('Cleaned Logfire data.\n')
    else:
        sys.stderr.write('Clean aborted.\n')


# TODO(Marcelo): Automatically check if this list should be updated.
# NOTE: List of packages from https://github.com/open-telemetry/opentelemetry-python-contrib/tree/main/instrumentation.
STANDARD_LIBRARY_PACKAGES = {'urllib', 'sqlite3'}
OTEL_PACKAGES: set[str] = {
    *STANDARD_LIBRARY_PACKAGES,
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
    'psycopg',
    'psycopg2',
    'pymemcache',
    'pymongo',
    'pymysql',
    'pyramid',
    'remoulade',
    'requests',
    'sqlalchemy',
    'starlette',
    'tornado',
    'tortoise_orm',
    'urllib3',
}
OTEL_PACKAGE_LINK = {'aiohttp': 'aiohttp-client', 'tortoise_orm': 'tortoiseorm', 'scikit-learn': 'sklearn'}


def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend packages that might be useful."""
    packages_to_ignore: set[str] = set(args.ignore) if args.ignore else set()
    packages_to_inspect = OTEL_PACKAGES - packages_to_ignore

    # Ignore warnings from packages that we don't control.
    warnings.simplefilter('ignore', category=UserWarning)

    packages: dict[str, str] = {}
    for name in packages_to_inspect:
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
    if packages.get('urllib3') and packages.get('requests'):
        del packages['urllib3']

    # fmt: off
    sys.stderr.write('The following packages from your environment have an OpenTelemetry instrumentation that is not installed:\n')
    sys.stderr.write('\n')
    # fmt: on

    rows: list[list[str]] = []
    for name, otel_package in sorted(packages.items()):
        package_name = otel_package.replace('.', '-')
        otel_package_name = f'opentelemetry-instrumentation-{package_name}'
        rows.append([name, otel_package_name])
    sys.stderr.write(_pretty_table(['Package', 'OpenTelemetry instrumentation package'], rows))

    if packages:  # pragma: no branch
        otel_packages_to_install = ' '.join(
            f'opentelemetry-instrumentation-{pkg.replace(".", "-")}' for pkg in packages.values()
        )
        install_command = f'pip install {otel_packages_to_install}'
        sys.stderr.writelines(
            (
                '\nTo install these packages, run:\n',
                f'\n$ {install_command}\n',
                f'\nFor further information, visit {INTEGRATIONS_DOCS_URL}\n',
            )
        )


def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This will authenticate your machine with Logfire and store the credentials.
    """
    logfire_url = cast(str, args.logfire_url)

    if DEFAULT_FILE.is_file():
        data = cast(DefaultFile, read_toml_file(DEFAULT_FILE))
        if is_logged_in(data, logfire_url):  # pragma: no branch
            sys.stderr.write(f'You are already logged in. (Your credentials are stored in {DEFAULT_FILE})\n')
            return
    else:
        data: DefaultFile = {'tokens': {}}

    sys.stderr.writelines(
        (
            '\n',
            'Welcome to Logfire! 🔥\n',
            'Before you can send data to Logfire, we need to authenticate you.\n',
            '\n',
        )
    )

    device_code, frontend_auth_url = request_device_code(args._session, logfire_url)
    frontend_host = urlparse(frontend_auth_url).netloc
    input(f'Press Enter to open {frontend_host} in your browser...')
    try:
        webbrowser.open(frontend_auth_url, new=2)
    except webbrowser.Error:
        pass
    sys.stderr.writelines(
        (
            f"Please open {frontend_auth_url} in your browser to authenticate if it hasn't already.\n",
            'Waiting for you to authenticate with Logfire...\n',
        )
    )

    data['tokens'][logfire_url] = poll_for_token(args._session, device_code, logfire_url)
    sys.stderr.write('Successfully authenticated!\n')

    # There's no standard library package to write TOML files, so we'll write it manually.
    with DEFAULT_FILE.open('w') as f:
        for url, info in data['tokens'].items():
            f.write(f'[tokens."{url}"]\n')
            f.write(f'token = "{info["token"]}"\n')
            f.write(f'expiration = "{info["expiration"]}"\n')

    sys.stderr.write(f'\nYour Logfire credentials are stored in {DEFAULT_FILE}\n')


def parse_list_projects(args: argparse.Namespace) -> None:
    """List user projects."""
    logfire_url = args.logfire_url
    projects = LogfireCredentials.get_user_projects(session=args._session, logfire_api_url=logfire_url)
    if projects:
        sys.stderr.write(
            _pretty_table(
                ['Organization', 'Project'],
                [
                    [project['organization_name'], project['project_name']]
                    for project in sorted(projects, key=itemgetter('organization_name', 'project_name'))
                ],
            )
        )
    else:
        sys.stderr.write(
            'No projects found for the current user. You can create a new project with `logfire projects new`\n'
        )


def _write_credentials(project_info: dict[str, Any], data_dir: Path, logfire_api_url: str) -> LogfireCredentials:
    try:
        credentials = LogfireCredentials(**project_info, logfire_api_url=logfire_api_url)
        credentials.write_creds_file(data_dir)
        return credentials
    except TypeError as e:
        raise LogfireConfigError(f'Invalid credentials, when initializing project: {e}') from e


def parse_create_new_project(args: argparse.Namespace) -> None:
    """Create a new project."""
    data_dir = Path(args.data_dir)
    logfire_url = args.logfire_url
    project_name = args.project_name
    organization = args.org
    default_organization = args.default_org
    project_info = LogfireCredentials.create_new_project(
        session=args._session,
        logfire_api_url=logfire_url,
        organization=organization,
        default_organization=default_organization,
        project_name=project_name,
    )
    credentials = _write_credentials(project_info, data_dir, logfire_url)
    sys.stderr.write(f'Project created successfully. You will be able to view it at: {credentials.project_url}\n')


def parse_use_project(args: argparse.Namespace) -> None:
    """Use an existing project."""
    data_dir = Path(args.data_dir)
    logfire_url = args.logfire_url
    project_name = args.project_name
    organization = args.org

    projects = LogfireCredentials.get_user_projects(session=args._session, logfire_api_url=logfire_url)
    project_info = LogfireCredentials.use_existing_project(
        session=args._session,
        logfire_api_url=logfire_url,
        projects=projects,
        organization=organization,
        project_name=project_name,
    )
    if project_info:
        credentials = _write_credentials(project_info, data_dir, logfire_url)
        sys.stderr.write(
            f'Project configured successfully. You will be able to view it at: {credentials.project_url}\n'
        )


def logfire_info() -> str:
    """Show versions of logfire, OS and related packages."""
    import importlib.metadata as importlib_metadata

    # get data about packages that are closely related to logfire
    package_names = {
        # use by otel to send data
        'requests': 1,
        # custom integration
        'pydantic': 2,
        # otel integration is customed
        'fastapi': 3,
        # custom integration
        'openai': 4,
        # dependencies of otel
        'protobuf': 5,
        # dependencies
        'rich': 6,
        # dependencies
        'typing-extensions': 7,
        # dependencies
        'tomli': 8,
        # dependencies
        'executing': 9,
    }
    otel_index = max(package_names.values(), default=0) + 1
    related_packages: list[tuple[int, str, str]] = []

    for dist in importlib_metadata.distributions():
        metadata = dist.metadata
        name = metadata.get('Name', '')
        version = metadata.get('Version', 'UNKNOWN')
        index = package_names.get(name)
        if index is not None:
            related_packages.append((index, name, version))
        if name.startswith('opentelemetry'):
            related_packages.append((otel_index, name, version))

    toml_lines: tuple[str, ...] = (
        f'logfire="{VERSION}"',
        f'platform="{platform.platform()}"',
        f'python="{sys.version}"',
        '[related_packages]',
        *(f'{name}="{version}"' for _, name, version in sorted(related_packages)),
    )
    return '\n'.join(toml_lines) + '\n'


def parse_info(_args: argparse.Namespace) -> None:
    """Show versions of logfire, OS and related packages."""
    sys.stderr.writelines(logfire_info())


def _pretty_table(header: list[str], rows: list[list[str]]):
    rows = [[' ' + first, *rest] for first, *rest in [header] + rows]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = ['   | '.join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows]
    header_line = '---|-'.join('-' * width for width in widths)
    lines.insert(1, header_line)
    return '\n'.join(lines) + '\n'


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


def _main(args: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog='logfire',
        description='The CLI for Pydantic Logfire.',
        epilog='See https://logfire.pydantic.dev/docs/reference/cli/ for more detailed documentation.',
    )

    parser.add_argument('--version', action='store_true', help='show the version and exit')
    global_opts = parser.add_argument_group(title='global options')
    global_opts.add_argument('--logfire-url', default=LOGFIRE_BASE_URL, help=argparse.SUPPRESS)
    parser.set_defaults(func=lambda _: parser.print_help())  # type: ignore
    subparsers = parser.add_subparsers(title='commands', metavar='')

    # NOTE(DavidM): Let's try to keep the commands listed in alphabetical order if we can
    cmd_auth = subparsers.add_parser('auth', help=parse_auth.__doc__.split('\n', 1)[0], description=parse_auth.__doc__)  # type: ignore
    cmd_auth.set_defaults(func=parse_auth)

    cmd_clean = subparsers.add_parser('clean', help=parse_clean.__doc__)
    cmd_clean.set_defaults(func=parse_clean)
    cmd_clean.add_argument('--data-dir', default='.logfire')
    cmd_clean.add_argument('--logs', action='store_true', default=False, help='remove the Logfire logs')

    cmd_inspect = subparsers.add_parser('inspect', help=parse_inspect.__doc__)
    cmd_inspect.set_defaults(func=parse_inspect)
    cmd_inspect.add_argument('--ignore', action=SplitArgs, help='ignore a package')

    cmd_whoami = subparsers.add_parser('whoami', help=parse_whoami.__doc__)
    cmd_whoami.set_defaults(func=parse_whoami)
    cmd_whoami.add_argument('--data-dir', default='.logfire')

    cmd_projects = subparsers.add_parser('projects', help='Project management for Logfire.')
    cmd_projects.set_defaults(func=lambda _: cmd_projects.print_help())  # type: ignore
    projects_subparsers = cmd_projects.add_subparsers()

    cmd_projects_list = projects_subparsers.add_parser('list', help='list projects')
    cmd_projects_list.set_defaults(func=parse_list_projects)

    cmd_projects_new = projects_subparsers.add_parser('new', help='create a new project')
    cmd_projects_new.add_argument('project_name', nargs='?', help='project name')
    cmd_projects_new.add_argument('--data-dir', default='.logfire')
    cmd_projects_new.add_argument('--org', help='project organization')
    cmd_projects_new.add_argument(
        '--default-org', action='store_true', help='whether to create project under user default organization'
    )
    cmd_projects_new.set_defaults(func=parse_create_new_project)

    cmd_projects_use = projects_subparsers.add_parser('use', help='use a project')
    cmd_projects_use.add_argument('project_name', nargs='?', help='project name')
    cmd_projects_use.add_argument('--org', help='project organization')
    cmd_projects_use.add_argument('--data-dir', default='.logfire')
    cmd_projects_use.set_defaults(func=parse_use_project)

    cmd_info = subparsers.add_parser('info', help=parse_info.__doc__)
    cmd_info.set_defaults(func=parse_info)

    namespace = parser.parse_args(args)

    trace.set_tracer_provider(tracer_provider=SDKTracerProvider())
    tracer = trace.get_tracer(__name__)

    def log_trace_id(response: requests.Response, context: ContextCarrier, *args: Any, **kwargs: Any) -> None:
        logger.debug('context=%s url=%s', context, response.url)

    with tracer.start_as_current_span('logfire._internal.cli'):
        if namespace.version:
            version_callback()
        elif namespace.func == parse_info:
            namespace.func(namespace)
        else:
            with requests.Session() as session:
                context = get_context()
                session.hooks = {'response': functools.partial(log_trace_id, context=context)}
                session.headers.update(context)
                namespace._session = session
                namespace.func(namespace)


def main(args: list[str] | None = None) -> None:
    """Run the CLI."""
    HOME_LOGFIRE.mkdir(exist_ok=True)

    file_handler = logging.FileHandler(LOGFIRE_LOG_FILE)
    file_handler.setLevel(logging.DEBUG)
    logging.basicConfig(handlers=[file_handler], level=logging.DEBUG)

    try:
        _main(args)
    except KeyboardInterrupt:
        sys.stderr.write('User cancelled.\n')
        sys.exit(1)
    finally:
        file_handler.close()
