import argparse
from _typeshed import Incomplete
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from rich.console import Console
from rich.text import Text

ALWAYS_AVAILABLE_PACKAGES: Incomplete
OTEL_INSTRUMENTATION_MAP: Incomplete

@dataclass
class InstrumentationContext:
    instrument_pkg_map: dict[str, str]
    installed_pkgs: set[str]
    installed_otel_pkgs: set[str]
    recommendations: set[tuple[str, str]]

def parse_run(args: argparse.Namespace) -> None: ...
@contextmanager
def alter_sys_argv(argv: list[str], cmd: str) -> Generator[None, None, None]: ...
def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
def instrument_packages(installed_otel_packages: set[str], instrument_pkg_map: dict[str, str]) -> list[str]:
    """Call every `logfire.instrument_x()` we can based on what's installed.

    Returns a list of packages that were successfully instrumented.
    """
def instrument_package(import_name: str): ...
def find_recommended_instrumentations_to_install(instrument_pkg_map: dict[str, str], installed_otel_pkgs: set[str], installed_pkgs: set[str], script_imports: set[str] | None = None) -> set[tuple[str, str]]:
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
def instrumented_packages_text(installed_otel_pkgs: set[str], instrumented_packages: list[str], installed_pkgs: set[str]) -> Text: ...
def get_recommendation_texts(recommendations: set[tuple[str, str]]) -> tuple[Text, Text]:
    """Return (recommended_packages_text, install_all_text) as Text objects."""
def print_otel_summary(*, console: Console, instrumented_packages_text: Text | None = None, recommendations: set[tuple[str, str]]) -> None: ...
def installed_packages() -> set[str]:
    """Get a set of all installed packages."""
def find_script_imports(script_path: str | None = None, module_name: str | None = None) -> set[str] | None:
    """Extract top-level import names from a script file or module.

    Uses AST parsing to find all `import X` and `from X import ...` statements,
    returning the set of top-level module names (e.g. 'requests', 'sqlite3').

    Returns None if the source cannot be determined (e.g. no script or module provided),
    which signals that filtering should be skipped (all packages recommended as before).
    """
def collect_instrumentation_context(exclude: set[str], script_path: str | None = None, module_name: str | None = None) -> InstrumentationContext:
    """Collects all relevant context for instrumentation and recommendations."""
