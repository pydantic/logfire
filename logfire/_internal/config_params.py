from __future__ import annotations as _annotations

import os
import sys
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any, Callable, Literal, Set, TypeVar

from opentelemetry.sdk.environment_variables import OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME
from typing_extensions import get_args, get_origin

from logfire.exceptions import LogfireConfigError

from . import config
from .constants import LOGFIRE_BASE_URL, LevelName
from .exporters.console import ConsoleColorsValues
from .utils import read_toml_file

try:
    import opentelemetry.instrumentation.system_metrics  # noqa: F401 # type: ignore

    COLLECT_SYSTEM_METRICS_DEFAULT = True
except ImportError:  # pragma: no cover
    COLLECT_SYSTEM_METRICS_DEFAULT = False  # type: ignore


T = TypeVar('T')

slots_true = {'slots': True} if sys.version_info >= (3, 10) else {}

PydanticPluginRecordValues = Literal['off', 'all', 'failure', 'metrics']
"""Possible values for the `pydantic_plugin_record` parameter."""


@dataclass(**slots_true)
class ConfigParam:
    """A parameter that can be configured for a Logfire instance."""

    env_vars: list[str]
    """Environment variables to check for the parameter."""
    allow_file_config: bool = False
    """Whether the parameter can be set in the config file."""
    default: Any = None
    """Default value if no other value is found."""
    tp: Any = str
    """Type of the parameter."""


@dataclass
class _DefaultCallback:
    """A default value that is computed at runtime.

    A good example is when we want to check if we are running under pytest and set a default value based on that.
    """

    callback: Callable[[], Any]


_send_to_logfire_default = _DefaultCallback(lambda: 'PYTEST_CURRENT_TEST' not in os.environ)
"""When running under pytest, don't send spans to Logfire by default."""

# fmt: off
BASE_URL = ConfigParam(env_vars=['LOGFIRE_BASE_URL', OTEL_EXPORTER_OTLP_ENDPOINT], allow_file_config=True, default=LOGFIRE_BASE_URL)
"""Use to set the base URL of the Logfire backend."""
SEND_TO_LOGFIRE = ConfigParam(env_vars=['LOGFIRE_SEND_TO_LOGFIRE'], allow_file_config=True, default=_send_to_logfire_default, tp=bool)
"""Whether to send spans to Logfire."""
TOKEN = ConfigParam(env_vars=['LOGFIRE_TOKEN'])
"""Token for the Logfire API."""
PROJECT_NAME = ConfigParam(env_vars=['LOGFIRE_PROJECT_NAME'], allow_file_config=True)
"""Name of the project. Project name accepts a string value containing alphanumeric characters and hyphens (-). The hyphen character must not be located at the beginning or end of the string and should appear in between alphanumeric characters."""
SERVICE_NAME = ConfigParam(env_vars=['LOGFIRE_SERVICE_NAME', OTEL_SERVICE_NAME], allow_file_config=True, default='')
"""Name of the service emitting spans. For further details, please refer to the [Service section](https://opentelemetry.io/docs/specs/semconv/resource/#service)."""
SERVICE_VERSION = ConfigParam(env_vars=['LOGFIRE_SERVICE_VERSION', 'OTEL_SERVICE_VERSION'], allow_file_config=True)
"""Version number of the service emitting spans. For further details, please refer to the [Service section](https://opentelemetry.io/docs/specs/semconv/resource/#service)."""
SHOW_SUMMARY = ConfigParam(env_vars=['LOGFIRE_SHOW_SUMMARY'], allow_file_config=True, default=True, tp=bool)
"""Whether to show the summary when a new project is created."""
CREDENTIALS_DIR = ConfigParam(env_vars=['LOGFIRE_CREDENTIALS_DIR'], allow_file_config=True, default='.logfire', tp=Path)
"""The directory where to store the configuration file."""
COLLECT_SYSTEM_METRICS = ConfigParam(env_vars=['LOGFIRE_COLLECT_SYSTEM_METRICS'], allow_file_config=True, default=COLLECT_SYSTEM_METRICS_DEFAULT, tp=bool)
"""Whether to collect system metrics."""
CONSOLE = ConfigParam(env_vars=['LOGFIRE_CONSOLE'], allow_file_config=True, default=True, tp=bool)
"""Whether to enable/disable the console exporter."""
CONSOLE_COLORS = ConfigParam(env_vars=['LOGFIRE_CONSOLE_COLORS'], allow_file_config=True, default='auto', tp=ConsoleColorsValues)
"""Whether to use colors in the console."""
CONSOLE_SPAN_STYLE = ConfigParam(env_vars=['LOGFIRE_CONSOLE_SPAN_STYLE'], allow_file_config=True, default='show-parents', tp=Literal['simple', 'indented', 'show-parents'])
"""How spans are shown in the console.

* `'simple'`: Spans are shown as a flat list, not indented.
* `'indented'`: Spans are shown as a tree, indented based on how many parents they have.
* `'show-parents'`: Spans are shown intended, when spans are interleaved parent spans are printed again to
  give the best context."""
