import dataclasses
import requests
from .auth import DEFAULT_FILE as DEFAULT_FILE, DefaultFile as DefaultFile, is_logged_in as is_logged_in
from .config_params import ParamManager as ParamManager, PydanticPluginRecordValues as PydanticPluginRecordValues
from .constants import DEFAULT_FALLBACK_FILE_NAME as DEFAULT_FALLBACK_FILE_NAME, LevelName as LevelName, OTLP_MAX_BODY_SIZE as OTLP_MAX_BODY_SIZE
from .exporters.console import ConsoleColorsValues as ConsoleColorsValues, IndentedConsoleSpanExporter as IndentedConsoleSpanExporter, ShowParentsConsoleSpanExporter as ShowParentsConsoleSpanExporter, SimpleConsoleSpanExporter as SimpleConsoleSpanExporter
from .exporters.fallback import FallbackSpanExporter as FallbackSpanExporter
from .exporters.file import FileSpanExporter as FileSpanExporter
from .exporters.otlp import OTLPExporterHttpSession as OTLPExporterHttpSession, RetryFewerSpansSpanExporter as RetryFewerSpansSpanExporter
from .exporters.processor_wrapper import MainSpanProcessorWrapper as MainSpanProcessorWrapper
from .exporters.quiet_metrics import QuietMetricExporter as QuietMetricExporter
from .exporters.remove_pending import RemovePendingSpansExporter as RemovePendingSpansExporter
from .exporters.test import TestExporter as TestExporter
from .integrations.executors import instrument_executors as instrument_executors
from .main import FastLogfireSpan as FastLogfireSpan, LogfireSpan as LogfireSpan
from .metrics import ProxyMeterProvider as ProxyMeterProvider
from .scrubbing import BaseScrubber as BaseScrubber, NOOP_SCRUBBER as NOOP_SCRUBBER, Scrubber as Scrubber, ScrubbingOptions as ScrubbingOptions
from .stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from .tracer import PendingSpanProcessor as PendingSpanProcessor, ProxyTracerProvider as ProxyTracerProvider
from .utils import UnexpectedResponse as UnexpectedResponse, ensure_data_dir_exists as ensure_data_dir_exists, get_version as get_version, read_toml_file as read_toml_file, suppress_instrumentation as suppress_instrumentation
from _typeshed import Incomplete
from dataclasses import dataclass
from functools import cached_property
from logfire.exceptions import LogfireConfigError as LogfireConfigError
from logfire.sampling import SamplingOptions as SamplingOptions
from logfire.sampling._tail_sampling import TailSamplingProcessor as TailSamplingProcessor
from logfire.version import VERSION as VERSION
from opentelemetry import metrics
from opentelemetry.sdk.metrics.export import MetricReader as MetricReader
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.sdk.trace.id_generator import IdGenerator
from pathlib import Path
from typing import Any, Callable, Literal, Sequence, TypedDict
from typing_extensions import Self, Unpack
from weakref import WeakSet

OPEN_SPANS: WeakSet[LogfireSpan | FastLogfireSpan]
CREDENTIALS_FILENAME: str
COMMON_REQUEST_HEADERS: Incomplete
PROJECT_NAME_PATTERN: str
METRICS_PREFERRED_TEMPORALITY: Incomplete

@dataclass
class ConsoleOptions:
    """Options for controlling console output."""
    colors: ConsoleColorsValues = ...
    span_style: Literal['simple', 'indented', 'show-parents'] = ...
    include_timestamps: bool = ...
    verbose: bool = ...
    min_log_level: LevelName = ...

@dataclass
class PydanticPlugin:
    """Options for the Pydantic plugin."""
    record: PydanticPluginRecordValues = ...
    include: set[str] = ...
    exclude: set[str] = ...

class DeprecatedKwargs(TypedDict): ...

