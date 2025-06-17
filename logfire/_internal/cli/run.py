import argparse
import importlib
import importlib.metadata
import importlib.util
import os
import runpy
import shutil
import sys

import pkg_resources
from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import logfire

# Map of instrumentation packages to the packages they instrument
OTEL_INSTRUMENTATION_MAP = {
    'opentelemetry-instrumentation-fastapi': 'fastapi',
    'opentelemetry-instrumentation-flask': 'flask',
    'opentelemetry-instrumentation-django': 'django',
    'opentelemetry-instrumentation-requests': 'requests',
    'opentelemetry-instrumentation-httpx': 'httpx',
    'opentelemetry-instrumentation-sqlalchemy': 'sqlalchemy',
    'opentelemetry-instrumentation-asyncpg': 'asyncpg',
    'opentelemetry-instrumentation-psycopg2': 'psycopg2',
    'opentelemetry-instrumentation-redis': 'redis',
    'opentelemetry-instrumentation-celery': 'celery',
    'opentelemetry-instrumentation-aiohttp-client': 'aiohttp',
    'opentelemetry-instrumentation-sqlite3': 'sqlite3',
    'pydantic-ai-slim': 'pydantic_ai',
}

# Friendly names for display
OTEL_FRIENDLY_NAMES = {
    'opentelemetry-instrumentation-fastapi': 'FastAPI Instrumentation',
    'opentelemetry-instrumentation-flask': 'Flask Instrumentation',
    'opentelemetry-instrumentation-django': 'Django Instrumentation',
    'opentelemetry-instrumentation-requests': 'Requests Instrumentation',
    'opentelemetry-instrumentation-httpx': 'HTTPX Instrumentation',
    'opentelemetry-instrumentation-sqlalchemy': 'SQLAlchemy Instrumentation',
    'opentelemetry-instrumentation-asyncpg': 'AsyncPG Instrumentation',
    'opentelemetry-instrumentation-psycopg2': 'Psycopg2 Instrumentation',
    'opentelemetry-instrumentation-redis': 'Redis Instrumentation',
    'opentelemetry-instrumentation-celery': 'Celery Instrumentation',
    'opentelemetry-instrumentation-aiohttp-client': 'AIOHTTP Client Instrumentation',
    'opentelemetry-instrumentation-sqlite3': 'SQLite3 Instrumentation',
}


def parse_run(args: argparse.Namespace) -> None:
    # Initialize Logfire
    logfire.configure()

    # Show OpenTelemetry package information
    print_otel_info()

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


def get_installed_packages() -> set[str]:
    """Get a set of all installed packages."""
    try:
        # Try using importlib.metadata first (newer approach)
        return {dist.metadata['Name'].lower() for dist in importlib.metadata.distributions()}
    except (ImportError, AttributeError):
        # Fall back to pkg_resources
        return {pkg.key for pkg in pkg_resources.working_set}


def is_package_directly_imported(package_name: str) -> bool:
    """Check if a package is directly imported in the application, not just a dependency.

    Uses multiple methods to detect if a package is likely being used:
    1. Check if it's in sys.modules (currently imported)
    2. Check if any submodules are imported
    3. Check if it's an importable module with a valid spec
    """
    try:
        # Method 1: Check if the package or any submodule is already imported
        if package_name in sys.modules:
            return True

        # Check if any submodule of this package is imported
        for module_name in sys.modules:
            if module_name == package_name or module_name.startswith(f'{package_name}.'):
                return True

        # Method 2: Check if the package can be found/imported
        # This helps identify packages that may be used but not yet imported
        spec = importlib.util.find_spec(package_name)
        if spec:
            # For packages that are in our instrumentation map, count them as usable if installed
            if package_name in OTEL_INSTRUMENTATION_MAP.values():
                return True

            # If we can find a spec for the package, it's likely installed and usable
            try:
                # Try to import it as a simple test
                # This is reasonable as we're only checking packages that are already installed
                importlib.import_module(package_name)
                return True
            except ImportError:
                # If import fails, it might be a package that requires special initialization
                pass

        # Note: We intentionally avoid scanning Python files as it can be unreliable
        # and would require parsing code which is beyond the scope of this utility

        return False
    except (ImportError, AttributeError, ValueError, OSError):
        return False


