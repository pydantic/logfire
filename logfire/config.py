from __future__ import annotations, annotations as _annotations

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
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from typing_extensions import Self, get_args, get_origin

from ._constants import LOGFIRE_API_ROOT
from ._metrics import set_meter_provider
from ._tracer import set_global_tracer_provider
from .exporters.console import ConsoleSpanExporter
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
    id_generator: IdGenerator | None = None,
    ns_timestamp_generator: Callable[[], int] | None = None,
    processors: Sequence[SpanProcessor] | None = None,
    default_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
) -> None:
    f"""
    Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev. Defaults to the value of the environment variable `LOGFIRE_SEND_TO_LOGFIRE` if set, otherwise defaults to `True`.
        logfire_token: `anon_*`, `free_*` or `pro_*` token for logfire, if `None` it defaults to the value f the environment variable `LOGFIRE_LOGFIRE_TOKEN` if set, otherwise if
            `send_to_logfire` is True a new `anon_` project will be created using `project_name`.
        project_name: Name to request when creating a new project, if `None` uses the `LOGFIRE_PROJECT_NAME` environment variable.
        service_name: Name of this service, if `None` uses the `LOGFIRE_SERVICE_NAME` environment variable, or the current directory name.
        console_print: Whether to print to stderr and if so whether to use concise `[timestamp] {{indent}} [message]` lines, or to output full details of every log message.
            If `None` uses the `LOGFIRE_CONSOLE_PRINT` environment variable, otherwise defaults to `'concise'`.
        console_colors: Whether to color terminal output. If `None` uses the `LOGFIRE_CONSOLE_COLORS` environment variable, otherwise defaults to `'auto'`.
        show_summary: When to print a summary of the Logfire setup including a link to the dashboard. If `None` uses the `LOGFIRE_SHOW_SUMMARY` environment variable, otherwise
            defaults to `'new-project'`.
        logfire_dir: Directory to store credentials, and logs. If `None` uses the `LOGFIRE_DIR` environment variable, otherwise defaults to `'.logfire'`.
        logfire_api_root: Root URL for the Logfire API. If `None` uses the `LOGFIRE_API_ROOT` environment variable, otherwise defaults to {LOGFIRE_API_ROOT}.
        id_generator: Generator for span IDs. Defaults to `RandomIdGenerator()` from the OpenTelemetry SDK.
        ns_timestamp_generator: Generator for nanosecond timestamps. Defaults to `time.time_ns` from the Python standard library.
        processors: Span processors to use. Defaults to an empty sequence.
        default_processor: Function to create the default span processor. Defaults to `BatchSpanProcessor` from the OpenTelemetry SDK.
            You can configure the export delay for BatchSpanProcessor by setting the `OTEL_BSP_SCHEDULE_DELAY_MILLIS` environment variable.
    """
    config = LogfireConfig(
        api_root=logfire_api_root,
        send_to_logfire=send_to_logfire,
        logfire_token=logfire_token,
        project_name=project_name,
        service_name=service_name,
        console_print=console_print,
        console_colors=console_colors,
        show_summary=show_summary,
        logfire_dir=logfire_dir,
        id_generator=id_generator,
        ns_timestamp_generator=ns_timestamp_generator,
        processors=processors,
        default_processor=default_processor,
    )
    return _configure(config)


def _configure(config: LogfireConfig) -> None:
    global _meter_provider
    # this function exists just to avoid programming errors by referencing local variables in config()
    tracer_provider = SDKTracerProvider(
        resource=Resource.create(
            {
                'service.name': config.service_name,
            }
        ),
        id_generator=config.id_generator,
    )

    for processor in config.processors:
        tracer_provider.add_span_processor(processor)

    if config.console_print != 'off':
        tracer_provider.add_span_processor(
            config.default_processor(
                ConsoleSpanExporter(verbose=config.console_print == 'verbose'),
            )
        )

    credentials_from_local_file = None

    if config.send_to_logfire:
        if config.logfire_token is None:
            credentials_from_local_file = LogfireCredentials.load_creds_file(config.logfire_dir)
            if credentials_from_local_file:
                config.logfire_token = credentials_from_local_file.token
            else:
                # create a token by asking logfire.dev to create a new project
                new_credentials = LogfireCredentials.create_new_project(
                    logfire_api_url=config.api_root, requested_project_name=config.project_name or config.service_name
                )
                config.logfire_token = new_credentials.token
                new_credentials.write_creds_file(config.logfire_dir)
                if config.show_summary != 'never':
                    new_credentials.print_new_token_summary(config.logfire_dir)
                # to avoid printing another summary
                credentials_from_local_file = None

        headers = {'User-Agent': f'logfire/{VERSION}', 'Authorization': config.logfire_token}
        endpoint = f'{config.api_root}/v1/traces'
        tracer_provider.add_span_processor(
            config.default_processor(
                OTLPSpanExporter(
                    endpoint=endpoint,
                    headers=headers,
                )
            )
        )

        metric_exporter = OTLPMetricExporter(endpoint=f'{config.api_root}/v1/metrics', headers=headers)
        _meter_provider = set_meter_provider(exporter=metric_exporter)

    if config.show_summary == 'always' and credentials_from_local_file:
        credentials_from_local_file.print_existing_token_summary(config.logfire_dir)

    # reset the global proxy tracer
    set_global_tracer_provider(tracer_provider, config)


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


