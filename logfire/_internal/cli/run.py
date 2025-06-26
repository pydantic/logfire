from __future__ import annotations as _annotations

import argparse
import importlib
import importlib.metadata
import os
import runpy
import shutil
import sys
import warnings
from collections.abc import Iterable
from typing import cast

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import logfire

# Map of instrumentation packages to the packages they instrument
OTEL_INSTRUMENTATION_MAP = {
    'opentelemetry-instrumentation-aio_pika': 'aio_pika',
    'opentelemetry-instrumentation-aiohttp-client': 'aiohttp',
    'opentelemetry-instrumentation-aiopg': 'aiopg',
    'opentelemetry-instrumentation-asyncpg': 'asyncpg',
    'opentelemetry-instrumentation-boto': 'boto',
    'opentelemetry-instrumentation-botocore': 'botocore',
    'opentelemetry-instrumentation-celery': 'celery',
    'opentelemetry-instrumentation-confluent-kafka': 'confluent_kafka',
    'opentelemetry-instrumentation-django': 'django',
    'opentelemetry-instrumentation-elasticsearch': 'elasticsearch',
    'opentelemetry-instrumentation-falcon': 'falcon',
    'opentelemetry-instrumentation-fastapi': 'fastapi',
    'opentelemetry-instrumentation-flask': 'flask',
    'opentelemetry-instrumentation-grpc': 'grpc',
    'opentelemetry-instrumentation-httpx': 'httpx',
    'opentelemetry-instrumentation-jinja2': 'jinja2',
    'opentelemetry-instrumentation-kafka-python': 'kafka_python',
    'opentelemetry-instrumentation-mysql': 'mysql',
    'opentelemetry-instrumentation-mysqlclient': 'mysqlclient',
    'opentelemetry-instrumentation-pika': 'pika',
    'opentelemetry-instrumentation-psycopg': 'psycopg',
    'opentelemetry-instrumentation-psycopg2': 'psycopg2',
    'opentelemetry-instrumentation-pymemcache': 'pymemcache',
    'opentelemetry-instrumentation-pymongo': 'pymongo',
    'opentelemetry-instrumentation-pymysql': 'pymysql',
    'opentelemetry-instrumentation-pyramid': 'pyramid',
    'opentelemetry-instrumentation-redis': 'redis',
    'opentelemetry-instrumentation-remoulade': 'remoulade',
    'opentelemetry-instrumentation-requests': 'requests',
    'opentelemetry-instrumentation-sqlalchemy': 'sqlalchemy',
    'opentelemetry-instrumentation-sqlite3': 'sqlite3',
    'opentelemetry-instrumentation-starlette': 'starlette',
    'opentelemetry-instrumentation-tornado': 'tornado',
    'opentelemetry-instrumentation-tortoiseorm': 'tortoise_orm',
    'opentelemetry-instrumentation-urllib': 'urllib',
    'opentelemetry-instrumentation-urllib3': 'urllib3',
    'pydantic-ai-slim': 'pydantic_ai',
}


def parse_run(args: argparse.Namespace) -> None:
    # Initialize Logfire
    logfire.configure()

    summary = cast(bool, args.summary)
    exclude = cast('set[str]', args.exclude)

    # Show the instrumentation summary and perform the instrumentation.
    instrument(exclude=exclude, summary=summary)

    # Get arguments from the args parameter
    if hasattr(args, 'module') and args.module:
        # Module mode
        module_name = args.module
        module_args = getattr(args, 'args', [])

        cmd_str = f'python -m {module_name} {" ".join(module_args)}'

        # Save original arguments
        orig_argv = sys.argv.copy()

        try:
            # Set up args for the module
            sys.argv = [f'-m {module_name}'] + module_args

            logfire.info(f'Running command: {cmd_str}')

            # Run the module
            runpy.run_module(module_name, run_name='__main__', alter_sys=True)
        finally:
            # Restore original arguments
            sys.argv = orig_argv
    elif hasattr(args, 'script') and args.script:
        # Script mode
        script_path = args.script
        script_args = getattr(args, 'args', [])

        cmd_str = f'python {script_path} {" ".join(script_args)}'

        # Make sure the script directory is in sys.path
        script_dir = os.path.dirname(os.path.abspath(script_path))
        if script_dir not in sys.path:
            sys.path.insert(0, script_dir)

        # Save original arguments
        orig_argv = sys.argv.copy()

        try:
            # Set up args for the script
            sys.argv = [script_path] + script_args

            logfire.info(f'Running command: {cmd_str}')

            # Run the script
            runpy.run_path(script_path, run_name='__main__')
        finally:
            # Restore original arguments
            sys.argv = orig_argv
    else:
        print('Usage: logfire run [-m MODULE] [args...] OR logfire run SCRIPT [args...]')
        sys.exit(1)


def get_recommended_instrumentation(
    instrumentation_packages_map: dict[str, str],
    installed_otel_packages: list[str],
    installed_packages: set[str],
) -> list[tuple[str, str]]:
    """Get recommended OpenTelemetry instrumentation packages.

    Returns:
        List of tuples containing:
        - Package name
        - Package it instruments
    """
    # Find packages that we could instrument
    recommendations: list[tuple[str, str]] = []

    for otel_pkg, required_pkg in instrumentation_packages_map.items():
        # Skip if this instrumentation is already installed
        if otel_pkg in installed_otel_packages:
            continue

        # Include only if the package it instruments is installed or in sys.stdlib_module_names
        if required_pkg in installed_packages or required_pkg in sys.stdlib_module_names:
            recommendations.append((otel_pkg, required_pkg))

    return recommendations


