from __future__ import annotations as _annotations

import argparse
import ast
import importlib
import importlib.metadata
import importlib.util
import os
import runpy
import shutil
import sys
import warnings
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

from rich.box import ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

import logfire

# Packages that are always importable (stdlib or transitive deps of opentelemetry)
# but should only be suggested for instrumentation if the user's code actually imports them.
ALWAYS_AVAILABLE_PACKAGES = {'urllib', 'sqlite3', 'requests'}

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
    'opentelemetry-instrumentation-psycopg2': 'psycopg',
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


@dataclass
class InstrumentationContext:
    instrument_pkg_map: dict[str, str]
    installed_pkgs: set[str]
    installed_otel_pkgs: set[str]
    recommendations: set[tuple[str, str]]


def parse_run(args: argparse.Namespace) -> None:
    logfire.configure()

    summary = cast(bool, args.summary)
    exclude = cast(set[str], args.exclude)

    # Determine the script path or module name for import analysis
    script_and_args = args.script_and_args
    module_name = args.module
    script_path = script_and_args[0] if script_and_args and not module_name else None

    ctx = collect_instrumentation_context(exclude, script_path=script_path, module_name=module_name)

    instrumented_packages = instrument_packages(ctx.installed_otel_pkgs, ctx.instrument_pkg_map)

    if summary:
        console = Console(file=sys.stderr)
        instrumentation_text = instrumented_packages_text(
            ctx.installed_otel_pkgs, instrumented_packages, ctx.installed_pkgs
        )
        print_otel_summary(
            console=console, instrumented_packages_text=instrumentation_text, recommendations=ctx.recommendations
        )

    if module_name:
        module_args = script_and_args

        # Re-insert cwd for the actual module execution so that `python -m myapp`
        # semantics are preserved.  This intentionally happens AFTER
        # collect_instrumentation_context (and therefore after instrument_packages),
        # so local modules in cwd cannot shadow logfire's own instrumentation imports.
        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        # We need to change the `sys.argv` to make sure the module sees the right CLI args
        # e.g. in case of `logfire run -m uvicorn main:app --reload`, the application will see
        # ["<uvicorn.__main__.py>", "main:app", "--reload"].
        # alter_sys=True replaces the first element of sys.argv with the module path.
        # So we can really put anything there. That's why `-m {module_name}` is a single string.
        with alter_sys_argv([f'-m {module_name}'] + module_args, f'python -m {module_name} {" ".join(module_args)}'):
            runpy.run_module(module_name, run_name='__main__', alter_sys=True)
    elif script_and_args:
        # Script mode
        run_script_path = script_and_args[0]

        # Make sure the script directory is in sys.path
        script_dir = os.path.dirname(os.path.abspath(run_script_path))
        if script_dir not in sys.path:  # pragma: no branch
            sys.path.insert(0, script_dir)

        with alter_sys_argv(script_and_args, f'python {" ".join(script_and_args)}'):
            runpy.run_path(run_script_path, run_name='__main__')
    else:
        print('Usage: logfire run [-m MODULE] [args...] OR logfire run SCRIPT [args...]')
        sys.exit(1)


@contextmanager
def alter_sys_argv(argv: list[str], cmd: str) -> Generator[None, None, None]:
    orig_argv = sys.argv.copy()
    sys.argv = argv
    try:
        logfire.info('Running command: {cmd_str}', cmd_str=cmd)
        yield
    finally:
        sys.argv = orig_argv


def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
    return shutil.which('uv') is not None


def instrument_packages(installed_otel_packages: set[str], instrument_pkg_map: dict[str, str]) -> list[str]:
    """Call every `logfire.instrument_x()` we can based on what's installed.

    Returns a list of packages that were successfully instrumented.
    """
    instrumented: list[str] = []

    # Set the environment variables to enable tracing in LangSmith.
    os.environ.setdefault('LANGSMITH_OTEL_ENABLED', 'true')
    os.environ.setdefault('LANGSMITH_TRACING_ENABLED', 'true')

    # Process all installed OpenTelemetry packages
    for otel_pkg_name in installed_otel_packages:
        base_pkg = otel_pkg_name.replace('opentelemetry-instrumentation-', '')

        import_name = instrument_pkg_map[otel_pkg_name]
        try:
            instrument_package(import_name)
        except Exception:
            continue
        instrumented.append(base_pkg)
    return instrumented


def instrument_package(import_name: str):
    instrument_attr = f'instrument_{import_name}'
    getattr(logfire, instrument_attr)()