CONSOLE_INCLUDE_TIMESTAMP = ConfigParam(env_vars=['LOGFIRE_CONSOLE_INCLUDE_TIMESTAMP'], allow_file_config=True, default=True, tp=bool)
"""Whether to include the timestamp in the console."""
CONSOLE_VERBOSE = ConfigParam(env_vars=['LOGFIRE_CONSOLE_VERBOSE'], allow_file_config=True, default=False, tp=bool)
"""Whether to log in verbose mode in the console."""
CONSOLE_MIN_LOG_LEVEL = ConfigParam(env_vars=['LOGFIRE_CONSOLE_MIN_LOG_LEVEL'], allow_file_config=True, default='info', tp=LevelName)
"""Minimum log level to show in the console."""
PYDANTIC_PLUGIN_RECORD = ConfigParam(env_vars=['LOGFIRE_PYDANTIC_PLUGIN_RECORD'], allow_file_config=True, default='off', tp=PydanticPluginRecordValues)
"""Whether instrument Pydantic validation.."""
PYDANTIC_PLUGIN_INCLUDE = ConfigParam(env_vars=['LOGFIRE_PYDANTIC_PLUGIN_INCLUDE'], allow_file_config=True, default=set(), tp=Set[str])
"""Set of items that should be included in Logfire Pydantic plugin instrumentation."""
PYDANTIC_PLUGIN_EXCLUDE = ConfigParam(env_vars=['LOGFIRE_PYDANTIC_PLUGIN_EXCLUDE'], allow_file_config=True, default=set(), tp=Set[str])
"""Set of items that should be excluded from Logfire Pydantic plugin instrumentation."""
TRACE_SAMPLE_RATE = ConfigParam(env_vars=['LOGFIRE_TRACE_SAMPLE_RATE', 'OTEL_TRACES_SAMPLER_ARG'], allow_file_config=True, default=1.0, tp=float)
"""Default sampling ratio for traces. Can be overridden by the `logfire.sample_rate` attribute of a span."""
INSPECT_ARGUMENTS = ConfigParam(env_vars=['LOGFIRE_INSPECT_ARGUMENTS'], allow_file_config=True, default=sys.version_info[:2] >= (3, 11), tp=bool)
"""Whether to enable the f-string magic feature. On by default for Python 3.11 and above."""
IGNORE_NO_CONFIG = ConfigParam(env_vars=['LOGFIRE_IGNORE_NO_CONFIG'], allow_file_config=True, default=False, tp=bool)
"""Whether to show a warning message if logire if used without calling logfire.configure()"""
# fmt: on

CONFIG_PARAMS = {
    'base_url': BASE_URL,
    'send_to_logfire': SEND_TO_LOGFIRE,
    'token': TOKEN,
    'project_name': PROJECT_NAME,
    'service_name': SERVICE_NAME,
    'service_version': SERVICE_VERSION,
    'trace_sample_rate': TRACE_SAMPLE_RATE,
    'show_summary': SHOW_SUMMARY,
    'data_dir': CREDENTIALS_DIR,
    'collect_system_metrics': COLLECT_SYSTEM_METRICS,
    'console': CONSOLE,
    'console_colors': CONSOLE_COLORS,
    'console_span_style': CONSOLE_SPAN_STYLE,
    'console_include_timestamp': CONSOLE_INCLUDE_TIMESTAMP,
    'console_verbose': CONSOLE_VERBOSE,
    'console_min_log_level': CONSOLE_MIN_LOG_LEVEL,
    'pydantic_plugin_record': PYDANTIC_PLUGIN_RECORD,
    'pydantic_plugin_include': PYDANTIC_PLUGIN_INCLUDE,
    'pydantic_plugin_exclude': PYDANTIC_PLUGIN_EXCLUDE,
    'inspect_arguments': INSPECT_ARGUMENTS,
    'ignore_no_config': IGNORE_NO_CONFIG,
}


