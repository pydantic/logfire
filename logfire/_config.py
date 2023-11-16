from __future__ import annotations as _annotations

import dataclasses
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal, Sequence

import requests
from opentelemetry import metrics, trace
from opentelemetry.context import attach, detach, set_value
from opentelemetry.environment_variables import OTEL_TRACES_EXPORTER
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.environment_variables import (
    OTEL_BSP_SCHEDULE_DELAY,
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT,
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT,
    OTEL_RESOURCE_ATTRIBUTES,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.semconv.resource import ResourceAttributes
from typing_extensions import Self

from ._collect_system_info import collect_package_info
from ._config_params import ParamManager, PydanticPluginRecordValues
from ._constants import (
    DEFAULT_FALLBACK_FILE_NAME,
    OTLP_MAX_BODY_SIZE,
    RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
    SUPPRESS_INSTRUMENTATION_CONTEXT_KEY,
)
from ._metrics import ProxyMeterProvider, configure_metrics
from ._tracer import ProxyTracerProvider
from .exceptions import LogfireConfigError
from .exporters._fallback import FallbackSpanExporter
from .exporters._file import FileSpanExporter
from .exporters._otlp import OTLPExporterHttpSession
from .exporters.console import ConsoleColorsValues, ConsoleSpanExporter
from .integrations._executors import instrument_executors
from .version import VERSION

CREDENTIALS_FILENAME = 'logfire_credentials.json'
"""Default base URL for the Logfire API."""
COMMON_REQUEST_HEADERS = {'User-Agent': f'logfire/{VERSION}'}
"""Common request headers for requests to the Logfire API."""


@dataclass
class ConsoleOptions:
    """Options for controlling console output."""

    colors: ConsoleColorsValues = 'auto'
    indent_spans: bool = True
    include_timestamps: bool = True
    verbose: bool = False


@dataclass
class PydanticPluginOptions:
    """Options for the Pydantic plugin."""

    record: PydanticPluginRecordValues = 'off'
    include: set[str] = field(default_factory=set)
    exclude: set[str] = field(default_factory=set)


def configure(
    *,
    send_to_logfire: bool | None = None,
    token: str | None = None,
    project_name: str | None = None,
    service_name: str | None = None,
    service_version: str | None = None,
    trace_sample_rate: float | None = None,
    console: ConsoleOptions | Literal[False] | None = None,
    show_summary: bool | None = None,
    config_dir: Path | str | None = None,
    data_dir: Path | str | None = None,
    base_url: str | None = None,
    collect_system_metrics: bool | None = None,
    id_generator: IdGenerator | None = None,
    ns_timestamp_generator: Callable[[], int] | None = None,
    processors: Sequence[SpanProcessor] | None = None,
    default_span_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
    metric_readers: Sequence[MetricReader] | None = None,
    default_otlp_span_exporter_session: requests.Session | None = None,
    logfire_api_session: requests.Session | None = None,
    otlp_span_exporter: SpanExporter | None = None,
    pydantic_plugin: PydanticPluginOptions | None = None,
) -> None:
    """Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev. Defaults to the value of the environment variable `LOGFIRE_SEND_TO_LOGFIRE` if set, otherwise defaults to `True`.
        token: `anon_*`, `free_*` or `pro_*` token for logfire, if `None` it defaults to the value f the environment variable `LOGFIRE_TOKEN` if set, otherwise if
            `send_to_logfire` is `True` a new `anon_` project will be created using `project_name`.
        project_name: Name to request when creating a new project, if `None` uses the `LOGFIRE_PROJECT_NAME` environment variable.
        service_name: Name of this service, if `None` uses the `LOGFIRE_SERVICE_NAME` environment variable, or the current directory name.
        service_version: Version of this service, if `None` uses the `LOGFIRE_SERVICE_VERSION` environment variable or the current git commit hash if available.
        trace_sample_rate: Sampling ratio for spans, if `None` uses the `LOGFIRE_SAMPLING_RATIO` environment variable or the `OTEL_TRACES_SAMPLER_ARG` env variable, or defaults to `1.0`.
        console: Whether to control terminal output. If `None` uses the `LOGFIRE_CONSOLE_*` environment variables,
            otherwise defaults to `ConsoleOption(colors='auto', indent_spans=True, include_timestamps=True, verbose=False)`.
            If `False` disables console output. It can also be disabled by setting `LOGFIRE_CONSOLE` environment variable to `false`.
        show_summary: When to print a summary of the Logfire setup including a link to the dashboard. If `None` uses the `LOGFIRE_SHOW_SUMMARY` environment variable, otherwise
            defaults to `True`.
        config_dir: Directory that contains the `pyproject.toml` file for this project. If `None` uses the `LOGFIRE_CONFIG_DIR` environment variable, otherwise defaults to the
            current working directory.
        data_dir: Directory to store credentials, and logs. If `None` uses the `LOGFIRE_CREDENTIALS_DIR` environment variable, otherwise defaults to `'.logfire'`.
        base_url: Root URL for the Logfire API. If `None` uses the `LOGFIRE_BASE_URL` environment variable, otherwise defaults to https://api.logfire.dev.
        collect_system_metrics: Whether to collect system metrics like CPU and memory usage. If `None` uses the `LOGFIRE_COLLECT_SYSTEM_METRICS` environment variable,
            otherwise defaults to `True`.
        id_generator: Generator for span IDs. Defaults to `RandomIdGenerator()` from the OpenTelemetry SDK.
        ns_timestamp_generator: Generator for nanosecond timestamps. Defaults to [`time.time_ns`](https://docs.python.org/3/library/time.html#time.time_ns) from the Python standard library.
        processors: Span processors to use. Defaults to an empty sequence.
        default_span_processor: A function to create the default span processor. Defaults to `BatchSpanProcessor` from the OpenTelemetry SDK. You can configure the export delay for
            [`BatchSpanProcessor`](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html#opentelemetry.sdk.trace.export.BatchSpanProcessor)
            by setting the `OTEL_BSP_SCHEDULE_DELAY_MILLIS` environment variable.
        metric_readers: Sequence of metric readers to be used.
        default_otlp_span_exporter_session: Session configuration for the OTLP span exporter.
        logfire_api_session: HTTP client session used to communicate with the Logfire API.
        otlp_span_exporter: OTLP span exporter to use. If `None` defaults to [`OTLPSpanExporter`](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html#opentelemetry.exporter.otlp.OTLPSpanExporter)
        pydantic_plugin: Options for the Pydantic plugin. If `None` uses the `LOGFIRE_PYDANTIC_PLUGIN_*` environment
            variables, otherwise defaults to `PydanticPluginOptions(record='off', include=set(), exclude=set())`.
    """
    GLOBAL_CONFIG.load_configuration(
        base_url=base_url,
        send_to_logfire=send_to_logfire,
        token=token,
        project_name=project_name,
        service_name=service_name,
        service_version=service_version,
        trace_sample_rate=trace_sample_rate,
        console=console,
        show_summary=show_summary,
        config_dir=Path(config_dir) if config_dir else None,
        data_dir=Path(data_dir) if data_dir else None,
        collect_system_metrics=collect_system_metrics,
        id_generator=id_generator,
        ns_timestamp_generator=ns_timestamp_generator,
        processors=processors,
        default_span_processor=default_span_processor,
        metric_readers=metric_readers,
        default_otlp_span_exporter_session=default_otlp_span_exporter_session,
        logfire_api_session=logfire_api_session,
        otlp_span_exporter=otlp_span_exporter,
        pydantic_plugin=pydantic_plugin,
    )
    GLOBAL_CONFIG.initialize()


def _get_int_from_env(env_var: str) -> int | None:
    value = os.getenv(env_var)
    if not value:
        return None
    return int(value)


@dataclasses.dataclass
class _LogfireConfigData:
    """Data-only parent class for LogfireConfig.

    This class can be pickled / copied and gives a nice repr,
    while allowing us to keep the ugly stuff only in LogfireConfig.

    In particular, using this dataclass as a base class of LogfireConfig allows us to use
    `dataclasses.asdict` in `integrations/_executors.py` to get a dict with just the attributes from
    `_LogfireConfigData`, and none of the attributes added in `LogfireConfig`.
    """

    base_url: str
    """The base URL of the Logfire API"""

    send_to_logfire: bool
    """Whether to send logs and spans to Logfire"""

    token: str | None
    """The Logfire API token to use"""

    project_name: str | None
    """The Logfire project name to use"""

    service_name: str
    """The name of this service"""

    trace_sample_rate: float
    """The sampling ratio for spans"""

    console: ConsoleOptions | Literal[False] | None
    """Options for controlling console output"""

    show_summary: bool
    """Whether to show the summary when starting a new project"""

    data_dir: Path
    """The directory to store Logfire config in"""

    collect_system_metrics: bool
    """Whether to collect system metrics like CPU and memory usage"""

    id_generator: IdGenerator
    """The ID generator to use"""

    ns_timestamp_generator: Callable[[], int]
    """The nanosecond timestamp generator to use"""

    processors: Sequence[SpanProcessor]
    """Additional span processors"""

    pydantic_plugin: PydanticPluginOptions
    """Options for the Pydantic plugin"""

    default_span_processor: Callable[[SpanExporter], SpanProcessor]
    """The span processor used for the logfire exporter and console exporter"""

    default_otlp_span_exporter_session: requests.Session | None = None
    """The session to use when sending requests to the Logfire API"""

    logfire_api_session: requests.Session | None = None
    """The session to use when checking the Logfire backend"""

    otlp_span_exporter: SpanExporter | None = None
    """The OTLP span exporter to use"""

    def load_configuration(
        self,
        # note that there are no defaults here so that the only place
        # defaults exist is `__init__` and we don't forgot a parameter when
        # forwarding parameters from `__init__` to `load_configuration`
        base_url: str | None,
        send_to_logfire: bool | None,
        token: str | None,
        project_name: str | None,
        service_name: str | None,
        service_version: str | None,
        trace_sample_rate: float | None,
        console: ConsoleOptions | Literal[False] | None,
        show_summary: bool | None,
        config_dir: Path | None,
        data_dir: Path | None,
        collect_system_metrics: bool | None,
        id_generator: IdGenerator | None,
        ns_timestamp_generator: Callable[[], int] | None,
        processors: Sequence[SpanProcessor] | None,
        default_span_processor: Callable[[SpanExporter], SpanProcessor] | None,
        metric_readers: Sequence[MetricReader] | None,
        default_otlp_span_exporter_session: requests.Session | None,
        logfire_api_session: requests.Session | None,
        otlp_span_exporter: SpanExporter | None,
        pydantic_plugin: PydanticPluginOptions | None,
    ) -> None:
        """Merge the given parameters with the environment variables file configurations."""
        config_dir = Path(config_dir or os.getenv('LOGFIRE_CONFIG_DIR') or '.')
        config_from_file = self._load_config_from_file(config_dir)
        param_manager = ParamManager(config_from_file=config_from_file)

        self.base_url = param_manager.load_param('base_url', base_url)
        self.metrics_endpoint = os.getenv(OTEL_EXPORTER_OTLP_METRICS_ENDPOINT) or f'{self.base_url}/v1/metrics'
        self.traces_endpoint = os.getenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT) or f'{self.base_url}/v1/traces'

        self.send_to_logfire = param_manager.load_param('send_to_logfire', send_to_logfire)
        self.token = param_manager.load_param('token', token)
        self.project_name = param_manager.load_param('project_name', project_name)
        self.service_name = param_manager.load_param('service_name', service_name)
        self.service_version = param_manager.load_param('service_version', service_version)
        self.trace_sample_rate = param_manager.load_param('trace_sample_rate', trace_sample_rate)
        self.show_summary = param_manager.load_param('show_summary', show_summary)
        self.data_dir = param_manager.load_param('data_dir', data_dir)
        self.collect_system_metrics = param_manager.load_param('collect_system_metrics', collect_system_metrics)

        if console is not None:
            self.console = console
        elif param_manager.load_param('console') is False:
            self.console = False
        else:
            self.console = ConsoleOptions(
                colors=param_manager.load_param('console_colors'),
                indent_spans=param_manager.load_param('console_indent_span'),
                include_timestamps=param_manager.load_param('console_include_timestamp'),
                verbose=param_manager.load_param('console_verbose'),
            )

        self.pydantic_plugin = pydantic_plugin or PydanticPluginOptions(
            record=param_manager.load_param('pydantic_plugin_record'),
            include=param_manager.load_param('pydantic_plugin_include'),
            exclude=param_manager.load_param('pydantic_plugin_exclude'),
        )

        self.id_generator = id_generator or RandomIdGenerator()
        self.ns_timestamp_generator = ns_timestamp_generator or time.time_ns
        self.processors = list(processors or ())
        self.default_span_processor = default_span_processor or _get_default_span_processor
        self.metric_readers = metric_readers
        self.default_otlp_span_exporter_session = default_otlp_span_exporter_session
        self.logfire_api_session = logfire_api_session
        self.otlp_span_exporter = otlp_span_exporter
        if self.service_version is None:
            try:
                self.service_version = get_git_revision_hash()
            except Exception:
                # many things could go wrong here, e.g. git is not installed, etc.
                # ignore them
                pass

    def _load_config_from_file(self, config_dir: Path) -> dict[str, Any]:
        config_file = config_dir / 'pyproject.toml'
        if not config_file.exists():
            return {}
        try:
            if sys.version_info >= (3, 11):
                import tomllib

                with config_file.open('rb') as f:
                    data = tomllib.load(f)
            else:
                import rtoml

                with config_file.open() as f:
                    data = rtoml.load(f)
            return data.get('tool', {}).get('logfire', {})
        except Exception as exc:
            raise LogfireConfigError(f'Invalid config file: {config_file}') from exc