def find_recommended_instrumentations_to_install(
    instrument_pkg_map: dict[str, str],
    installed_otel_pkgs: set[str],
    installed_pkgs: set[str],
    script_imports: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Determine which OpenTelemetry instrumentation packages are recommended for installation.

    Args:
        instrument_pkg_map: Mapping of instrumentation package names to the packages they instrument.
        installed_otel_pkgs: Set of already installed instrumentation package names.
        installed_pkgs: Set of all installed package names.
        script_imports: Set of top-level module names imported by the user's script/module.
            Used to filter out false suggestions for packages that are always available
            (stdlib or transitive deps) but not actually used.

    Returns:
        Set of tuples where each tuple is (instrumentation_package, target_package) that
            is recommended for installation.
    """
    recommendations: set[tuple[str, str]] = set()

    for otel_pkg, required_pkg in instrument_pkg_map.items():
        # Skip if this instrumentation is already installed
        if otel_pkg in installed_otel_pkgs:
            continue

        # For packages that are always importable (stdlib or transitive deps of otel),
        # only recommend if the user's code actually imports them.
        if required_pkg in ALWAYS_AVAILABLE_PACKAGES:
            if script_imports is not None and required_pkg not in script_imports:
                continue
            recommendations.add((otel_pkg, required_pkg))
            continue

        # For other packages, recommend if they are installed
        if required_pkg in installed_pkgs:
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
        installed_otel_pkgs.discard('opentelemetry-instrumentation-starlette')
    if 'requests' in installed_pkgs:
        installed_otel_pkgs.discard('opentelemetry-instrumentation-urllib3')

    text = Text('Your instrumentation checklist:\n\n')
    for pkg_name in sorted(installed_otel_pkgs):
        base_pkg = pkg_name.replace('opentelemetry-instrumentation-', '')
        if base_pkg in instrumented_packages:
            text.append(f'✓ {base_pkg} (installed and instrumented)\n', style='green')
        else:
            # This is the case on OTel packages that don't have a logfire method, and methods that need the app
            # like Starlette, FastAPI and Flask.
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


def installed_packages() -> set[str]:
    """Get a set of all installed packages."""
    try:
        # Try using importlib.metadata first (it's available in Python >=3.10)
        return {dist.metadata['Name'].lower() for dist in importlib.metadata.distributions()}
    except (ImportError, AttributeError):  # pragma: no cover
        # Fall back to pkg_resources
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=UserWarning)
            import pkg_resources  # pyright: ignore[reportMissingImports]

            return {pkg.key for pkg in pkg_resources.working_set}  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]


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


def find_script_imports(script_path: str | None = None, module_name: str | None = None) -> set[str] | None:
    """Extract top-level import names from a script file or module.

    Uses AST parsing to find all `import X` and `from X import ...` statements,
    returning the set of top-level module names (e.g. 'requests', 'sqlite3').

    Returns None if the source cannot be determined (e.g. no script or module provided),
    which signals that filtering should be skipped (all packages recommended as before).
    """
    source: str | None = None

    if script_path:
        try:
            with open(script_path) as f:
                source = f.read()
        except OSError:
            return None
    elif module_name:
        # Temporarily insert cwd into sys.path so that find_spec can locate local
        # modules (e.g. `logfire run -m myapp`). The insertion is scoped with
        # try/finally so it is removed immediately after the analysis pass and does
        # NOT persist into the instrumentation-import phase, preventing local modules
        # from shadowing logfire's own dependencies.
        cwd = os.getcwd()
        cwd_inserted = False
        if cwd not in sys.path:
            sys.path.insert(0, cwd)
            cwd_inserted = True
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin:
                origin = spec.origin
                # For packages, runtime executes __main__.py (via runpy.run_module),
                # not __init__.py. Analyze __main__.py if it exists so that
                # recommendations match what actually runs.
                if origin.endswith('__init__.py'):
                    main_py = origin.replace('__init__.py', '__main__.py')
                    if os.path.isfile(main_py):
                        origin = main_py
                with open(origin) as f:
                    source = f.read()
        except (ModuleNotFoundError, ValueError, OSError):
            return None
        finally:
            if cwd_inserted:
                try:
                    sys.path.remove(cwd)
                except ValueError:
                    pass

    if source is None:
        return None

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # 'import urllib.request' -> top-level is 'urllib'
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports


def collect_instrumentation_context(
    exclude: set[str],
    script_path: str | None = None,
    module_name: str | None = None,
) -> InstrumentationContext:
    """Collects all relevant context for instrumentation and recommendations."""
    instrument_pkg_map = {otel_pkg: pkg for otel_pkg, pkg in OTEL_INSTRUMENTATION_MAP.items() if pkg not in exclude}
    installed_pkgs = installed_packages()
    installed_otel_pkgs = {pkg for pkg in instrument_pkg_map.keys() if pkg in installed_pkgs}
    script_imports = find_script_imports(script_path=script_path, module_name=module_name)
    recommendations = find_recommended_instrumentations_to_install(
        instrument_pkg_map, installed_otel_pkgs, installed_pkgs, script_imports=script_imports
    )
    return InstrumentationContext(
        instrument_pkg_map=instrument_pkg_map,
        installed_pkgs=installed_pkgs,
        installed_otel_pkgs=installed_otel_pkgs,
        recommendations=recommendations,
    )
