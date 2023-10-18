from __future__ import annotations as _annotations

import dataclasses
import json
import os
import time
from pathlib import Path
from typing import (
    Any,
    Callable,
    Literal,
    Sequence,
    TypeVar,
)

import httpx
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from typing_extensions import Self, get_args, get_origin

from ._constants import LOGFIRE_API_ROOT
from ._metrics import ProxyMeterProvider, configure_metrics
from ._tracer import ProxyTracerProvider
from .exporters.console import ConsoleSpanExporter
from .integrations._executors import instrument_executors
from .version import VERSION

CREDENTIALS_FILENAME = 'logfire_credentials.json'
"""Default base URL for the Logfire API."""
COMMON_REQUEST_HEADERS = {'User-Agent': f'logfire/{VERSION}'}


def configure(
    send_to_logfire: bool | None = None,
    logfire_token: str | None = None,
    project_name: str | None = None,
    service_name: str | None = None,
    console_print: Literal['off', 'concise', 'verbose'] | None = None,
    console_colors: Literal['auto', 'always', 'never'] | None = None,
    show_summary: Literal['always', 'never', 'new-project'] | None = None,
    logfire_dir: Path | None = None,
    logfire_api_root: str | None = None,
    collect_system_metrics: bool | None = None,
    id_generator: IdGenerator | None = None,
    ns_timestamp_generator: Callable[[], int] | None = None,
    processors: Sequence[SpanProcessor] | None = None,
    default_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
    metric_readers: Sequence[MetricReader] | None = None,
) -> None:
    """Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev. Defaults to the value of the environment variable `LOGFIRE_SEND_TO_LOGFIRE` if set, otherwise defaults to `True`.
        logfire_token: `anon_*`, `free_*` or `pro_*` token for logfire, if `None` it defaults to the value f the environment variable `LOGFIRE_LOGFIRE_TOKEN` if set, otherwise if
            `send_to_logfire` is True a new `anon_` project will be created using `project_name`.
        project_name: Name to request when creating a new project, if `None` uses the `LOGFIRE_PROJECT_NAME` environment variable.
        service_name: Name of this service, if `None` uses the `LOGFIRE_SERVICE_NAME` environment variable, or the current directory name.
        console_print: Whether to print to stderr and if so whether to use concise `[timestamp] {indent} [message]` lines, or to output full details of every log message.
            If `None` uses the `LOGFIRE_CONSOLE_PRINT` environment variable, otherwise defaults to `'concise'`.
        console_colors: Whether to color terminal output. If `None` uses the `LOGFIRE_CONSOLE_COLORS` environment variable, otherwise defaults to `'auto'`.
        show_summary: When to print a summary of the Logfire setup including a link to the dashboard. If `None` uses the `LOGFIRE_SHOW_SUMMARY` environment variable, otherwise
            defaults to `'new-project'`.
        logfire_dir: Directory to store credentials, and logs. If `None` uses the `LOGFIRE_DIR` environment variable, otherwise defaults to `'.logfire'`.
        logfire_api_root: Root URL for the Logfire API. If `None` uses the `LOGFIRE_API_ROOT` environment variable, otherwise defaults to https://api.logfire.dev.
        id_generator: Generator for span IDs. Defaults to `RandomIdGenerator()` from the OpenTelemetry SDK.
        ns_timestamp_generator: Generator for nanosecond timestamps. Defaults to `time.time_ns` from the Python standard library.
        processors: Span processors to use. Defaults to an empty sequence.
        default_processor: Function to create the default span processor. Defaults to `BatchSpanProcessor` from the OpenTelemetry SDK.
            You can configure the export delay for BatchSpanProcessor by setting the `OTEL_BSP_SCHEDULE_DELAY_MILLIS` environment variable.
    """
    GLOBAL_CONFIG.merge_with_env(
        logfire_api_root=logfire_api_root,
        send_to_logfire=send_to_logfire,
        logfire_token=logfire_token,
        project_name=project_name,
        service_name=service_name,
        console_print=console_print,
        console_colors=console_colors,
        show_summary=show_summary,
        logfire_dir=logfire_dir,
        collect_system_metrics=collect_system_metrics,
        id_generator=id_generator,
        ns_timestamp_generator=ns_timestamp_generator,
        processors=processors,
        default_processor=default_processor,
        metric_readers=metric_readers,
    )
    GLOBAL_CONFIG.initialize()


