from __future__ import annotations as _annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeVar

from typing_extensions import get_args, get_origin

from logfire.exporters.console import ConsoleColorsValues

from ._constants import DEFAULT_FALLBACK_FILE_NAME, LOGFIRE_BASE_URL
from .exceptions import LogfireConfigError

T = TypeVar('T')

slots_true = {'slots': True} if sys.version_info >= (3, 10) else {}

ShowSummaryValues = Literal['always', 'never', 'new-project']
"""Possible values for the `show_summary` parameter."""


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


# fmt: off
BASE_URL = ConfigParam(env_vars=['LOGFIRE_BASE_URL'], allow_file_config=True, default=LOGFIRE_BASE_URL)
SEND_TO_LOGFIRE = ConfigParam(env_vars=['LOGFIRE_SEND_TO_LOGFIRE'], allow_file_config=True, default=True, tp=bool)
TOKEN = ConfigParam(env_vars=['LOGFIRE_TOKEN'])
PROJECT_NAME = ConfigParam(env_vars=['LOGFIRE_PROJECT_NAME'], allow_file_config=True)
SERVICE_NAME = ConfigParam(env_vars=['LOGFIRE_SERVICE_NAME'], allow_file_config=True, default='unknown')
SHOW_SUMMARY = ConfigParam(env_vars=['LOGFIRE_SHOW_SUMMARY'], allow_file_config=True, default=True, tp=ShowSummaryValues)
CREDENTIALS_DIR = ConfigParam(env_vars=['LOGFIRE_CREDENTIALS_DIR'], allow_file_config=True, default='.logfire', tp=Path)
EXPORTER_FALLBACK_FILE_PATH = ConfigParam(env_vars=['LOGFIRE_EXPORTER_FALLBACK_FILE_PATH'], allow_file_config=True, default=DEFAULT_FALLBACK_FILE_NAME, tp=Path)
COLLECT_SYSTEM_METRICS = ConfigParam(env_vars=['LOGFIRE_COLLECT_SYSTEM_METRICS'], allow_file_config=True, default=True, tp=bool)
CONSOLE_ENABLED = ConfigParam(env_vars=['LOGFIRE_CONSOLE_ENABLED'], allow_file_config=True, default=True, tp=bool)
CONSOLE_COLORS = ConfigParam(env_vars=['LOGFIRE_CONSOLE_COLORS'], allow_file_config=True, default='auto', tp=ConsoleColorsValues)
CONSOLE_INDENT_SPAN = ConfigParam(env_vars=['LOGFIRE_CONSOLE_INDENT_SPAN'], allow_file_config=True, default=True, tp=bool)
CONSOLE_INCLUDE_TIMESTAMP = ConfigParam(env_vars=['LOGFIRE_CONSOLE_INCLUDE_TIMESTAMP'], allow_file_config=True, default=True, tp=bool)
CONSOLE_VERBOSE = ConfigParam(env_vars=['LOGFIRE_CONSOLE_VERBOSE'], allow_file_config=True, default=False, tp=bool)
# fmt: on

CONFIG_PARAMS = {
    'base_url': BASE_URL,
    'send_to_logfire': SEND_TO_LOGFIRE,
    'token': TOKEN,
    'project_name': PROJECT_NAME,
    'service_name': SERVICE_NAME,
    'show_summary': SHOW_SUMMARY,
    'credentials_dir': CREDENTIALS_DIR,
    'exporter_fallback_file_path': EXPORTER_FALLBACK_FILE_PATH,
    'collect_system_metrics': COLLECT_SYSTEM_METRICS,
    'console_enabled': CONSOLE_ENABLED,
    'console_colors': CONSOLE_COLORS,
    'console_indent_span': CONSOLE_INDENT_SPAN,
    'console_include_timestamp': CONSOLE_INCLUDE_TIMESTAMP,
    'console_verbose': CONSOLE_VERBOSE,
}


@dataclass(**slots_true)
class ParamManager:
    """Manage parameters for a Logfire instance."""

    config_from_file: dict[str, Any]
    """Config loaded from the config file."""

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
            if value is not None:
                return self._cast(value, name, param.tp)

        if param.allow_file_config:
            value = self.config_from_file.get(name)
            if value is not None:
                return self._cast(value, name, param.tp)

        return param.default

    def _cast(self, value: Any, name: str, tp: type[T]) -> T | None:
        if tp is str:
            return value
        if get_origin(tp) is Literal:
            return _check_literal(value, name, tp)
        if tp is bool:
            return _check_bool(value, name)  # type: ignore
        if tp is Path:
            return Path(value)  # type: ignore
        raise RuntimeError(f'Unexpected type {tp}')


def _check_literal(value: Any, name: str, tp: type[T]) -> T | None:
    if value is None:
        return None
    literals = get_args(tp)
    if value not in literals:
        raise LogfireConfigError(f'Expected {name} to be one of {literals}, got {value!r}')
    return value


def _check_bool(value: Any, name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() in ('1', 'true', 't'):
            return True
        if value.lower() in ('0', 'false', 'f'):
            return False
    raise LogfireConfigError(f'Expected {name} to be a boolean, got {value!r}')