def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
    return shutil.which('uv') is not None


def instrument_packages(installed_otel_packages: list[str], instrumentation_packages_map: dict[str, str]) -> list[str]:
    """Automatically instrument the installed OpenTelemetry packages.

    Returns a list of packages that were successfully instrumented.
    """
    instrumented: list[str] = []

    try:
        # Import logfire first
        import logfire

        # Process all installed OpenTelemetry packages
        for pkg_name in installed_otel_packages:
            if pkg_name in instrumentation_packages_map.keys():
                base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
                # Handle special cases
                if base_pkg == 'aiohttp-client':
                    base_pkg = 'aiohttp'

                import_name = instrumentation_packages_map[pkg_name]
                instrument_attr = f'instrument_{import_name}'

                try:
                    # Try to access the instrumentation function as an attribute of logfire
                    if hasattr(logfire, instrument_attr):
                        # The function exists, call it to instrument the package
                        getattr(logfire, instrument_attr)()
                        instrumented.append(base_pkg)
                except Exception:
                    continue
    except ImportError:
        # logfire is not installed
        pass

    return instrumented


def instrument(exclude: Iterable[str] = (), summary: bool = True) -> None:
    """Print OpenTelemetry package information using Rich library."""
    console = Console(file=sys.stderr)

    # Get the packages that we want to consider for instrumentation.
    instrumentation_packages_map = {
        otel_package: package for otel_package, package in OTEL_INSTRUMENTATION_MAP.items() if package not in exclude
    }

    installed_packages = _installed_packages()
    installed_otel_packages = [pkg for pkg in instrumentation_packages_map.keys() if pkg in installed_packages]

    recommendations = get_recommended_instrumentation(
        instrumentation_packages_map, installed_otel_packages, installed_packages
    )
    instrumented_packages = instrument_packages(installed_otel_packages, instrumentation_packages_map)

    # Create instrumentation status text for all packages
    instrumentation_text = Text('Your instrumentation checklist:\n\n')

    # Add installed and instrumented packages
    for pkg_name in installed_otel_packages:
        base_pkg = _base_pkg_name(pkg_name)

        if base_pkg in instrumented_packages:
            instrumentation_text.append(f'✓ {base_pkg} (installed and instrumented)\n', style='green')
        else:
            instrumentation_text.append(
                f'⚠️ {base_pkg} (installed but not automatically instrumented)\n', style='yellow'
            )

    # Add recommended packages that are not installed
    for pkg_name, instrumented_pkg in recommendations:
        instrumentation_text.append(f'☐ {instrumented_pkg} (need to install {pkg_name})\n', style='grey50')

    # Get full install command for all packages
    full_install_cmd = _full_install_command(recommendations)

    # Create section for installing all packages at once
    install_all_text = Text()
    if recommendations:
        install_all_text.append('To install all recommended packages at once, run:\n\n')
        install_all_text.append(full_install_cmd, style='bold')
        install_all_text.append('\n')

    # Create note about hiding the summary
    hide_note = Text('\nTo hide this summary box, use: ', style='italic')
    hide_note.append('logfire run --no-summary', style='italic bold')
    hide_note.append('.', style='italic')

    # Create a final rule for the bottom section
    footer_rule = Rule(style='blue')

    # Build group with all elements
    content = Group(
        # system_info,
        # otel_title,
        instrumentation_text,
        install_all_text,
        footer_rule,
        hide_note,
    )

    # Create a panel containing the content with a rounded box border
    panel = Panel(
        content,
        title='[bold blue]Logfire Summary[/bold blue]',
        border_style='blue',
        box=ROUNDED,
        padding=(1, 2),
    )

    if summary:
        console.print('\n')
        console.print(panel)
        console.print()


def _base_pkg_name(pkg_name: str) -> str:
    base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
    if base_pkg == 'aiohttp-client':
        base_pkg = 'aiohttp'
    return base_pkg


def _installed_packages() -> set[str]:
    """Get a set of all installed packages."""
    try:
        # Try using importlib.metadata first (it's available in Python >=3.10)
        return {dist.metadata['Name'].lower() for dist in importlib.metadata.distributions()}
    except (ImportError, AttributeError):
        # Fall back to pkg_resources
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=UserWarning)
            import pkg_resources

            return {pkg.key for pkg in pkg_resources.working_set}


def _full_install_command(recommendations: list[tuple[str, str]]) -> str:
    """Generate a command to install all recommended packages at once."""
    if not recommendations:
        return ''

    package_names = [pkg_name for pkg_name, _ in recommendations]

    # TODO(Marcelo): We should customize this. If the user uses poetry, they'd use `poetry add`.
    # Something like `--install-format` with options like `requirements`, `poetry`, `uv`, `pip`.
    if is_uv_installed():
        return f'uv add {" ".join(package_names)}'
    else:
        return f'pip install {" ".join(package_names)}'