def _get_bool_from_env(env_var: str) -> bool | None:
    value = os.getenv(env_var)
    if value is None:
        return None
    return value.lower() in ('1', 'true', 't')


_ConsolePrintValues = Literal['off', 'concise', 'verbose']
_ConsoleColorsValues = Literal['auto', 'always', 'never']
_ShowSummaryValues = Literal['always', 'never', 'new-project']


T = TypeVar('T')


def _check_literal(value: Any | None, name: str, tp: type[T]) -> T | None:
    if value is None:
        return None
    assert get_origin(tp) is Literal
    literals = get_args(tp)
    if value not in literals:
        raise LogfireConfigError(f'Expected {name} to be one of {literals}, got {value!r}')
    return value


def _coalesce(runtime: T | None, env: T | None, default: T) -> T:
    """
    Return the first non-None value.
    """
    if runtime is not None:
        return runtime
    if env is not None:
        return env
    return default


@dataclasses.dataclass
class _LogfireConfigData:
    """Data-only parent class for LogfireConfig.

    This class can be pickled / copied and gives a nice repr,
    while allowing us to keep the ugly stuff only in LogfireConfig.

    In particular, using this dataclass as a base class of LogfireConfig allows us to use
    `dataclasses.asdict` in `integrations/_executors.py` to get a dict with just the attributes from
    `_LogfireConfigData`, and none of the attributes added in `LogfireConfig`.
    """

    logfire_api_root: str
    """The root URL of the Logfire API"""

    send_to_logfire: bool
    """Whether to send logs and spans to Logfire"""

    logfire_token: str | None
    """The Logfire API token to use"""

    project_name: str | None
    """The Logfire project name to use"""

    service_name: str
    """The name of this service"""

    console_print: _ConsolePrintValues
    """How to print logs to the console"""

    console_colors: _ConsoleColorsValues
    """Whether to use colors when printing logs to the console"""

    show_summary: _ShowSummaryValues
    """Whether to show the summary when starting a new project"""

    logfire_dir: Path
    """The directory to store Logfire config in"""

    collect_system_metrics: bool
    """Whether to collect system metrics like CPU and memory usage"""

    id_generator: IdGenerator
    """The ID generator to use"""

    ns_timestamp_generator: Callable[[], int]
    """The nanosecond timestamp generator to use"""

    processors: Sequence[SpanProcessor]
    """Additional span processors"""

    default_processor: Callable[[SpanExporter], SpanProcessor]
    """The span processor used for the logfire exporter and console exporter"""

    def merge_with_env(
        self,
        # note that there are no defaults here so that the only place
        # defaults exist is `__init__` and we don't forgot a parameter when
        # forwarding parameters from `__init__` to `merge_with_env
        logfire_api_root: str | None,
        send_to_logfire: bool | None,
        logfire_token: str | None,
        project_name: str | None,
        service_name: str | None,
        console_print: _ConsolePrintValues | None,
        console_colors: _ConsoleColorsValues | None,
        show_summary: _ShowSummaryValues | None,
        logfire_dir: Path | None,
        collect_system_metrics: bool | None,
        id_generator: IdGenerator | None,
        ns_timestamp_generator: Callable[[], int] | None,
        processors: Sequence[SpanProcessor] | None,
        default_processor: Callable[[SpanExporter], SpanProcessor] | None,
        metric_readers: Sequence[MetricReader] | None,
    ) -> None:
        """Merge the given parameters with the environment variables file configurations"""
        self.logfire_api_root = logfire_api_root or os.getenv('LOGFIRE_API_ROOT') or LOGFIRE_API_ROOT
        self.send_to_logfire = _coalesce(
            send_to_logfire,
            _get_bool_from_env('LOGFIRE_SEND_TO_LOGFIRE'),
            True,
        )
        self.logfire_token = logfire_token or os.getenv('LOGFIRE_TOKEN')
        self.project_name = project_name or os.getenv('LOGFIRE_PROJECT_NAME')
        self.service_name = service_name or os.getenv('LOGFIRE_SERVICE_NAME') or 'unknown'
        self.console_print = console_print or _check_literal(os.getenv('LOGFIRE_CONSOLE_PRINT'), 'console_print', _ConsolePrintValues) or 'concise'  # type: ignore
        self.console_colors = console_colors or _check_literal(os.getenv('LOGFIRE_CONSOLE_COLORS'), 'console_colors', _ConsoleColorsValues) or 'auto'  # type: ignore
        self.show_summary = show_summary or _check_literal(os.getenv('LOGFIRE_SHOW_SUMMARY'), 'show_summary', _ShowSummaryValues) or 'new-project'  # type: ignore
        if logfire_dir:
            self.logfire_dir = logfire_dir
        else:
            dir = os.getenv('LOGFIRE_DIR')
            if dir is not None:
                self.logfire_dir = Path(dir)
            else:
                self.logfire_dir = Path('.logfire')
        self.collect_system_metrics = (
            collect_system_metrics or _get_bool_from_env('LOGFIRE_COLLECT_SYSTEM_METRICS') or True
        )
        self.id_generator = id_generator or RandomIdGenerator()
        self.ns_timestamp_generator = ns_timestamp_generator or time.time_ns
        self.processors = list(processors or ())
        self.default_processor = default_processor or BatchSpanProcessor
        self.metric_readers = metric_readers


