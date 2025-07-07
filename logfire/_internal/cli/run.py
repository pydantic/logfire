from __future__ import annotations as _annotations

import argparse
import importlib
import importlib.metadata
import os
import runpy
import shutil
import sys
import warnings
from typing import cast

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import logfire

STANDARD_LIBRARY_PACKAGES = {'urllib', 'sqlite3'}

# Map of instrumentation packages to the packages they instrument
OTEL_INSTRUMENTATION_MAP = {
    'opentelemetry-instrumentation-aio_pika': 'aio_pika',
    'opentelemetry-instrumentation-aiohttp-client': 'aiohttp_client',
    'opentelemetry-instrumentation-aiohttp-server': 'aiohttp_server',
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
    # Those are not OpenTelemetry packages, but Logfire instruments them.
    'pydantic-ai-slim': 'pydantic_ai',
    'anthropic': 'anthropic',
    'openai': 'openai',
    'openai-agents': 'openai_agents',
}


def parse_run(args: argparse.Namespace) -> None:  # pragma: no cover
    # Initialize Logfire
    logfire.configure()

    summary = cast(bool, args.summary)
    exclude = cast(set[str], args.exclude)

    instrument_pkg_map = {otel_pkg: pkg for otel_pkg, pkg in OTEL_INSTRUMENTATION_MAP.items() if pkg not in exclude}

    installed_pkgs = installed_packages()
    installed_otel_pkgs = {pkg for pkg in instrument_pkg_map.keys() if pkg in installed_pkgs}

    recommendations = recommended_instrumentation(instrument_pkg_map, installed_otel_pkgs, installed_pkgs)

    instrumented_packages = instrument_packages(installed_otel_pkgs, instrument_pkg_map)

    if summary:
        console = Console(file=sys.stderr)
        instrumentation_text = instrumented_packages_text(installed_otel_pkgs, instrumented_packages, installed_pkgs)
        print_otel_summary(
            console=console,
            instrumented_packages_text=instrumentation_text,
            recommendations=recommendations,
        )

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


def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
    return shutil.which('uv') is not None


def instrument_packages(installed_otel_packages: set[str], instrument_pkg_map: dict[str, str]) -> list[str]:
    """Automatically instrument the installed OpenTelemetry packages.

    Returns a list of packages that were successfully instrumented.
    """
    instrumented: list[str] = []

    # Set the environment variables to enable tracing in LangSmith.
    os.environ.setdefault('LANGSMITH_OTEL_ENABLED', 'true')
    os.environ.setdefault('LANGSMITH_TRACING_ENABLED', 'true')

    # Process all installed OpenTelemetry packages
    for otel_pkg_name in installed_otel_packages:
        if pkg_name in instrument_pkg_map.keys():  # pragma: no branch
            base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')

            import_name = instrument_pkg_map[pkg_name]
            instrument_attr = f'instrument_{import_name}'

            try:
                # Try to access the instrumentation function as an attribute of logfire
                if hasattr(logfire, instrument_attr):
                    # The function exists, call it to instrument the package
                    getattr(logfire, instrument_attr)()
            except Exception:  # pragma: no cover
                continue
            instrumented.append(base_pkg)
    return instrumented


def recommended_instrumentation(
    instrument_pkg_map: dict[str, str],
    installed_otel_pkgs: set[str],
    installed_pkgs: set[str],
) -> set[tuple[str, str]]:
    """Get recommended OpenTelemetry instrumentation packages.

    Returns:
        List of tuples containing:
        - Package name
        - Package it instruments
    """
    recommendations: set[tuple[str, str]] = set()

    for otel_pkg, required_pkg in instrument_pkg_map.items():
        # Skip if this instrumentation is already installed
        if otel_pkg in installed_otel_pkgs:
            continue

        # Include only if the package it instruments is installed or in sys.stdlib_module_names
        if required_pkg in installed_pkgs or required_pkg in STANDARD_LIBRARY_PACKAGES:
            recommendations.add((otel_pkg, required_pkg))

    # Special case: if fastapi is installed, don't show starlette instrumentation.
    if 'fastapi' in installed_pkgs:
        recommendations.discard(('opentelemetry-instrumentation-starlette', 'starlette'))
    # Special case: if requests is installed, don't show urllib3 instrumentation.
    if 'requests' in installed_pkgs:
        recommendations.discard(('opentelemetry-instrumentation-urllib3', 'urllib3'))

    return recommendations


def instrumented_packages_text(
    installed_otel_pkgs: set[str], instrumented_packages: list[str], installed_pkgs: set[str]
) -> Text:
    # Filter out special cases for display
    if 'fastapi' in installed_pkgs:
        installed_otel_pkgs.discard('opentelemetry-instrumentation-starlette')  # pragma: no cover
    if 'requests' in installed_pkgs:
        installed_otel_pkgs.discard('opentelemetry-instrumentation-urllib3')  # pragma: no cover

    text = Text('Your instrumentation checklist:\n\n')
    for pkg_name in sorted(installed_otel_pkgs):
        base_pkg = _base_pkg_name(pkg_name)
        if base_pkg in instrumented_packages:
            text.append(f'✓ {base_pkg} (installed and instrumented)\n', style='green')
        else:
            text.append(f'⚠️ {base_pkg} (installed but not automatically instrumented)\n', style='yellow')
    return text


def get_recommendation_texts(recommendations: set[tuple[str, str]]) -> tuple[Text, Text]:
    """Return (recommended_packages_text, install_all_text) as Text objects."""
    sorted_recommendations = sorted(recommendations)
    recommended_text = Text()
    for pkg_name, instrumented_pkg in sorted_recommendations:
        recommended_text.append(f'☐ {instrumented_pkg} (need to install {pkg_name})\n', style='grey50')
    recommended_text.append('\n')

    install_text = Text()
    if recommendations:  # pragma: no branch
        install_text.append('To install all recommended packages at once, run:\n\n')
        install_text.append(_full_install_command(sorted_recommendations), style='bold')
        install_text.append('\n')
    return recommended_text, install_text


def print_otel_summary(
    *,
    console: Console,
    instrumented_packages_text: Text | None = None,
    recommendations: set[tuple[str, str]],
) -> None:
    # Create note about hiding the summary
    hide_note = Text('\nTo hide this summary box, use: ', style='italic')
    hide_note.append('logfire run --no-summary', style='italic bold')
    hide_note.append('.', style='italic')

    # Create a final rule for the bottom section
    footer_rule = Rule(style='blue')

    # Generate recommended and install texts
    recommended_packages_text, install_all_text = get_recommendation_texts(recommendations)

    # We don't want a new line between the two sections.
    if instrumented_packages_text:
        packages_text = instrumented_packages_text + recommended_packages_text  # pragma: no cover
    else:
        packages_text = recommended_packages_text

    # Build group with all elements
    content = Group(
        packages_text,
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

    console.print('\n')
    console.print(panel)
    console.print()


def _base_pkg_name(pkg_name: str) -> str:
    base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
    if base_pkg == 'aiohttp-client':
        base_pkg = 'aiohttp'  # pragma: no cover
    return base_pkg


def installed_packages() -> set[str]:  # pragma: no cover
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
        return ''  # pragma: no cover

    package_names = [pkg_name for pkg_name, _ in recommendations]

    # TODO(Marcelo): We should customize this. If the user uses poetry, they'd use `poetry add`.
    # Something like `--install-format` with options like `requirements`, `poetry`, `uv`, `pip`.
    if is_uv_installed():
        return f'uv add {" ".join(package_names)}'
    else:
        return f'pip install {" ".join(package_names)}'  # pragma: no cover