class LogfireConfig(_LogfireConfigData):
    def __init__(
        self,
        base_url: str | None = None,
        send_to_logfire: bool | None = None,
        token: str | None = None,
        project_name: str | None = None,
        service_name: str | None = None,
        service_version: str | None = None,
        trace_sample_rate: float | None = None,
        console: ConsoleOptions | Literal[False] | None = None,
        show_summary: bool | None = None,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
        collect_system_metrics: bool | None = None,
        id_generator: IdGenerator | None = None,
        ns_timestamp_generator: Callable[[], int] | None = None,
        processors: Sequence[SpanProcessor] | None = None,
        default_span_processor: Callable[[SpanExporter], SpanProcessor] | None = None,
        metric_readers: Sequence[MetricReader] | None = None,
        default_otlp_span_exporter_session: requests.Session | None = None,
        logfire_api_session: requests.Session | None = None,
        otlp_span_exporter: SpanExporter | None = None,
        pydantic_plugin: PydanticPluginOptions | None = None,
    ) -> None:
        """Create a new LogfireConfig.

        Users should never need to call this directly, instead use `logfire.configure`.

        See `_LogfireConfigData` for parameter documentation.
        """
        # The `load_configuration` is it's own method so that it can be called on an existing config object
        # in particular the global config object.
        self.load_configuration(
            base_url=base_url,
            send_to_logfire=send_to_logfire,
            token=token,
            project_name=project_name,
            service_name=service_name,
            service_version=service_version,
            trace_sample_rate=trace_sample_rate,
            console=console,
            show_summary=show_summary,
            config_dir=config_dir,
            data_dir=data_dir,
            collect_system_metrics=collect_system_metrics,
            id_generator=id_generator,
            ns_timestamp_generator=ns_timestamp_generator,
            processors=processors,
            default_span_processor=default_span_processor,
            metric_readers=metric_readers,
            default_otlp_span_exporter_session=default_otlp_span_exporter_session,
            logfire_api_session=logfire_api_session,
            otlp_span_exporter=otlp_span_exporter,
            pydantic_plugin=pydantic_plugin,
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
        token: str | None = None,
        data_dir: Path = Path('.logfire'),
    ) -> tuple[str | None, LogfireCredentials | None]:
        file_creds = LogfireCredentials.load_creds_file(data_dir)
        if token is None:
            token = os.getenv('LOGFIRE_TOKEN')
            if token is None and file_creds:
                token = file_creds.token
        return token, file_creds

    def initialize(self) -> ProxyTracerProvider:  # noqa: C901
        """Configure internals to start exporting traces and metrics."""
        backup_context = attach(set_value(SUPPRESS_INSTRUMENTATION_CONTEXT_KEY, True))
        try:
            resource_attributes: dict[str, Any] = {
                ResourceAttributes.SERVICE_NAME: self.service_name,
                RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS: json.dumps(collect_package_info()),
            }
            if self.service_version:
                resource_attributes[ResourceAttributes.SERVICE_VERSION] = self.service_version
            resource_attributes_from_env = os.getenv(OTEL_RESOURCE_ATTRIBUTES)
            if resource_attributes_from_env:
                for _field in resource_attributes_from_env.split(','):
                    key, value = _field.split('=')
                    resource_attributes[key.strip()] = value.strip()

            resource = Resource.create(resource_attributes)
            tracer_provider = SDKTracerProvider(
                sampler=ParentBasedTraceIdRatio(self.trace_sample_rate),
                resource=resource,
                id_generator=self.id_generator,
            )
            self._tracer_provider.set_provider(tracer_provider)

            for processor in self.processors:
                tracer_provider.add_span_processor(processor)

            if self.console:
                tracer_provider.add_span_processor(
                    SimpleSpanProcessor(
                        ConsoleSpanExporter(
                            colors=self.console.colors,
                            indent_spans=self.console.indent_spans,
                            include_timestamp=self.console.include_timestamps,
                            verbose=self.console.verbose,
                        ),
                    )
                )

            credentials_from_local_file = None

            metric_readers = list(self.metric_readers or ())

            if self.send_to_logfire:
                new_credentials: LogfireCredentials | None = None
                if self.token is None:
                    credentials_from_local_file = LogfireCredentials.load_creds_file(self.data_dir)
                    credentials_to_save = credentials_from_local_file
                    if not credentials_from_local_file:
                        # create a token by asking logfire.dev to create a new project
                        new_credentials = LogfireCredentials.create_new_project(
                            logfire_api_url=self.base_url,
                            requested_project_name=self.project_name or self.service_name,
                            session=self.logfire_api_session,
                        )
                        new_credentials.write_creds_file(self.data_dir)
                        if self.show_summary:
                            new_credentials.print_token_summary()
                        credentials_to_save = new_credentials
                        # to avoid printing another summary
                        credentials_from_local_file = None

                    assert credentials_to_save is not None
                    self.token = self.token or credentials_to_save.token
                    self.project_name = self.project_name or credentials_to_save.project_name
                    self.base_url = self.base_url or credentials_to_save.logfire_api_url

                headers = {
                    'User-Agent': f'logfire/{VERSION}',
                    'Authorization': self.token,
                }
                # NOTE: Only check the backend if we didn't call it already.
                if new_credentials is None:
                    logfire_api_session = self.logfire_api_session or requests.Session()
                    logfire_api_session.headers.update(headers)
                    self.check_logfire_backend(logfire_api_session)

                session = self.default_otlp_span_exporter_session or OTLPExporterHttpSession(
                    max_body_size=OTLP_MAX_BODY_SIZE
                )
                session.headers.update(headers)
                otel_traces_exporter_env = os.getenv(OTEL_TRACES_EXPORTER)
                otel_traces_exporter_env = otel_traces_exporter_env.lower() if otel_traces_exporter_env else None
                if otel_traces_exporter_env is None or otel_traces_exporter_env == 'otlp':
                    if self.otlp_span_exporter:
                        span_exporter = self.otlp_span_exporter
                    else:
                        span_exporter = OTLPSpanExporter(endpoint=self.traces_endpoint, session=session)
                    span_exporter = FallbackSpanExporter(
                        span_exporter, FileSpanExporter(self.data_dir / DEFAULT_FALLBACK_FILE_NAME)
                    )
                    self._tracer_provider.add_span_processor(self.default_span_processor(span_exporter))
                elif otel_traces_exporter_env != 'none':
                    raise ValueError(
                        'OTEL_TRACES_EXPORTER must be "otlp", "none" or unset. Logfire does not support other exporters.'
                    )

                metric_readers.append(
                    PeriodicExportingMetricReader(
                        OTLPMetricExporter(
                            endpoint=self.metrics_endpoint,
                            headers=headers,
                        )
                    )
                )

            if self.show_summary and credentials_from_local_file:
                credentials_from_local_file.print_token_summary()

            meter_provider = MeterProvider(metric_readers=metric_readers, resource=resource)
            if self.collect_system_metrics:
                configure_metrics(meter_provider)
            self._meter_provider.set_meter_provider(meter_provider)

            if self is GLOBAL_CONFIG and not self._initialized:
                trace.set_tracer_provider(self._tracer_provider)
                metrics.set_meter_provider(self._meter_provider)

            self._initialized = True

            # set up context propagation for ThreadPoolExecutor and ProcessPoolExecutor
            instrument_executors()

            return self._tracer_provider
        finally:
            detach(backup_context)

    def get_tracer_provider(self) -> ProxyTracerProvider:
        """Get a tracer provider from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The tracer provider.
        """
        if not self._initialized:
            return self.initialize()
        return self._tracer_provider

    def check_logfire_backend(self, session: requests.Session) -> None:
        """Check that the token is valid, and the Logfire API is reachable.

        Raises:
            LogfireConfigError: If the token is invalid or the Logfire API is not reachable.
        """
        try:
            response = session.get(f'{self.base_url}/v1/health')
            if response.status_code == 404:
                raise LogfireConfigError('Invalid Logfire token.')
            response.raise_for_status()
        except requests.HTTPError as e:
            raise LogfireConfigError('Logfire API is not healthy.') from e