class LogfireConfig(_LogfireConfigData):
    def __init__(
        self,
        logfire_api_root: str | None = None,
        send_to_logfire: bool | None = None,
        logfire_token: str | None = None,
        project_name: str | None = None,
        service_name: str | None = None,
        console_print: _ConsolePrintValues | None = None,
        console_colors: _ConsoleColorsValues | None = None,
        show_summary: _ShowSummaryValues | None = None,
        logfire_dir: Path | None = None,
        collect_system_metrics: bool | None = None,
        id_generator: IdGenerator | None = None,
        ns_timestamp_generator: Callable[[], int] | None = None,
        processors: Sequence[SpanProcessor] | None = None,
        default_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
        metric_readers: Sequence[MetricReader] | None = None,
    ) -> None:
        """Create a new LogfireConfig.

        Users should never need to call this directly, instead use `logfire.configure`.

        See `_LogfireConfigData` for parameter documentation.
        """
        # merge_with_env is it's own method so that it can be called on an existing config object
        # in particular the global config object
        self.merge_with_env(
            logfire_api_root=logfire_api_root,
            send_to_logfire=send_to_logfire,
            logfire_token=logfire_token,
            project_name=project_name,
            service_name=service_name,
            console_print=console_print,
            console_colors=console_colors,
            show_summary=show_summary,
            logfire_dir=logfire_dir,
            collect_system_metrics=collect_system_metrics,
            id_generator=id_generator,
            ns_timestamp_generator=ns_timestamp_generator,
            processors=processors,
            default_processor=default_processor,
            metric_readers=metric_readers,
        )
        # initialize with no-ops so that we don't impact OTEL's global config just because logfire is installed
        # that is, we defer setting logfire as the otel global config until `configure` is called
        self._tracer_provider = ProxyTracerProvider(trace.NoOpTracerProvider(), self)
        # note: this reference is important because the MeterProvider runs things in background threads
        # thus it "shuts down" when it's gc'ed
        self._meter_provider = ProxyMeterProvider(metrics.NoOpMeterProvider())
        self._initialized = False

    @staticmethod
    def load_token(
        logfire_token: str | None = None,
        logfire_dir: Path = Path('.logfire'),
    ) -> tuple[str | None, LogfireCredentials | None]:
        file_creds = LogfireCredentials.load_creds_file(logfire_dir)
        if logfire_token is None:
            logfire_token = os.getenv('LOGFIRE_TOKEN')
            if logfire_token is None and file_creds:
                logfire_token = file_creds.token
        return logfire_token, file_creds

    def initialize(self) -> ProxyTracerProvider:
        """Configure internals to start exporting traces and metrics."""
        resource = Resource.create(
            {
                'service.name': self.service_name,
            }
        )
        tracer_provider = SDKTracerProvider(
            resource=resource,
            id_generator=self.id_generator,
        )

        for processor in self.processors:
            tracer_provider.add_span_processor(processor)

        if self.console_print != 'off':
            tracer_provider.add_span_processor(
                self.default_processor(
                    ConsoleSpanExporter(verbose=self.console_print == 'verbose'),
                )
            )

        credentials_from_local_file = None

        metric_readers = list(self.metric_readers or ())

        if self.send_to_logfire:
            if self.logfire_token is None:
                credentials_from_local_file = LogfireCredentials.load_creds_file(self.logfire_dir)
                credentials_to_save = credentials_from_local_file
                if not credentials_from_local_file:
                    # create a token by asking logfire.dev to create a new project
                    new_credentials = LogfireCredentials.create_new_project(
                        logfire_api_url=self.logfire_api_root,
                        requested_project_name=self.project_name or self.service_name,
                    )
                    new_credentials.write_creds_file(self.logfire_dir)
                    if self.show_summary != 'never':
                        new_credentials.print_new_token_summary(self.logfire_dir)
                    credentials_to_save = new_credentials
                    # to avoid printing another summary
                    credentials_from_local_file = None

                assert credentials_to_save is not None
                self.logfire_token = self.logfire_token or credentials_to_save.token
                self.project_name = self.project_name or credentials_to_save.project_name
                self.logfire_api_root = self.logfire_api_root or credentials_to_save.logfire_api_url

            headers = {'User-Agent': f'logfire/{VERSION}', 'Authorization': self.logfire_token}
            tracer_provider.add_span_processor(
                self.default_processor(
                    OTLPSpanExporter(
                        endpoint=f'{self.logfire_api_root}/v1/traces',
                        headers=headers,
                    )
                )
            )

            metric_readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(
                        endpoint=f'{self.logfire_api_root}/v1/metrics',
                        headers=headers,
                    )
                )
            )

        if self.show_summary == 'always' and credentials_from_local_file:
            credentials_from_local_file.print_existing_token_summary(self.logfire_dir)

        meter_provider = MeterProvider(metric_readers=metric_readers, resource=resource)
        if self.collect_system_metrics:
            configure_metrics(meter_provider)
        self._tracer_provider.set_provider(tracer_provider)
        self._meter_provider.set_meter_provider(meter_provider)

        if self is GLOBAL_CONFIG and not self._initialized:
            trace.set_tracer_provider(self._tracer_provider)
            metrics.set_meter_provider(self._meter_provider)

        self._initialized = True

        # set up context propagation for ThreadPoolExecutor and ProcessPoolExecutor
        instrument_executors()

        return self._tracer_provider

    def get_tracer_provider(self) -> ProxyTracerProvider:
        """Get a tracer provider from this LogfireConfig

        This is used internally and should not be called by users of the SDK.
        """
        if not self._initialized:
            return self.initialize()
        return self._tracer_provider


