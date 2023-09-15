from __future__ import annotations as _annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import httpx
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from .version import VERSION

if TYPE_CHECKING:
    from typing_extensions import Self

_default_config: LogfireConfig | None = None
CREDENTIALS_FILENAME = 'logfire_credentials.json'
# LOGFIRE_API_ROOT = 'https://api.logfire.dev'
# TODO(Samuel) remove before release
LOGFIRE_API_ROOT = 'http://localhost:4318'
COMMON_REQUEST_HEADERS = {'User-Agent': f'logfire/{VERSION}'}


def configure(
    send_to_logfire: Literal['enabled', 'env', 'off'] = 'env',
    logfire_token: str | None = None,
    project_name: str | None = None,
    service_name: str | None = None,
    console_print: Literal['off', 'concise', 'verbose'] = 'concise',
    console_colors: Literal['auto', 'always', 'never'] = 'auto',
    show_summary: Literal['always', 'never', 'new-project'] = 'always',
    logfire_dir: Path = Path('.logfire'),
    logfire_api_root: str = LOGFIRE_API_ROOT,
) -> None:
    """
    Configure the logfire SDK.

    Args:
        send_to_logfire: Whether to send logs to logfire.dev, defaults to `enabled`, values have the following meaning:
            * 'enabled': logs will be send to logfire.dev, uses logfire_token, if missing will be generated
            * 'env': checks the `LOGFIRE_SEND` env var, otherwise defaults to `enabled`
            * TODO 'require-auth`: like `enabled` but requires a proper authenticated token, either free or pro
            * TODO 'require-pro`: like `enabled` but requires a pro-tier token
        logfire_token: `anon_*`, `free_*` or `pro_*` token for logfire, if `None` and `send=True` it
            will be read from the `LOGFIRE_TOKEN` env variable,
            otherwise an anon-tier token will be generated and stored in `<logfire_dir>/token`
        project_name: Name to request when creating a new project, if `None` checks `LOGFIRE_PROJECT_NAME`,
            only used when creating a project
        service_name: Name of this service, if `None` checks `LOGFIRE_SERVICE_NAME`, or the current directory name
        console_print: Whether to print to stderr and if so whether to use concise `[timestamp] {indent} [message]`
            lines or to output full JSON details of every log message
        console_colors: whether to color terminal output
        show_summary: When to print a summary of the logfire setup including a link to the dashboard
        logfire_dir: Directory to store credentials and logs in
        logfire_api_root: Root URL for the logfire API

    Returns:
        None
    """
    global _default_config

    _default_config = LogfireConfig.configure(
        send_to_logfire=send_to_logfire,
        logfire_token=logfire_token,
        project_name=project_name,
        service_name=service_name,
        console_print=console_print,
        console_colors=console_colors,
        show_summary=show_summary,
        logfire_dir=logfire_dir,
        logfire_api_root=logfire_api_root,
    )


