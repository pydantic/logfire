from __future__ import annotations as _annotations

import dataclasses
import json
import os
import re
import time
import warnings
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Literal, Sequence, cast
from urllib.parse import urljoin

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
from opentelemetry.sdk.metrics import (
    Counter,
    Histogram,
    MeterProvider,
    ObservableCounter,
    ObservableGauge,
    ObservableUpDownCounter,
    UpDownCounter,
)
from opentelemetry.sdk.metrics.export import AggregationTemporality, MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.id_generator import IdGenerator, RandomIdGenerator
from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
from opentelemetry.semconv.resource import ResourceAttributes
from rich.prompt import Confirm, Prompt
from typing_extensions import Self

from ._auth import DEFAULT_FILE, DefaultFile, is_logged_in
from ._collect_system_info import collect_package_info
from ._config_params import ParamManager, PydanticPluginRecordValues
from ._constants import (
    DEFAULT_FALLBACK_FILE_NAME,
    OTLP_MAX_BODY_SIZE,
    RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS,
    SUPPRESS_INSTRUMENTATION_CONTEXT_KEY,
)
from ._metrics import ProxyMeterProvider, configure_metrics
from ._scrubbing import Scrubber, ScrubCallback
from ._tracer import PendingSpanProcessor, ProxyTracerProvider
from ._utils import UnexpectedResponse, ensure_data_dir_exists, read_toml_file
from .exceptions import LogfireConfigError
from .exporters._fallback import FallbackSpanExporter
from .exporters._file import FileSpanExporter
from .exporters._otlp import OTLPExporterHttpSession, RetryFewerSpansSpanExporter
from .exporters._processor_wrapper import SpanProcessorWrapper
from .exporters._remove_pending import RemovePendingSpansExporter
from .exporters.console import (
    ConsoleColorsValues,
    IndentedConsoleSpanExporter,
    ShowParentsConsoleSpanExporter,
    SimpleConsoleSpanExporter,
)
from .integrations._executors import instrument_executors
from .version import VERSION

CREDENTIALS_FILENAME = 'logfire_credentials.json'
"""Default base URL for the Logfire API."""
COMMON_REQUEST_HEADERS = {'User-Agent': f'logfire/{VERSION}'}
"""Common request headers for requests to the Logfire API."""
PROJECT_NAME_PATTERN = r'^[a-z0-9]+(?:-[a-z0-9]+)*$'

METRICS_PREFERRED_TEMPORALITY = {
    Counter: AggregationTemporality.DELTA,
    UpDownCounter: AggregationTemporality.DELTA,
    Histogram: AggregationTemporality.DELTA,
    ObservableCounter: AggregationTemporality.DELTA,
    ObservableUpDownCounter: AggregationTemporality.DELTA,
    ObservableGauge: AggregationTemporality.DELTA,
}
"""This should be passed as the `preferred_temporality` argument of metric readers and exporters."""


@dataclass
class ConsoleOptions:
    """Options for controlling console output."""

    colors: ConsoleColorsValues = 'auto'
    span_style: Literal['simple', 'indented', 'show-parents'] = 'show-parents'
    """How spans are shown in the console."""
    include_timestamps: bool = True
    verbose: bool = False


@dataclass
class PydanticPlugin:
    """Options for the Pydantic plugin."""

    record: PydanticPluginRecordValues = 'off'
    """The record mode for the Pydantic plugin.

    It can be one of the following values:

    * `off`: Disable instrumentation. This is default value.
    * `all`: Send traces and metrics for all events.
    * `failure`: Send metrics for all validations and traces only for validation failures.
    * `metrics`: Send only metrics.
    """
    include: set[str] = field(default_factory=set)
    """By default, third party modules are not instrumented. This option allows you to include specific modules."""
    exclude: set[str] = field(default_factory=set)
    """Exclude specific modules from instrumentation."""


