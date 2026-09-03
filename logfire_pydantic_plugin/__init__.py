"""Top-level Pydantic entry-point shim for Logfire.

Must live outside the ``logfire`` package: importing any ``logfire.*`` module
executes ``logfire/__init__.py``, which eagerly pulls OpenTelemetry. Pydantic
loads every ``pydantic`` entry point on first ``SchemaValidator`` construction,
so the entry point target has to stay cheap when instrumentation is off.
"""

from __future__ import annotations

import inspect
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


def _should_load_full_plugin(plugin_settings: dict[str, Any]) -> bool:
    logfire_settings = plugin_settings.get('logfire')
    if logfire_settings and 'record' in logfire_settings:
        return logfire_settings['record'] != 'off'

    if 'logfire.integrations.pydantic' in sys.modules:
        from logfire.integrations.pydantic import get_pydantic_plugin_config

        return get_pydantic_plugin_config().record != 'off'

    config_module = sys.modules.get('logfire._internal.config')
    if config_module is not None:
        config = getattr(config_module, 'GLOBAL_CONFIG', None)
        # Config can be partially initialized while its own models are built.
        return config is not None and config.param_manager.pydantic_plugin.record != 'off'

    env_record = os.environ.get('LOGFIRE_PYDANTIC_PLUGIN_RECORD')
    if env_record:
        return env_record != 'off'
    return _file_enables_recording()


@lru_cache
def _file_enables_recording() -> bool:
    """Check the initial file setting without importing the SDK's config module."""
    config_file = Path(os.environ.get('LOGFIRE_CONFIG_DIR') or '.') / 'pyproject.toml'
    if not config_file.exists():
        return False
    if sys.version_info >= (3, 11):
        from tomllib import load
    else:
        from tomli import load
    try:
        with config_file.open('rb') as f:
            record = load(f).get('tool', {}).get('logfire', {}).get('pydantic_plugin_record')
    except Exception:
        # Delegate malformed/unreadable config to the existing SDK error handling.
        return True
    return record not in (None, 'off')


@lru_cache
def patch_pluggable_schema_validator():
    """Preserve Pydantic's cloudpickle workaround even while recording is off.

    Getting an attribute before initialization leads to infinite recursion
    trying to get _schema_validator.
    """
    from pydantic.plugin._schema_validator import PluggableSchemaValidator

    if (  # pragma: no branch
        inspect.getsource(PluggableSchemaValidator.__getattr__).strip()
        # Check that we're replacing the code that's known to be buggy.
        == """
    def __getattr__(self, name: str) -> Any:
        return getattr(self._schema_validator, name)
    """.strip()
    ):

        def __getattr__(self: Any, name: str) -> Any:
            # Missing attributes must raise AttributeError rather than recurse.
            if name == '_schema_validator':
                raise AttributeError(name)
            return getattr(self._schema_validator, name)

        PluggableSchemaValidator.__getattr__ = __getattr__


class _LazyLogfirePydanticPlugin:
    """Entry-point object: cheap to import, delegates when recording is enabled."""

    def new_schema_validator(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        from pydantic.version import VERSION

        if tuple(map(int, VERSION.split('.')[:2])) < (2, 5) or os.environ.get('LOGFIRE_PYDANTIC_RECORD') == 'off':
            return None, None, None

        patch_pluggable_schema_validator()
        plugin_settings: dict[str, Any] | None
        if len(args) >= 6:
            plugin_settings = args[5]
        else:
            plugin_settings = kwargs.get('plugin_settings')

        if not _should_load_full_plugin(plugin_settings or {}):
            return None, None, None

        from logfire.integrations.pydantic import plugin as real_plugin

        return real_plugin.new_schema_validator(*args, **kwargs)


plugin = _LazyLogfirePydanticPlugin()
