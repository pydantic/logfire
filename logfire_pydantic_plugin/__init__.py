"""Top-level Pydantic entry-point shim for Logfire.

Must live outside the ``logfire`` package: importing any ``logfire.*`` module
executes ``logfire/__init__.py``, which eagerly pulls OpenTelemetry. Pydantic
loads every ``pydantic`` entry point on first ``SchemaValidator`` construction,
so the entry point target has to stay cheap when instrumentation is off.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Set by ``logfire.integrations.pydantic.set_pydantic_plugin_config`` /
# ``instrument_pydantic`` without requiring this module to import Logfire.
_plugin_config_override: Any = None


def get_plugin_config_override() -> Any:
    return _plugin_config_override


def set_plugin_config_override(config: Any) -> None:
    global _plugin_config_override
    _plugin_config_override = config


def _record_from_plugin_settings(plugin_settings: dict[str, Any] | None) -> str | None:
    if not plugin_settings:
        return None
    logfire_settings = plugin_settings.get('logfire')
    if isinstance(logfire_settings, dict) and 'record' in logfire_settings:
        return logfire_settings['record']
    return None


def _should_load_full_plugin(plugin_settings: dict[str, Any] | None) -> bool:
    settings_record = _record_from_plugin_settings(plugin_settings)
    if settings_record is not None:
        return settings_record != 'off'

    if os.environ.get('LOGFIRE_PYDANTIC_RECORD') == 'off':
        return False

    if _plugin_config_override is not None:
        return getattr(_plugin_config_override, 'record', 'off') != 'off'

    env_record = os.environ.get('LOGFIRE_PYDANTIC_RECORD')
    if env_record not in (None, '') and env_record != 'off':
        return True

    # Default is off. Only consult GLOBAL_CONFIG if Logfire was already imported
    # (e.g. ``logfire.configure()`` loaded pydantic_plugin_record from settings).
    if 'logfire._internal.config' not in sys.modules:
        return False

    from logfire._internal.config import GLOBAL_CONFIG

    return GLOBAL_CONFIG.param_manager.pydantic_plugin.record != 'off'


class _LazyLogfirePydanticPlugin:
    """Entry-point object: cheap to import, delegates when recording is enabled."""

    def new_schema_validator(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        plugin_settings: dict[str, Any] | None
        if len(args) >= 6:
            plugin_settings = args[5]
        else:
            plugin_settings = kwargs.get('plugin_settings')

        if not _should_load_full_plugin(plugin_settings if isinstance(plugin_settings, dict) else None):
            return None, None, None

        from logfire.integrations.pydantic import plugin as real_plugin

        return real_plugin.new_schema_validator(*args, **kwargs)


plugin = _LazyLogfirePydanticPlugin()