# Need to hold onto a reference to avoid gc
# TODO(adrian): refactor this to be more like the global proxy tracer
_meter_provider: MeterProvider | None = None


def coalesce(runtime: T | None, env: T | None, default: T) -> T:
    """
    Return the first non-None value.
    """
    if runtime is not None:
        return runtime
    if env is not None:
        return env
    return default


class LogfireConfig:
    api_root: str
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
    id_generator: IdGenerator
    """The ID generator to use"""
    ns_timestamp_generator: Callable[[], int]
    """The nanosecond timestamp generator to use"""
    processors: Sequence[SpanProcessor]
    """Additional span processors"""
    default_processor: Callable[[SpanExporter], SpanProcessor]
    """The span processor used for the logfire exporter and console exporter"""

    def __init__(
        self,
        api_root: str | None = None,
        send_to_logfire: bool | None = None,
        logfire_token: str | None = None,
        project_name: str | None = None,
        service_name: str | None = None,
        console_print: _ConsolePrintValues | None = None,
        console_colors: _ConsoleColorsValues | None = None,
        show_summary: _ShowSummaryValues | None = None,
        logfire_dir: Path | None = None,
        id_generator: IdGenerator | None = None,
        ns_timestamp_generator: Callable[[], int] | None = None,
        processors: Sequence[SpanProcessor] | None = None,
        default_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
    ) -> None:
        """
        Configure the logfire SDK.

        See the `configure` function for details of the arguments.
        """
        self.api_root = api_root or os.getenv('LOGFIRE_API_ROOT') or DEFAULT_CONFIG.api_root
        self.send_to_logfire = coalesce(
            send_to_logfire, _get_bool_from_env('LOGFIRE_SEND_TO_LOGFIRE'), DEFAULT_CONFIG.send_to_logfire
        )
        self.logfire_token = logfire_token or os.getenv('LOGFIRE_LOGFIRE_TOKEN') or DEFAULT_CONFIG.logfire_token
        self.project_name = project_name or os.getenv('LOGFIRE_PROJECT_NAME') or DEFAULT_CONFIG.project_name
        self.service_name = service_name or os.getenv('LOGFIRE_SERVICE_NAME') or DEFAULT_CONFIG.service_name
        self.console_print = console_print or _check_literal(os.getenv('LOGFIRE_CONSOLE_PRINT'), 'console_print', _ConsolePrintValues) or DEFAULT_CONFIG.console_print  # type: ignore
        self.console_colors = console_colors or _check_literal(os.getenv('LOGFIRE_CONSOLE_COLORS'), 'console_colors', _ConsoleColorsValues) or DEFAULT_CONFIG.console_colors  # type: ignore
        self.show_summary = show_summary or _check_literal(os.getenv('LOGFIRE_SHOW_SUMMARY'), 'show_summary', _ShowSummaryValues) or DEFAULT_CONFIG.show_summary  # type: ignore
        if logfire_dir:
            self.logfire_dir = logfire_dir
        else:
            dir = os.getenv('LOGFIRE_DIR')
            if dir is not None:
                self.logfire_dir = Path(dir)
            else:
                self.logfire_dir = DEFAULT_CONFIG.logfire_dir
        self.id_generator = id_generator or DEFAULT_CONFIG.id_generator
        self.ns_timestamp_generator = ns_timestamp_generator or DEFAULT_CONFIG.ns_timestamp_generator
        self.processors = tuple(processors or DEFAULT_CONFIG.processors)
        self.default_processor = default_processor or DEFAULT_CONFIG.default_processor

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

    def __repr__(self) -> str:
        return f'LogfireConfig({", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())})'


DEFAULT_CONFIG = object.__new__(LogfireConfig)
DEFAULT_CONFIG.api_root = LOGFIRE_API_ROOT
DEFAULT_CONFIG.send_to_logfire = True
DEFAULT_CONFIG.console_print = 'concise'
DEFAULT_CONFIG.console_colors = 'auto'
DEFAULT_CONFIG.show_summary = 'new-project'
DEFAULT_CONFIG.logfire_dir = Path('.logfire')
DEFAULT_CONFIG.project_name = None
DEFAULT_CONFIG.logfire_token = None
DEFAULT_CONFIG.service_name = 'unknown'
DEFAULT_CONFIG.id_generator = RandomIdGenerator()
DEFAULT_CONFIG.ns_timestamp_generator = time.time_ns
DEFAULT_CONFIG.processors = ()
DEFAULT_CONFIG.default_processor = BatchSpanProcessor


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
"""
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
"""
            )


def _print_summary(message: str):
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
    Console(stderr=True, theme=custom_theme).print(panel)


def _get_creds_file(creds_dir: Path) -> Path:
    """
    Get the path to the credentials file.
    """
    return creds_dir / CREDENTIALS_FILENAME


class LogfireConfigError(ValueError):
    """
    Error raised when there is a problem with the Logfire configuration.
    """