def configure(*, send_to_logfire: bool | Literal['if-token-present'] | None = None, token: str | None = None, service_name: str | None = None, service_version: str | None = None, console: ConsoleOptions | Literal[False] | None = None, show_summary: bool | None = None, config_dir: Path | str | None = None, data_dir: Path | str | None = None, base_url: str | None = None, id_generator: IdGenerator | None = None, ns_timestamp_generator: Callable[[], int] | None = None, additional_span_processors: Sequence[SpanProcessor] | None = None, additional_metric_readers: Sequence[MetricReader] | None = None, pydantic_plugin: PydanticPlugin | None = None, fast_shutdown: bool = False, scrubbing: ScrubbingOptions | Literal[False] | None = None, inspect_arguments: bool | None = None, sampling: SamplingOptions | None = None, **deprecated_kwargs: Unpack[DeprecatedKwargs]) -> None:
    """Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev. Defaults to the `LOGFIRE_SEND_TO_LOGFIRE` environment
            variable if set, otherwise defaults to `True`. If `if-token-present` is provided, logs will only be sent if
            a token is present.
        token: The project token. Defaults to the `LOGFIRE_TOKEN` environment variable.
        service_name: Name of this service. Defaults to the `LOGFIRE_SERVICE_NAME` environment variable.
        service_version: Version of this service. Defaults to the `LOGFIRE_SERVICE_VERSION` environment variable, or the
            current git commit hash if available.
        console: Whether to control terminal output. If `None` uses the `LOGFIRE_CONSOLE_*` environment variables,
            otherwise defaults to `ConsoleOption(colors='auto', indent_spans=True, include_timestamps=True, verbose=False)`.
            If `False` disables console output. It can also be disabled by setting `LOGFIRE_CONSOLE` environment variable to `false`.
        show_summary: When to print a summary of the Logfire setup including a link to the dashboard. If `None` uses the `LOGFIRE_SHOW_SUMMARY` environment variable, otherwise
            defaults to `True`.
        config_dir: Directory that contains the `pyproject.toml` file for this project. If `None` uses the
            `LOGFIRE_CONFIG_DIR` environment variable, otherwise defaults to the current working directory.
        data_dir: Directory to store credentials, and logs. If `None` uses the `LOGFIRE_CREDENTIALS_DIR` environment variable, otherwise defaults to `'.logfire'`.
        base_url: Root URL for the Logfire API. If `None` uses the `LOGFIRE_BASE_URL` environment variable, otherwise defaults to https://logfire-api.pydantic.dev.
        id_generator: Generator for span IDs. Defaults to `RandomIdGenerator()` from the OpenTelemetry SDK.
        ns_timestamp_generator: Generator for nanosecond timestamps. Defaults to [`time.time_ns`][time.time_ns] from the
            Python standard library.
        additional_span_processors: Span processors to use in addition to the default processor which exports spans to Logfire's API.
        additional_metric_readers: Sequence of metric readers to be used in addition to the default reader
            which exports metrics to Logfire's API.
        pydantic_plugin: Configuration for the Pydantic plugin. If `None` uses the `LOGFIRE_PYDANTIC_PLUGIN_*` environment
            variables, otherwise defaults to `PydanticPlugin(record='off')`.
        fast_shutdown: Whether to shut down exporters and providers quickly, mostly used for tests. Defaults to `False`.
        scrubbing: Options for scrubbing sensitive data. Set to `False` to disable.
        inspect_arguments: Whether to enable
            [f-string magic](https://docs.pydantic.dev/logfire/guides/onboarding_checklist/add_manual_tracing/#f-strings).
            If `None` uses the `LOGFIRE_INSPECT_ARGUMENTS` environment variable.
            Defaults to `True` if and only if the Python version is at least 3.11.
        sampling: Sampling options. See the [sampling guide](https://docs.pydantic.dev/logfire/guides/advanced/sampling/).
    """

@dataclasses.dataclass
class _LogfireConfigData:
    """Data-only parent class for LogfireConfig.

    This class can be pickled / copied and gives a nice repr,
    while allowing us to keep the ugly stuff only in LogfireConfig.

    In particular, using this dataclass as a base class of LogfireConfig allows us to use
    `dataclasses.asdict` in `integrations/executors.py` to get a dict with just the attributes from
    `_LogfireConfigData`, and none of the attributes added in `LogfireConfig`.
    """
    base_url: str
    send_to_logfire: bool | Literal['if-token-present']
    token: str | None
    service_name: str
    service_version: str | None
    console: ConsoleOptions | Literal[False] | None
    show_summary: bool
    data_dir: Path
    id_generator: IdGenerator
    ns_timestamp_generator: Callable[[], int]
    additional_span_processors: Sequence[SpanProcessor] | None
    pydantic_plugin: PydanticPlugin
    fast_shutdown: bool
    scrubbing: ScrubbingOptions | Literal[False]
    inspect_arguments: bool
    sampling: SamplingOptions