def _get_default_span_processor(exporter: SpanExporter) -> SpanProcessor:
    schedule_delay_millis = _get_int_from_env(OTEL_BSP_SCHEDULE_DELAY) or 500
    return BatchSpanProcessor(exporter, schedule_delay_millis=schedule_delay_millis)


# The global config is the single global object in logfire
# It also does not initialize anything when it's created (right now)
# but when `logfire.configure` aka `GLOBAL_CONFIG.configure` is called
# it will initialize the tracer and metrics
GLOBAL_CONFIG = LogfireConfig()


@dataclasses.dataclass
class LogfireCredentials:
    """Credentials for logfire.dev."""

    token: str
    """The Logfire API token to use."""
    project_name: str
    """The name of the project."""
    dashboard_url: str
    """The URL to the project dashboard."""
    logfire_api_url: str
    """The Logfire API base URL."""

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
    def create_new_project(
        cls, *, logfire_api_url: str, requested_project_name: str, session: requests.Session | None = None
    ) -> Self:
        """Create a new project on logfire.dev requesting the given project name.

        Args:
            logfire_api_url: The Logfire API base URL.
            requested_project_name: Name to request for the project, the actual returned name may include a random
                suffix to make it unique.
            session: HTTP client session used to communicate with the Logfire API.

        Returns:
            The new credentials.

        Raises:
            LogfireConfigError: If there was an error creating the new project.
        """
        url = f'{logfire_api_url}/v1/projects/'
        try:
            response = (session or requests).post(
                url,
                params={'requested_project_name': requested_project_name},
                headers=COMMON_REQUEST_HEADERS,
            )
            response.raise_for_status()
        except requests.ConnectionError as e:
            raise LogfireConfigError(f'Error creating new project at {url}') from e
        else:
            json_data = response.json()
            try:
                return cls(**json_data, logfire_api_url=logfire_api_url)
            except TypeError as e:
                raise LogfireConfigError(f'Invalid credentials, when creating project at {url}: {e}') from e

    def write_creds_file(self, creds_dir: Path) -> None:
        """Write a credentials file to the given path."""
        data = dataclasses.asdict(self)
        path = _get_creds_file(creds_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')

    def print_token_summary(self) -> None:
        """Print a summary of the existing project."""
        if self.dashboard_url:
            _print_summary(
                f'[bold]Logfire[/bold] dashboard: [link={self.dashboard_url} cyan]{self.dashboard_url}[/link]',
                min_content_width=len(self.dashboard_url),
            )


def _print_summary(message: str, min_content_width: int) -> None:
    from rich.console import Console
    from rich.style import Style
    from rich.theme import Theme

    # customise the link color since the default `blue` is too dark for me to read.
    custom_theme = Theme({'markdown.link_url': Style(color='cyan')})
    console = Console(stderr=True, theme=custom_theme)
    if console.width < min_content_width + 4:
        console.width = min_content_width + 4
    console.print(message)


def _get_creds_file(creds_dir: Path) -> Path:
    """Get the path to the credentials file."""
    return creds_dir / CREDENTIALS_FILENAME


try:
    import git

    def get_git_revision_hash() -> str:
        repo = git.Repo(search_parent_directories=True)
        return repo.head.object.hexsha

except ImportError:
    # gitpython is not installed
    # fall back to using the git command line

    def get_git_revision_hash() -> str:
        """Get the current git commit hash."""
        import subprocess

        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.STDOUT).decode('ascii').strip()