@dataclass
class ParamManager:
    """Manage parameters for a Logfire instance."""

    config_from_file: dict[str, Any]
    """Config loaded from the config file."""

    @classmethod
    def create(cls, config_dir: Path | None = None) -> ParamManager:
        config_dir = Path(config_dir or os.getenv('LOGFIRE_CONFIG_DIR') or '.')
        config_from_file = _load_config_from_file(config_dir)
        return ParamManager(config_from_file=config_from_file)

    def load_param(self, name: str, runtime: Any = None) -> Any:
        """Load a parameter given its name.

        The parameter is loaded in the following order:
        1. From the runtime argument, if provided.
        2. From the environment variables.
        3. From the config file, if allowed.

        If none of the above is found, the default value is returned.

        Args:
            name: Name of the parameter.
            runtime: Value provided at runtime.

        Returns:
            The value of the parameter.
        """
        if runtime is not None:
            return runtime

        param = CONFIG_PARAMS[name]
        for env_var in param.env_vars:
            value = os.getenv(env_var)
            # `None` (unset) and `''` (empty string) are generally considered the same
            if value:
                return self._cast(value, name, param.tp)

        if param.allow_file_config:
            value = self.config_from_file.get(name)
            if value is not None:
                return self._cast(value, name, param.tp)

        if isinstance(param.default, _DefaultCallback):
            return self._cast(param.default.callback(), name, param.tp)
        return self._cast(param.default, name, param.tp)

    @cached_property
    def pydantic_plugin(self):
        return config.PydanticPlugin(
            record=self.load_param('pydantic_plugin_record'),
            include=self.load_param('pydantic_plugin_include'),
            exclude=self.load_param('pydantic_plugin_exclude'),
        )

    def _cast(self, value: Any, name: str, tp: type[T]) -> T | None:
        if tp is str:
            return value
        if get_origin(tp) is Literal:
            return _check_literal(value, name, tp)
        if tp is bool:
            return _check_bool(value, name)  # type: ignore
        if tp is float:
            return float(value)  # type: ignore
        if tp is Path:
            return Path(value)  # type: ignore
        if get_origin(tp) is set and get_args(tp) == (str,):  # pragma: no branch
            return _extract_set_of_str(value)  # type: ignore
        raise RuntimeError(f'Unexpected type {tp}')  # pragma: no cover


@lru_cache
def default_param_manager():
    return ParamManager.create()


def _check_literal(value: Any, name: str, tp: type[T]) -> T | None:
    if value is None:  # pragma: no cover
        return None
    literals = get_args(tp)
    if value not in literals:
        raise LogfireConfigError(f'Expected {name} to be one of {literals}, got {value!r}')
    return value


def _check_bool(value: Any, name: str) -> bool | None:
    if value is None:  # pragma: no cover
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):  # pragma: no branch
        if value.lower() in ('1', 'true', 't'):
            return True
        if value.lower() in ('0', 'false', 'f'):  # pragma: no branch
            return False
    raise LogfireConfigError(f'Expected {name} to be a boolean, got {value!r}')  # pragma: no cover


def _extract_set_of_str(value: str | set[str]) -> set[str]:
    return set(map(str.strip, value.split(','))) if isinstance(value, str) else value


def _load_config_from_file(config_dir: Path) -> dict[str, Any]:
    config_file = config_dir / 'pyproject.toml'
    if not config_file.exists():
        return {}
    try:
        data = read_toml_file(config_file)
        return data.get('tool', {}).get('logfire', {})
    except Exception as exc:
        raise LogfireConfigError(f'Invalid config file: {config_file}') from exc