class LogfireConfig(_LogfireConfigData):
    def __init__(self, base_url: str | None = None, send_to_logfire: bool | None = None, token: str | None = None, service_name: str | None = None, service_version: str | None = None, console: ConsoleOptions | Literal[False] | None = None, show_summary: bool | None = None, config_dir: Path | None = None, data_dir: Path | None = None, id_generator: IdGenerator | None = None, ns_timestamp_generator: Callable[[], int] | None = None, additional_span_processors: Sequence[SpanProcessor] | None = None, additional_metric_readers: Sequence[MetricReader] | None = None, pydantic_plugin: PydanticPlugin | None = None, fast_shutdown: bool = False, scrubbing: ScrubbingOptions | Literal[False] | None = None, inspect_arguments: bool | None = None, sampling: SamplingOptions | None = None) -> None:
        """Create a new LogfireConfig.

        Users should never need to call this directly, instead use `logfire.configure`.

        See `_LogfireConfigData` for parameter documentation.
        """
    def configure(self, base_url: str | None, send_to_logfire: bool | Literal['if-token-present'] | None, token: str | None, service_name: str | None, service_version: str | None, console: ConsoleOptions | Literal[False] | None, show_summary: bool | None, config_dir: Path | None, data_dir: Path | None, id_generator: IdGenerator | None, ns_timestamp_generator: Callable[[], int] | None, additional_span_processors: Sequence[SpanProcessor] | None, additional_metric_readers: Sequence[MetricReader] | None, pydantic_plugin: PydanticPlugin | None, fast_shutdown: bool, scrubbing: ScrubbingOptions | Literal[False] | None, inspect_arguments: bool | None, sampling: SamplingOptions | None) -> None: ...
    def initialize(self) -> ProxyTracerProvider:
        """Configure internals to start exporting traces and metrics."""
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush all spans and metrics.

        Args:
            timeout_millis: The timeout in milliseconds.

        Returns:
            Whether the flush of spans was successful.
        """
    def get_tracer_provider(self) -> ProxyTracerProvider:
        """Get a tracer provider from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The tracer provider.
        """
    def get_meter_provider(self) -> ProxyMeterProvider:
        """Get a meter provider from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The meter provider.
        """
    def warn_if_not_initialized(self, message: str): ...
    @cached_property
    def meter(self) -> metrics.Meter:
        """Get a meter from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The meter.
        """

GLOBAL_CONFIG: Incomplete

@dataclasses.dataclass
class LogfireCredentials:
    """Credentials for logfire.dev."""
    token: str
    project_name: str
    project_url: str
    logfire_api_url: str
    @classmethod
    def load_creds_file(cls, creds_dir: Path) -> Self | None:
        """Check if a credentials file exists and if so load it.

        Args:
            creds_dir: Path to the credentials directory.

        Returns:
            The loaded credentials or `None` if the file does not exist.

        Raises:
            LogfireConfigError: If the credentials file exists but is invalid.
        """
    @classmethod
    def from_token(cls, token: str, session: requests.Session, base_url: str) -> Self | None:
        """Check that the token is valid.

        Issue a warning if the Logfire API is unreachable, or we get a response other than 200 or 401.

        We continue unless we get a 401. If something is wrong, we'll later store data locally for back-fill.

        Raises:
            LogfireConfigError: If the token is invalid.
        """
    @classmethod
    def get_current_user(cls, session: requests.Session, logfire_api_url: str) -> dict[str, Any] | None: ...
    @classmethod
    def get_user_projects(cls, session: requests.Session, logfire_api_url: str) -> list[dict[str, Any]]:
        """Get list of projects that user has access to them.

        Args:
            session: HTTP client session used to communicate with the Logfire API.
            logfire_api_url: The Logfire API base URL.

        Returns:
            List of user projects.

        Raises:
            LogfireConfigError: If there was an error retrieving user projects.
        """
    @classmethod
    def use_existing_project(cls, *, session: requests.Session, logfire_api_url: str, projects: list[dict[str, Any]], organization: str | None = None, project_name: str | None = None) -> dict[str, Any] | None:
        """Configure one of the user projects to be used by Logfire.

        It configures the project if organization/project_name is a valid project that
        the user has access to it. Otherwise, it asks the user to select a project interactively.

        Args:
            session: HTTP client session used to communicate with the Logfire API.
            logfire_api_url: The Logfire API base URL.
            projects: List of user projects.
            organization: Project organization.
            project_name: Name of project that has to be used.

        Returns:
            The configured project information.

        Raises:
            LogfireConfigError: If there was an error configuring the project.
        """
    @classmethod
    def create_new_project(cls, *, session: requests.Session, logfire_api_url: str, organization: str | None = None, default_organization: bool = False, project_name: str | None = None) -> dict[str, Any]:
        """Create a new project and configure it to be used by Logfire.

        It creates the project under the organization if both project and organization are valid.
        Otherwise, it asks the user to select organization and enter a valid project name interactively.

        Args:
            session: HTTP client session used to communicate with the Logfire API.
            logfire_api_url: The Logfire API base URL.
            organization: The organization name of the new project.
            default_organization: Whether to create the project under the user default organization.
            project_name: The default name of the project.

        Returns:
            The created project informations.

        Raises:
            LogfireConfigError: If there was an error creating projects.
        """
    @classmethod
    def initialize_project(cls, *, logfire_api_url: str, session: requests.Session) -> Self:
        """Create a new project or use an existing project on logfire.dev requesting the given project name.

        Args:
            logfire_api_url: The Logfire API base URL.
            session: HTTP client session used to communicate with the Logfire API.

        Returns:
            The new credentials.

        Raises:
            LogfireConfigError: If there was an error on creating/configuring the project.
        """
    def write_creds_file(self, creds_dir: Path) -> None:
        """Write a credentials file to the given path."""
    def print_token_summary(self) -> None:
        """Print a summary of the existing project."""

def get_git_revision_hash() -> str:
    """Get the current git commit hash."""
def sanitize_project_name(name: str) -> str:
    """Convert `name` to a string suitable for the `requested_project_name` API parameter."""
def default_project_name(): ...

class LogfireNotConfiguredWarning(UserWarning): ...