def get_recommended_instrumentation() -> list[tuple[str, str, str]]:
    """Get recommended OpenTelemetry instrumentation packages.

    Returns:
        List of tuples containing:
        - Package name
        - Friendly name
        - Package it instruments
    """
    installed_packages = get_installed_packages()

    # Get all installed otel packages
    installed_otel = {pkg for pkg in OTEL_INSTRUMENTATION_MAP.keys() if pkg in installed_packages}

    # Find packages that we could instrument
    recommendations: list[tuple[str, str, str]] = []

    for otel_pkg, required_pkg in OTEL_INSTRUMENTATION_MAP.items():
        # Skip if this instrumentation is already installed
        if otel_pkg in installed_otel:
            continue

        # Include only if the package it instruments is installed
        if required_pkg in installed_packages:
            # For built-in modules like sqlite3, we can assume they're usable if in sys.modules
            if required_pkg in sys.builtin_module_names or is_package_directly_imported(required_pkg):
                friendly_name = OTEL_FRIENDLY_NAMES.get(otel_pkg, otel_pkg)
                recommendations.append((otel_pkg, friendly_name, required_pkg))

    return recommendations


def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
    return shutil.which('uv') is not None


def get_install_command(package_name: str) -> str:
    """Get the appropriate install command based on available package managers."""
    if is_uv_installed():
        return f'uv add {package_name}'
    return f'pip install {package_name}'


def get_full_install_command(recommendations: list[tuple[str, str, str]]) -> str:
    """Generate a command to install all recommended packages at once."""
    if not recommendations:
        return ''

    package_names = [pkg_name for pkg_name, _, _ in recommendations]

    if is_uv_installed():
        return f'uv add {" ".join(package_names)}'
    else:
        return f'pip install {" ".join(package_names)}'


def get_installed_otel_packages() -> list[str]:
    """Get a list of installed OpenTelemetry instrumentation packages."""
    installed_packages = get_installed_packages()

    # Return installed OpenTelemetry instrumentation packages
    return [pkg for pkg in OTEL_INSTRUMENTATION_MAP.keys() if pkg in installed_packages]


def instrument_packages(installed_otel_packages: list[str]) -> list[str]:
    """Automatically instrument the installed OpenTelemetry packages.

    Returns a list of packages that were successfully instrumented.
    """
    instrumented: list[str] = []

    try:
        # Import logfire first
        import logfire

        # Process all installed OpenTelemetry packages
        for pkg_name in installed_otel_packages:
            if pkg_name in OTEL_INSTRUMENTATION_MAP.keys():
                base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
                # Handle special cases
                if base_pkg == 'aiohttp-client':
                    base_pkg = 'aiohttp'

                import_name = OTEL_INSTRUMENTATION_MAP[pkg_name]
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


def print_otel_info() -> None:
    """Print OpenTelemetry package information using Rich library."""
    console = Console()
    recommendations = get_recommended_instrumentation()

    # Get installed OpenTelemetry packages
    installed_otel_packages = get_installed_otel_packages()

    # Try to instrument installed packages
    instrumented_packages = instrument_packages(installed_otel_packages)

    # Create instrumentation status text for all packages
    instrumentation_text = Text('Your instrumentation checklist:\n\n')

    # Add installed and instrumented packages
    for pkg_name in installed_otel_packages:
        base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
        if base_pkg == 'aiohttp-client':
            base_pkg = 'aiohttp'

        if base_pkg in instrumented_packages:
            instrumentation_text.append(f'✓ {base_pkg} (installed and instrumented)\n', style='green')
        else:
            instrumentation_text.append(
                f'⚠️ {base_pkg} (installed but not automatically instrumented)\n',
                style='yellow',
            )

    # Add recommended packages that are not installed
    for pkg_name, _, instrumented_pkg in recommendations:
        instrumentation_text.append(f'☐ {instrumented_pkg} (need to install {pkg_name})\n', style='grey50')

    # Get full install command for all packages
    full_install_cmd = get_full_install_command(recommendations)

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

    console.print('\n')
    console.print(panel)
    console.print()