def configure(
    *,
    send_to_logfire: bool | Literal['if-token-present'] | None = None,
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
    logfire_api_session: requests.Session | None = None,
    pydantic_plugin: PydanticPlugin | None = None,
    fast_shutdown: bool = False,
    scrubbing_patterns: Sequence[str] | None = None,
    scrubbing_callback: ScrubCallback | None = None,
) -> None:
    """Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev. Defaults to the `LOGFIRE_SEND_TO_LOGFIRE` environment
            variable if set, otherwise defaults to `True`. If `if-token-present` is provided, logs will only be sent if
            a token is present.
        token: The project token. Defaults to the `LOGFIRE_TOKEN` environment variable.
        project_name: Name to request when creating a new project. Defaults to the `LOGFIRE_PROJECT_NAME` environment
            variable, or the service name. Project name accepts a string value containing alphanumeric characters and
            hyphens (-). The hyphen character must not be located at the beginning or end of the string and should
            appear in between alphanumeric characters.
        service_name: Name of this service. Defaults to the `LOGFIRE_SERVICE_NAME` environment variable, or the current
            directory name.
        service_version: Version of this service. Defaults to the `LOGFIRE_SERVICE_VERSION` environment variable, or the
            current git commit hash if available.
        trace_sample_rate: Sampling ratio for spans. Defaults to the `LOGFIRE_SAMPLING_RATIO` environment variable, or
            the `OTEL_TRACES_SAMPLER_ARG` environment variable, or to `1.0`.
        console: Whether to control terminal output. If `None` uses the `LOGFIRE_CONSOLE_*` environment variables,
            otherwise defaults to `ConsoleOption(colors='auto', indent_spans=True, include_timestamps=True, verbose=False)`.
            If `False` disables console output. It can also be disabled by setting `LOGFIRE_CONSOLE` environment variable to `false`.
        show_summary: When to print a summary of the Logfire setup including a link to the dashboard. If `None` uses the `LOGFIRE_SHOW_SUMMARY` environment variable, otherwise
            defaults to `True`.
        config_dir: Directory that contains the `pyproject.toml` file for this project. If `None` uses the
            `LOGFIRE_CONFIG_DIR` environment variable, otherwise defaults to the current working directory.
        data_dir: Directory to store credentials, and logs. If `None` uses the `LOGFIRE_CREDENTIALS_DIR` environment variable, otherwise defaults to `'.logfire'`.
        base_url: Root URL for the Logfire API. If `None` uses the `LOGFIRE_BASE_URL` environment variable, otherwise defaults to https://api.logfire.dev.
        collect_system_metrics: Whether to collect system metrics like CPU and memory usage. If `None` uses the `LOGFIRE_COLLECT_SYSTEM_METRICS` environment variable,
            otherwise defaults to `True`.
        id_generator: Generator for span IDs. Defaults to `RandomIdGenerator()` from the OpenTelemetry SDK.
        ns_timestamp_generator: Generator for nanosecond timestamps. Defaults to [`time.time_ns`][time.time_ns] from the
            Python standard library.
        processors: Span processors to use. Defaults to None. If None is provided then the default span processor is
            used. If a sequence is passed the default processor is disabled (which disables exporting of spans to
            Logfire's API) and the specified processors are used instead. In particular, if an empty list is provided
            then no span processors are used.
        default_span_processor: A function to create the default span processor. Defaults to `BatchSpanProcessor` from the OpenTelemetry SDK. You can configure the export delay for
            [`BatchSpanProcessor`](https://opentelemetry-python.readthedocs.io/en/latest/sdk/trace.export.html#opentelemetry.sdk.trace.export.BatchSpanProcessor)
            by setting the `OTEL_BSP_SCHEDULE_DELAY_MILLIS` environment variable.
        metric_readers: Sequence of metric readers to be used. If `None` then a default metrics reader is used.
            Pass an empty list to disable metrics.
            Ensure that `preferred_temporality=logfire.METRICS_PREFERRED_TEMPORALITY`
            is passed to the constructor of metric readers/exporters that accept the `preferred_temporality` argument.
        logfire_api_session: HTTP client session used to communicate with the Logfire API.
        pydantic_plugin: Configuration for the Pydantic plugin. If `None` uses the `LOGFIRE_PYDANTIC_PLUGIN_*` environment
            variables, otherwise defaults to `PydanticPlugin(record='off')`.
        fast_shutdown: Whether to shut down exporters and providers quickly, mostly used for tests. Defaults to `False`.
        scrubbing_patterns: A sequence of regular expressions to detect sensitive data that should be redacted.
            For example, the default includes `'password'`, `'secret'`, and `'api[._ -]?key'`.
            The specified patterns are combined with the default patterns.
        scrubbing_callback: A function that is called for each match found by the scrubber.
            If it returns `None`, the value is redacted.
            Otherwise, the returned value replaces the matched value.
            The function accepts a single argument of type [`logfire.ScrubMatch`][logfire.ScrubMatch].
    """
    GLOBAL_CONFIG.configure(
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
        logfire_api_session=logfire_api_session,
        pydantic_plugin=pydantic_plugin,
        fast_shutdown=fast_shutdown,
        scrubbing_patterns=scrubbing_patterns,
        scrubbing_callback=scrubbing_callback,
    )


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

    send_to_logfire: bool | Literal['if-token-present']
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

    logfire_api_session: requests.Session
    """The session to use when checking the Logfire backend"""

    ns_timestamp_generator: Callable[[], int]
    """The nanosecond timestamp generator to use"""

    processors: Sequence[SpanProcessor] | None
    """Additional span processors"""

    pydantic_plugin: PydanticPlugin
    """Options for the Pydantic plugin"""

    default_span_processor: Callable[[SpanExporter], SpanProcessor]
    """The span processor used for the logfire exporter and console exporter"""

    fast_shutdown: bool
    """Whether to shut down exporters and providers quickly, mostly used for tests"""

    scrubbing_patterns: Sequence[str] | None
    """A sequence of regular expressions to detect sensitive data that should be redacted."""

    scrubbing_callback: ScrubCallback | None
    """A function that is called for each match found by the scrubber."""

    def _load_configuration(
        self,
        # note that there are no defaults here so that the only place
        # defaults exist is `__init__` and we don't forgot a parameter when
        # forwarding parameters from `__init__` to `load_configuration`
        base_url: str | None,
        send_to_logfire: bool | Literal['if-token-present'] | None,
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
        logfire_api_session: requests.Session | None,
        pydantic_plugin: PydanticPlugin | None,
        fast_shutdown: bool = False,
        scrubbing_patterns: Sequence[str] | None = None,
        scrubbing_callback: ScrubCallback | None = None,
    ) -> None:
        """Merge the given parameters with the environment variables file configurations."""
        config_dir = Path(config_dir or os.getenv('LOGFIRE_CONFIG_DIR') or '.')
        config_from_file = self._load_config_from_file(config_dir)
        param_manager = ParamManager(config_from_file=config_from_file)

        self.base_url = param_manager.load_param('base_url', base_url)
        self.metrics_endpoint = os.getenv(OTEL_EXPORTER_OTLP_METRICS_ENDPOINT) or urljoin(self.base_url, '/v1/metrics')
        self.traces_endpoint = os.getenv(OTEL_EXPORTER_OTLP_TRACES_ENDPOINT) or urljoin(self.base_url, '/v1/traces')

        self.send_to_logfire = param_manager.load_param('send_to_logfire', send_to_logfire)
        self.token = param_manager.load_param('token', token)
        self.project_name = param_manager.load_param('project_name', project_name)
        self.service_name = param_manager.load_param('service_name', service_name)
        self.service_version = param_manager.load_param('service_version', service_version)
        self.trace_sample_rate = param_manager.load_param('trace_sample_rate', trace_sample_rate)
        self.show_summary = param_manager.load_param('show_summary', show_summary)
        self.data_dir = param_manager.load_param('data_dir', data_dir)
        self.collect_system_metrics = param_manager.load_param('collect_system_metrics', collect_system_metrics)

        # We save `scrubbing_patterns` and `scrubbing_callback` just so that they can be serialized and deserialized.
        self.scrubbing_patterns = scrubbing_patterns
        self.scrubbing_callback = scrubbing_callback
        self.scrubber = Scrubber(scrubbing_patterns, scrubbing_callback)

        if isinstance(console, dict):
            # This is particularly for deserializing from a dict as in _executors.py
            console = ConsoleOptions(**console)  # type: ignore
        if console is not None:
            self.console = console
        elif param_manager.load_param('console') is False:
            self.console = False
        else:
            self.console = ConsoleOptions(
                colors=param_manager.load_param('console_colors'),
                span_style=param_manager.load_param('console_span_style'),
                include_timestamps=param_manager.load_param('console_include_timestamp'),
                verbose=param_manager.load_param('console_verbose'),
            )

        if isinstance(pydantic_plugin, dict):
            # This is particularly for deserializing from a dict as in _executors.py
            pydantic_plugin = PydanticPlugin(**pydantic_plugin)  # type: ignore
        self.pydantic_plugin = pydantic_plugin or PydanticPlugin(
            record=param_manager.load_param('pydantic_plugin_record'),
            include=param_manager.load_param('pydantic_plugin_include'),
            exclude=param_manager.load_param('pydantic_plugin_exclude'),
        )
        self.fast_shutdown = fast_shutdown

        self.id_generator = id_generator or RandomIdGenerator()
        self.ns_timestamp_generator = ns_timestamp_generator or time.time_ns
        self.processors = processors
        self.default_span_processor = default_span_processor or _get_default_span_processor
        self.metric_readers = metric_readers
        self.logfire_api_session = logfire_api_session or requests.Session()
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
            data = read_toml_file(config_file)
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
        logfire_api_session: requests.Session | None = None,
        pydantic_plugin: PydanticPlugin | None = None,
        fast_shutdown: bool = False,
        scrubbing_patterns: Sequence[str] | None = None,
        scrubbing_callback: ScrubCallback | None = None,
    ) -> None:
        """Create a new LogfireConfig.

        Users should never need to call this directly, instead use `logfire.configure`.

        See `_LogfireConfigData` for parameter documentation.
        """
        # The `load_configuration` is it's own method so that it can be called on an existing config object
        # in particular the global config object.
        self._load_configuration(
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
            logfire_api_session=logfire_api_session,
            pydantic_plugin=pydantic_plugin,
            fast_shutdown=fast_shutdown,
            scrubbing_patterns=scrubbing_patterns,
            scrubbing_callback=scrubbing_callback,
        )
        # initialize with no-ops so that we don't impact OTEL's global config just because logfire is installed
        # that is, we defer setting logfire as the otel global config until `configure` is called
        self._tracer_provider = ProxyTracerProvider(trace.NoOpTracerProvider(), self)
        # note: this reference is important because the MeterProvider runs things in background threads
        # thus it "shuts down" when it's gc'ed
        self._meter_provider = ProxyMeterProvider(metrics.NoOpMeterProvider())
        self._initialized = False
        self._lock = RLock()

    # TODO(Marcelo): We should test the `load_token` method.
    @staticmethod
    def load_token(
        token: str | None = None,
        data_dir: Path = Path('.logfire'),
    ) -> tuple[str | None, LogfireCredentials | None]:  # pragma: no cover
        file_creds = LogfireCredentials.load_creds_file(data_dir)
        if token is None:
            token = os.getenv('LOGFIRE_TOKEN')
            if token is None and file_creds:
                token = file_creds.token
        return token, file_creds

    def configure(
        self,
        base_url: str | None,
        send_to_logfire: bool | Literal['if-token-present'] | None,
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
        logfire_api_session: requests.Session | None,
        pydantic_plugin: PydanticPlugin | None,
        fast_shutdown: bool = False,
        scrubbing_patterns: Sequence[str] | None = None,
        scrubbing_callback: ScrubCallback | None = None,
    ) -> None:
        with self._lock:
            self._initialized = False
            self._load_configuration(
                base_url,
                send_to_logfire,
                token,
                project_name,
                service_name,
                service_version,
                trace_sample_rate,
                console,
                show_summary,
                config_dir,
                data_dir,
                collect_system_metrics,
                id_generator,
                ns_timestamp_generator,
                processors,
                default_span_processor,
                metric_readers,
                logfire_api_session,
                pydantic_plugin,
                fast_shutdown,
                scrubbing_patterns,
                scrubbing_callback,
            )
            self.initialize()

    def initialize(self) -> ProxyTracerProvider:
        """Configure internals to start exporting traces and metrics."""
        with self._lock:
            return self._initialize()

    def _initialize(self) -> ProxyTracerProvider:
        if self._initialized:  # pragma: no branch
            return self._tracer_provider

        backup_context = attach(set_value(SUPPRESS_INSTRUMENTATION_CONTEXT_KEY, True))
        try:
            otel_resource_attributes: dict[str, Any] = {
                ResourceAttributes.SERVICE_NAME: self.service_name,
                RESOURCE_ATTRIBUTES_PACKAGE_VERSIONS: json.dumps(collect_package_info(), separators=(',', ':')),
            }
            if self.service_version:
                otel_resource_attributes[ResourceAttributes.SERVICE_VERSION] = self.service_version
            otel_resource_attributes_from_env = os.getenv(OTEL_RESOURCE_ATTRIBUTES)
            if otel_resource_attributes_from_env:
                extra_resource_attributes = {}
                for _field in otel_resource_attributes_from_env.split(','):
                    key, value = _field.split('=')
                    extra_resource_attributes[key.strip()] = value.strip()
                otel_resource_attributes.update(
                    self.scrubber.scrub(('otel_resource_attributes',), extra_resource_attributes)
                )

            resource = Resource.create(otel_resource_attributes)
            tracer_provider = SDKTracerProvider(
                sampler=ParentBasedTraceIdRatio(self.trace_sample_rate),
                resource=resource,
                id_generator=self.id_generator,
            )

            self._tracer_provider.shutdown()
            self._tracer_provider.set_provider(tracer_provider)  # do we need to shut down the existing one???

            processors: list[SpanProcessor] = []

            def add_span_processor(span_processor: SpanProcessor) -> None:
                # Most span processors added to the tracer provider should also be recorded in the `processors` list
                # so that they can be used by the final pending span processor.
                # This means that `tracer_provider.add_span_processor` should only appear in two places.
                span_processor = SpanProcessorWrapper(span_processor, self.scrubber)
                tracer_provider.add_span_processor(span_processor)
                processors.append(span_processor)

            if self.processors is not None:
                for processor in self.processors:
                    add_span_processor(processor)

            if self.console:
                if self.console.span_style == 'simple':  # pragma: no branch
                    exporter_cls = SimpleConsoleSpanExporter
                elif self.console.span_style == 'indented':  # pragma: no branch
                    exporter_cls = IndentedConsoleSpanExporter
                else:
                    assert self.console.span_style == 'show-parents'
                    exporter_cls = ShowParentsConsoleSpanExporter
                add_span_processor(
                    SimpleSpanProcessor(
                        exporter_cls(
                            colors=self.console.colors,
                            include_timestamp=self.console.include_timestamps,
                            verbose=self.console.verbose,
                        ),
                    )
                )

            credentials_from_local_file = None

            metric_readers = self.metric_readers

            if (self.send_to_logfire == 'if-token-present' and self.token is not None) or self.send_to_logfire:
                new_credentials: LogfireCredentials | None = None
                if self.token is None:
                    credentials_from_local_file = LogfireCredentials.load_creds_file(self.data_dir)
                    credentials_to_save = credentials_from_local_file
                    if not credentials_from_local_file:
                        if os.getenv('LOGFIRE_ANONYMOUS_PROJECT_ENABLED') == 'true':
                            new_credentials = LogfireCredentials.create_anonymous_project(
                                logfire_api_url=self.base_url,
                                requested_project_name=self.project_name or sanitize_project_name(self.service_name),
                                session=self.logfire_api_session,
                            )
                        else:
                            new_credentials = LogfireCredentials.initialize_project(
                                logfire_api_url=self.base_url,
                                project_name=self.project_name,
                                service_name=self.service_name,
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

                headers = {'User-Agent': f'logfire/{VERSION}', 'Authorization': self.token}
                # NOTE: Only check the backend if we didn't call it already.
                if new_credentials is None:
                    self.logfire_api_session.headers.update(headers)
                    self.check_logfire_backend()

                session = OTLPExporterHttpSession(max_body_size=OTLP_MAX_BODY_SIZE)
                session.headers.update(headers)
                otel_traces_exporter_env = os.getenv(OTEL_TRACES_EXPORTER)
                otel_traces_exporter_env = otel_traces_exporter_env.lower() if otel_traces_exporter_env else None
                if otel_traces_exporter_env is None or otel_traces_exporter_env == 'otlp':
                    span_exporter = OTLPSpanExporter(endpoint=self.traces_endpoint, session=session)
                    span_exporter = RetryFewerSpansSpanExporter(span_exporter)
                    span_exporter = FallbackSpanExporter(
                        span_exporter, FileSpanExporter(self.data_dir / DEFAULT_FALLBACK_FILE_NAME, warn=True)
                    )
                    span_exporter = RemovePendingSpansExporter(span_exporter)
                    if self.processors is None:
                        # Only add the default span processor if the user didn't specify any of their own.
                        add_span_processor(self.default_span_processor(span_exporter))

                elif otel_traces_exporter_env != 'none':
                    raise ValueError(
                        'OTEL_TRACES_EXPORTER must be "otlp", "none" or unset. Logfire does not support other exporters.'
                    )

                if metric_readers is None:
                    metric_readers = [
                        PeriodicExportingMetricReader(
                            OTLPMetricExporter(
                                endpoint=self.metrics_endpoint,
                                headers=headers,
                                preferred_temporality=METRICS_PREFERRED_TEMPORALITY,
                            )
                        )
                    ]

            tracer_provider.add_span_processor(PendingSpanProcessor(self.id_generator, tuple(processors)))

            metric_readers = metric_readers or []

            if self.show_summary and credentials_from_local_file:  # pragma: no branch
                credentials_from_local_file.print_token_summary()

            meter_provider = MeterProvider(metric_readers=metric_readers, resource=resource)
            if self.collect_system_metrics:
                configure_metrics(meter_provider)

            # we need to shut down any existing providers to avoid leaking resources (like threads)
            # but if this takes longer than 100ms you should call `logfire.shutdown` before reconfiguring
            self._meter_provider.shutdown(
                timeout_millis=200
            )  # note: this may raise an Exception if it times out, call `logfire.shutdown` first
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

    def get_meter_provider(self) -> ProxyMeterProvider:
        """Get a meter provider from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The meter provider.
        """
        if not self._initialized:  # pragma: no branch
            self.initialize()
        return self._meter_provider

    @cached_property
    def meter(self) -> metrics.Meter:
        """Get a meter from this `LogfireConfig`.

        This is used internally and should not be called by users of the SDK.

        Returns:
            The meter.
        """
        return self.get_meter_provider().get_meter('logfire', VERSION)

    def check_logfire_backend(self) -> None:
        """Check that the token is valid.

        Issue a warning if the Logfire API is unreachable, or we get a response other than 200 or 401.

        We continue unless we get a 401 and allow OTel to take of storing data locally for back-fill.

        Raises:
            LogfireConfigError: If the token is invalid.
        """
        try:
            response = self.logfire_api_session.get(urljoin(self.base_url, '/v1/health'), timeout=10)
        except requests.RequestException as e:  # pragma: no cover
            warnings.warn(f'Logfire API is unreachable, you may have trouble sending data. Error: {e}')
        else:
            if response.status_code == 401:
                raise LogfireConfigError('Invalid Logfire token.')
            elif response.status_code != 200:
                # any other status code is considered unhealthy
                warnings.warn(
                    f'Logfire API is unhealthy, you may have trouble sending data. Status code: {response.status_code}'
                )


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
    project_url: str
    """The URL for the project."""
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
            except (ValueError, OSError) as e:  # pragma: no cover
                raise LogfireConfigError(f'Invalid credentials file: {path}') from e

            try:
                # Handle legacy key
                dashboard_url = data.get('dashboard_url')
                if dashboard_url is not None:
                    data.setdefault('project_url', dashboard_url)
                return cls(**data)
            except TypeError as e:  # pragma: no cover
                raise LogfireConfigError(f'Invalid credentials file: {path} - {e}') from e

    @classmethod
    def _get_user_token(cls, logfire_api_url: str) -> str:
        if DEFAULT_FILE.is_file():  # pragma: no branch
            data = cast(DefaultFile, read_toml_file(DEFAULT_FILE))
            if is_logged_in(data, logfire_api_url):
                return data['tokens'][logfire_api_url]['token']
        raise LogfireConfigError('You are not authenticated. Please run `logfire auth` to authenticate.')

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
        user_token = cls._get_user_token(logfire_api_url=logfire_api_url)
        headers = {**COMMON_REQUEST_HEADERS, 'Authorization': user_token}
        projects_url = urljoin(logfire_api_url, '/v1/projects/')
        try:
            response = session.get(projects_url, headers=headers)
            UnexpectedResponse.raise_for_status(response)
        except requests.RequestException as e:  # pragma: no cover
            raise LogfireConfigError('Error retrieving list of projects.') from e
        return response.json()

    @classmethod
    def use_existing_project(
        cls,
        *,
        session: requests.Session,
        logfire_api_url: str,
        projects: list[dict[str, Any]],
        organization: str | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any] | None:
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
            The configured project informations.

        Raises:
            LogfireConfigError: If there was an error configuring the project.
        """
        user_token = cls._get_user_token(logfire_api_url=logfire_api_url)
        headers = {**COMMON_REQUEST_HEADERS, 'Authorization': user_token}

        # {1: (<organization_name1>, <project_name1>), 2: (<organization_name2>, <project_name2>)}
        projects_map = {str(index + 1): (p['organization_name'], p['project_name']) for index, p in enumerate(projects)}

        if (organization, project_name) not in projects_map.values():
            if not projects_map:  # pragma: no branch
                Prompt.ask('There is no project to use. Continue?', default=True)
                return None

            project_choices_str = '\n'.join([f'{index}. {item[0]}/{item[1]}' for index, item in projects_map.items()])
            selected_project_key = Prompt.ask(
                f'Please select one of the existing project number:\n' f'{project_choices_str}\n',
                choices=list(projects_map.keys()),
                default='1',
            )
            project_info_tuple = projects_map[selected_project_key]
            organization = project_info_tuple[0]
            project_name = project_info_tuple[1]

        project_write_token_url = urljoin(
            logfire_api_url,
            f'/v1/organizations/{organization}/projects/{project_name}/write-tokens/',
        )
        try:
            response = session.post(project_write_token_url, headers=headers)
            UnexpectedResponse.raise_for_status(response)
        except requests.RequestException as e:  # pragma: no cover
            raise LogfireConfigError('Error creating project write token.') from e

        return response.json()

    @classmethod
    def create_new_project(
        cls,
        *,
        session: requests.Session,
        logfire_api_url: str,
        organization: str | None = None,
        default_organization: bool = False,
        project_name: str | None = None,
        service_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a new project and configure it to be used by Logfire.

        It creates the project under the organization if both project and organization are valid.
        Otherwise, it asks the user to select organization and enter a valid project name interactively.

        Args:
            session: HTTP client session used to communicate with the Logfire API.
            logfire_api_url: The Logfire API base URL.
            organization: The organization name of the new project.
            default_organization: Whether to create the project under the user default organization.
            project_name: Name of the project.
            service_name: Name of the service.

        Returns:
            The created project informations.

        Raises:
            LogfireConfigError: If there was an error creating projects.
        """
        user_token = cls._get_user_token(logfire_api_url=logfire_api_url)
        headers = {**COMMON_REQUEST_HEADERS, 'Authorization': user_token}

        # Get user organizations
        organizations_url = urljoin(logfire_api_url, '/v1/organizations/')
        try:
            response = session.get(organizations_url, headers=headers)
            UnexpectedResponse.raise_for_status(response)
        except requests.RequestException as e:  # pragma: no cover
            raise LogfireConfigError('Error retrieving list of organizations.') from e
        organizations = [item['organization_name'] for item in response.json()]

        if organization not in organizations:
            if len(organizations) > 1:
                # Get user default organization
                account_info_url = urljoin(logfire_api_url, '/v1/account/me')
                try:
                    response = session.get(account_info_url, headers=headers)
                    UnexpectedResponse.raise_for_status(response)
                except requests.RequestException as e:  # pragma: no cover
                    raise LogfireConfigError('Error retrieving user information.') from e
                json_response = response.json()
                user_default_organization_name = json_response.get('default_organization', {}).get('organization_name')

                if default_organization and user_default_organization_name:
                    organization = user_default_organization_name
                else:
                    organization = Prompt.ask(
                        '\nTo create and use a new project, please provide the following information:\n'
                        'Select the organization to create the project in',
                        choices=organizations,
                        default=user_default_organization_name if user_default_organization_name else organizations[0],
                    )
            else:
                organization = organizations[0]
                if not default_organization:
                    Confirm.ask(
                        f'The project will be created in the organization "{organization}". Continue?', default=True
                    )

        project_name_default: str | None = project_name or (
            sanitize_project_name(service_name) if service_name else None
        )
        project_name_prompt = 'Enter the project name'
        while True:
            if not project_name:
                project_name = Prompt.ask(project_name_prompt, default=project_name_default)
            while project_name and not re.match(PROJECT_NAME_PATTERN, project_name):
                project_name = Prompt.ask(
                    "\nThe project you've entered is invalid. Valid project names:\n"
                    '  * may contain lowercase alphanumeric characters\n'
                    '  * may contain single hyphens\n'
                    '  * may not start or end with a hyphen\n\n'
                    'Enter the project name you want to use:',
                    default=project_name_default,
                )

            url = urljoin(logfire_api_url, f'/v1/projects/{organization}')
            try:
                response = session.post(url, headers=headers, json={'project_name': project_name})
                if response.status_code == 409:
                    project_name_default = ...  # type: ignore  # this means the value is required
                    project_name_prompt = (
                        '\nA project with that name already exists. Please enter a different project name'
                    )
                    project_name = None
                    continue
                if response.status_code == 422:
                    error = response.json()['detail'][0]
                    if error['loc'] == ['body', 'project_name']:  # pragma: no branch
                        project_name_default = ...  # type: ignore  # this means the value is required
                        project_name_prompt = (
                            f'\nThe project name you entered is invalid:\n'
                            f'{error["msg"]}\n'
                            f'Please enter a different project name'
                        )
                        project_name = None
                        continue
                UnexpectedResponse.raise_for_status(response)
            except requests.RequestException as e:  # pragma: no cover
                raise LogfireConfigError('Error creating new project.') from e
            else:
                return response.json()

    @classmethod
    def initialize_project(
        cls,
        *,
        logfire_api_url: str,
        project_name: str | None,
        service_name: str,
        session: requests.Session,
    ) -> Self:
        """Create a new project or use an existing project on logfire.dev requesting the given project name.

        Args:
            logfire_api_url: The Logfire API base URL.
            project_name: Name for the project.
            service_name: Name of the service.
            user_token: The user's token to use to create the new project.
            session: HTTP client session used to communicate with the Logfire API.

        Returns:
            The new credentials.

        Raises:
            LogfireConfigError: If there was an error on creating/configuring the project.
        """
        credentials: dict[str, Any] | None = None

        print(
            'No Logfire project credentials found.\n'  # TODO: Add a link to the docs about where we look
            'All data sent to Logfire must be associated with a project.\n'
        )

        projects = cls.get_user_projects(session=session, logfire_api_url=logfire_api_url)
        if projects:
            use_existing_projects = Confirm.ask(
                'Do you want to use one of your existing projects? ',
                default=True,
            )
            if use_existing_projects:  # pragma: no branch
                credentials = cls.use_existing_project(
                    session=session, logfire_api_url=logfire_api_url, projects=projects
                )

        if not credentials:
            credentials = cls.create_new_project(
                session=session,
                logfire_api_url=logfire_api_url,
                project_name=project_name,
                service_name=service_name,
            )

        try:
            result = cls(**credentials, logfire_api_url=logfire_api_url)
            Prompt.ask(
                f'Project initialized successfully. You will be able to view it at: {result.project_url}\n'
                'Press Enter to continue'
            )
            return result
        except TypeError as e:  # pragma: no cover
            raise LogfireConfigError(f'Invalid credentials, when initializing project: {e}') from e

    @classmethod
    def create_anonymous_project(
        cls,
        *,
        logfire_api_url: str,
        requested_project_name: str,
        session: requests.Session,
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
        url = urljoin(logfire_api_url, '/v1/projects/')
        try:
            params = {'requested_project_name': requested_project_name}
            response = session.post(url, params=params, headers=COMMON_REQUEST_HEADERS)
            UnexpectedResponse.raise_for_status(response)
        except requests.RequestException as e:
            raise LogfireConfigError('Error creating new project.') from e
        else:
            json_data = response.json()
            try:
                return cls(**json_data, logfire_api_url=logfire_api_url)
            except TypeError as e:
                raise LogfireConfigError(f'Invalid credentials, when creating project at {url}: {e}') from e

    def write_creds_file(self, creds_dir: Path) -> None:
        """Write a credentials file to the given path."""
        ensure_data_dir_exists(creds_dir)
        data = dataclasses.asdict(self)
        path = _get_creds_file(creds_dir)
        path.write_text(json.dumps(data, indent=2) + '\n')

    def print_token_summary(self) -> None:
        """Print a summary of the existing project."""
        if self.project_url:
            _print_summary(
                f'[bold]Logfire[/bold] project URL: [link={self.project_url} cyan]{self.project_url}[/link]',
                min_content_width=len(self.project_url),
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


def sanitize_project_name(name: str) -> str:
    """Convert `name` to a string suitable for the `requested_project_name` API parameter."""
    # Project names are limited to 50 characters, but the backend may also add 9 characters
    # if the project name already exists, so we limit it to 41 characters.
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()[:41] or 'untitled'