# The global config is the single global object in logfire
# It also does not initialize anything when it's created (right now)
# but when `logfire.configure` aka `GLOBAL_CONFIG.configure` is called
# it will initialize the tracer and metrics
GLOBAL_CONFIG = LogfireConfig()


@dataclasses.dataclass
class LogfireCredentials:
    """
    Credentials for logfire.dev.
    """

    token: str
    project_name: str
    """The name of the project"""
    dashboard_url: str
    """The URL to the project dashboard."""
    logfire_api_url: str
    """The root URL for the Logfire API."""

    def __post_init__(self):
        for attr, value in dataclasses.asdict(self).items():
            value = getattr(self, attr)
            if not isinstance(value, str):
                raise TypeError(f'`{attr}` must be a string, got {value!r}')

    @classmethod
    def load_creds_file(cls, creds_dir: Path) -> Self | None:
        """
        Check if a credentials file exists and if so load it.

        Args:
            creds_dir: Path to the credentials directory

        Returns:
            The loaded credentials or `None` if the file does not exist.

        Raises:
            LogfireConfigError: If the credentials file exists but is invalid.
        """
        path = _get_creds_file(creds_dir)
        if path.exists():
            try:
                with path.open('rb') as f:
                    data = json.load(f)
            except (ValueError, OSError) as e:
                raise LogfireConfigError(f'Invalid credentials file: {path}') from e

            try:
                return cls(**data)
            except TypeError as e:
                raise LogfireConfigError(f'Invalid credentials file: {path} - {e}') from e

    @classmethod
    def create_new_project(cls, *, logfire_api_url: str, requested_project_name: str) -> Self:
        """
        Create a new project on logfire.dev requesting the given project name.

        Args:
            logfire_api_url: The root URL for the Logfire API.
            requested_project_name: Name to request for the project, the actual returned name may include a random
                suffix to make it unique.

        Returns:
            The new credentials.
        """
        url = f'{logfire_api_url}/v1/projects/'
        try:
            response = httpx.post(
                url,
                params={'requested_project_name': requested_project_name},
                headers=COMMON_REQUEST_HEADERS,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise LogfireConfigError(f'Error creating new project at {url}') from e
        else:
            json_data = response.json()
            try:
                return cls(**json_data, logfire_api_url=logfire_api_url)
            except TypeError as e:
                raise LogfireConfigError(f'Invalid credentials, when creating project at {url}: {e}') from e

    def write_creds_file(self, creds_dir: Path) -> None:
        """
        Write a credentials file to the given path.
        """
        data = dataclasses.asdict(self)
        path = _get_creds_file(creds_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')

    def print_new_token_summary(self, creds_dir: Path) -> None:
        """
        Print a summary of the new project.
        """
        creds_file = _get_creds_file(creds_dir)
        _print_summary(
            f"""\
A new anonymous project called **{self.project_name}** has been created on logfire.dev, to view it go to:

[{self.dashboard_url}]({self.dashboard_url})

But you can see project details by running `logfire whoami`, or by viewing the credentials file at `{creds_file}`.
""",
            min_content_width=len(self.dashboard_url),
        )

    def print_existing_token_summary(self, creds_dir: Path) -> None:
        """
        Print a summary of the existing project.
        """
        if self.project_name and self.dashboard_url:
            creds_file = _get_creds_file(creds_dir)
            _print_summary(
                f"""\
A project called **{self.project_name}** was found and has been configured for this service, to view it go to:

[{self.dashboard_url}]({self.dashboard_url})

But you can see project details by running `logfire whoami`, or by viewing the credentials file at `{creds_file}`.
""",
                min_content_width=len(self.dashboard_url),
            )


def _print_summary(message: str, min_content_width: int) -> None:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.style import Style
    from rich.theme import Theme

    panel = Panel.fit(
        Markdown(message),
        title='Logfire',
        subtitle=f'logfire SDK v{VERSION}',
        subtitle_align='right',
        border_style='green',
    )

    # customise the link color since the default `blue` is too dark for me to read.
    custom_theme = Theme({'markdown.link_url': Style(color='cyan')})
    console = Console(stderr=True, theme=custom_theme)
    if console.width < min_content_width + 4:
        console.width = min_content_width + 4
    console.print(panel)


def _get_creds_file(creds_dir: Path) -> Path:
    """
    Get the path to the credentials file.
    """
    return creds_dir / CREDENTIALS_FILENAME


class LogfireConfigError(ValueError):
    """
    Error raised when there is a problem with the Logfire configuration.
    """
