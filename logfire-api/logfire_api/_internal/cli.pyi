import argparse
from ..version import VERSION as VERSION
from .auth import DEFAULT_FILE as DEFAULT_FILE, DefaultFile as DefaultFile, HOME_LOGFIRE as HOME_LOGFIRE, is_logged_in as is_logged_in, poll_for_token as poll_for_token, request_device_code as request_device_code
from .config import LogfireCredentials as LogfireCredentials
from .config_params import ParamManager as ParamManager
from .constants import LOGFIRE_BASE_URL as LOGFIRE_BASE_URL
from .tracer import SDKTracerProvider as SDKTracerProvider
from .utils import read_toml_file as read_toml_file
from _typeshed import Incomplete
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.propagate import ContextCarrier as ContextCarrier, get_context as get_context

BASE_OTEL_INTEGRATION_URL: str
BASE_DOCS_URL: str
INTEGRATIONS_DOCS_URL: Incomplete
LOGFIRE_LOG_FILE: Incomplete
file_handler: Incomplete
logger: Incomplete

def version_callback() -> None:
    """Show the version and exit."""
def parse_whoami(args: argparse.Namespace) -> None:
    """Show user authenticated username and the URL to your Logfire project."""
def parse_clean(args: argparse.Namespace) -> None:
    """Remove the contents of the Logfire data directory."""
def parse_backfill(args: argparse.Namespace) -> None:
    """Bulk upload data to Logfire."""

OTEL_PACKAGES: set[str]
OTEL_PACKAGE_LINK: Incomplete

def parse_inspect(args: argparse.Namespace) -> None:
    """Inspect installed packages and recommend packages that might be useful."""
def parse_auth(args: argparse.Namespace) -> None:
    """Authenticate with Logfire.

    This will authenticate your machine with Logfire and store the credentials.
    """
def parse_list_projects(args: argparse.Namespace) -> None:
    """List user projects."""
def parse_create_new_project(args: argparse.Namespace) -> None:
    """Create a new project."""
def parse_use_project(args: argparse.Namespace) -> None:
    """Use an existing project."""
def parse_info(_args: argparse.Namespace) -> None:
    """Show versions of logfire, OS and related packages."""
def main(args: list[str] | None = None) -> None:
    """Run the CLI."""