@dataclasses.dataclass
class LogfireConfig:
    """
    Configuration for the logfire SDK.
    """

    provider: TracerProvider
    service_name: str
    internal_logging: bool = False

    @classmethod
    def configure(
        cls,
        send_to_logfire: Literal['enabled', 'env', 'off'] = 'env',
        logfire_token: str | None = None,
        project_name: str | None = None,
        service_name: str | None = None,
        console_print: Literal['off', 'concise', 'verbose'] = 'concise',
        console_colors: Literal['auto', 'always', 'never'] = 'auto',
        show_summary: Literal['always', 'never', 'new-project'] = 'always',
        logfire_dir: Path = Path('.logfire'),
        logfire_api_root: str = LOGFIRE_API_ROOT,
    ) -> Self:
        """
        Construct a new config, see the `configure` function in this module for more details.
        """
        send = get_send_value(send_to_logfire)

        if logfire_dir.exists() and not logfire_dir.is_dir():
            raise LogfireConfigError(f'`logfire_dir` {logfire_dir!r} must be a directory')

        file_creds = LogfireCredentials.load_creds_file(logfire_dir)

        service_name = service_name or get_env('LOGFIRE_SERVICE_NAME') or Path.cwd().name

        if logfire_token is None and send:
            logfire_token = get_env('LOGFIRE_TOKEN')
            if logfire_token is None and file_creds:
                logfire_token = file_creds.token

            if logfire_token is None:
                # the token is still None, we create one by asking logfire.dev to create a new project
                request_project_name = project_name or get_env('LOGFIRE_PROJECT_NAME') or service_name
                new_creds = LogfireCredentials.create_new_project(request_project_name)
                logfire_token = new_creds.token
                new_creds.write_creds_file(logfire_dir)
                if show_summary != 'never':
                    new_creds.print_new_token_summary(logfire_dir)
                # to avoid printing another summary
                file_creds = None

        if show_summary == 'always' and file_creds:
            # existing token, print summary
            file_creds.print_existing_token_summary(logfire_dir)

        exporters: list[SpanExporter] = []
        if send and logfire_token is not None:
            headers = {'Authorization': logfire_token, **COMMON_REQUEST_HEADERS}
            exporters.append(OTLPSpanExporter(endpoint=f'{logfire_api_root}/v1/traces', headers=headers))

        if console_print != 'off':
            from .exporters.console import ConsoleSpanExporter

            # TODO(Samuel) use console_colors
            exporters.append(ConsoleSpanExporter(verbose=console_print == 'verbose'))

        return cls.from_exports(*exporters, service_name=service_name)

    @classmethod
    def from_exports(cls, *exporters: SpanExporter, service_name: str, schedule_delay_millis: int = 1) -> Self:
        provider = TracerProvider(resource=Resource(attributes={'service.name': service_name}))
        for exporter in exporters:
            provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=schedule_delay_millis))
        return cls(service_name=service_name, provider=provider)

    @staticmethod
    def get_default() -> LogfireConfig:
        global _default_config
        if _default_config is None:
            configure()
            assert _default_config is not None
        return _default_config


def get_send_value(arg: str | bool) -> bool:
    if arg is True:
        arg = 'enabled'
    elif arg is False:
        arg = 'off'
    elif arg == 'env':
        arg = get_env('LOGFIRE_SEND') or 'enabled'
        if arg not in {'enabled', 'off'}:
            raise LogfireConfigError(f'Invalid value for LOGFIRE_SEND env var: {arg!r}, must be "enabled" or "off"')

    return arg == 'enabled'


def get_env(name: str) -> str | None:
    """
    Get an environment variable, returning `None` if it is not set or empty
    """
    return os.environ.get(name) or None


@dataclasses.dataclass
class LogfireCredentials:
    """
    Credentials for logfire.dev.
    """

    token: str
    project_name: str
    dashboard_url: str

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
            `LogfireCredentials`, all values will be `None` if the file does not exist
        """
        path = get_creds_file(creds_dir)
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
    def create_new_project(cls, requested_project_name: str) -> Self:
        """
        Create a new project on logfire.dev requesting the given project name.

        Args:
            requested_project_name: Name to request for the project, the actual returned name may include a
                random suffix to make it unique.

        Returns:
            `LogfireCredentials`
        """
        url = f'{LOGFIRE_API_ROOT}/v1/projects/'
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
                return cls(**json_data)
            except TypeError as e:
                raise LogfireConfigError(f'Invalid credentials, when creating project at {url}: {e}') from e

    def write_creds_file(self, creds_dir: Path) -> None:
        """
        Write a credentials file to the given path.
        """
        data = dataclasses.asdict(self)
        path = get_creds_file(creds_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')

    def print_new_token_summary(self, creds_dir: Path) -> None:
        """
        Print a summary of the new project.
        """
        creds_file = get_creds_file(creds_dir)
        print_summary(
            f"""\
A new anonymous project called **{self.project_name}** has been created on logfire.dev, to view it go

[{self.dashboard_url}]({self.dashboard_url})

But you can see project details by running `logfire whoami`, or by viewing the credentials file at `{creds_file}`.
"""
        )

    def print_existing_token_summary(self, creds_dir: Path) -> None:
        """
        Print a summary of the existing project.
        """
        if self.project_name and self.dashboard_url:
            creds_file = get_creds_file(creds_dir)
            print_summary(
                f"""\
A project called **{self.project_name}** was found and has been configured for this service, to view it go

[{self.dashboard_url}]({self.dashboard_url})

But you can see project details by running `logfire whoami`, or by viewing the credentials file at `{creds_file}`.
"""
            )


def print_summary(message: str):
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


def get_creds_file(creds_dir: Path) -> Path:
    """
    Get the path to the credentials file.
    """
    return creds_dir / CREDENTIALS_FILENAME


class LogfireConfigError(ValueError):
    """
    Error raised when there is a problem with the logfire configuration.
    """

    pass
