import argparse
from _typeshed import Incomplete
from collections.abc import Collection, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from logfire._internal.utils import get_version as get_version
from rich.console import Console
from rich.text import Text

STANDARD_LIBRARY_PACKAGES: Incomplete
AMBIGUOUS_RECOMMENDATION_PACKAGES: Incomplete
INSTRUMENTATION_TARGETS: Incomplete
TARGET_PACKAGE_ALIASES: Incomplete
INSTRUMENTATION_CALL_ARGUMENTS: Incomplete
MINIMUM_INSTRUMENTATION_VERSIONS: Incomplete
OTEL_INSTRUMENTATION_MAP: Incomplete

@dataclass(frozen=True, order=True)
class InstrumentationRecommendation:
    package_name: str
    target_packages: tuple[str, ...]
    minimum_version: str | None = ...
    already_installed: bool = ...
    @property
    def package_spec(self) -> str: ...

@dataclass
class InstrumentationContext:
    instrument_pkg_map: dict[str, str]
    installed_pkgs: set[str]
    installed_otel_pkgs: set[str]
    installed_versions: dict[str, str]
    recommendations: set[InstrumentationRecommendation]

def parse_run(args: argparse.Namespace) -> None: ...
@contextmanager
def alter_sys_argv(argv: list[str], cmd: str) -> Generator[None, None, None]: ...
def is_uv_installed() -> bool:
    """Check if uv package manager is installed and available in the PATH."""
def instrument_packages(installed_otel_packages: set[str], instrument_pkg_map: dict[str, str]) -> list[str]:
    """Call every `logfire.instrument_x()` we can based on what's installed.

    Returns a list of packages that were successfully instrumented.
    """
def instrument_package(import_name: str, *args: str) -> None: ...
def find_recommended_instrumentations_to_install(instrument_pkg_map: dict[str, str], installed_otel_pkgs: set[str], installed_pkgs: set[str], installed_versions: Mapping[str, str] | None = None) -> set[InstrumentationRecommendation]:
    """Determine which OpenTelemetry instrumentation packages are recommended for installation.

    Args:
        instrument_pkg_map: Mapping of instrumentation package names to the packages they instrument.
        installed_otel_pkgs: Set of already installed instrumentation package names.
        installed_pkgs: Set of all installed package names.
        installed_versions: Installed versions keyed by instrumentation package name.

    Returns:
        Instrumentation packages that should be installed or upgraded.
    """
def instrumented_packages_text(installed_otel_pkgs: set[str], instrumented_packages: list[str], installed_pkgs: set[str], installed_versions: Mapping[str, str] | None = None) -> Text: ...
def get_recommendation_texts(recommendations: set[InstrumentationRecommendation]) -> tuple[Text, Text]:
    """Return (recommended_packages_text, install_all_text) as Text objects."""
def print_otel_summary(*, console: Console, instrumented_packages_text: Text | None = None, recommendations: set[InstrumentationRecommendation]) -> None: ...
def installed_packages() -> set[str]:
    """Get a set of all installed packages."""
def collect_instrumentation_context(exclude: Collection[str]) -> InstrumentationContext:
    """Collects all relevant context for instrumentation and recommendations."""
