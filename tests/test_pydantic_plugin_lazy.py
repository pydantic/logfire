"""Ensure the Pydantic entry point stays cheap when instrumentation is off."""

from __future__ import annotations

import importlib
import sys


def test_entry_point_module_does_not_import_logfire_sdk():
    # Simulate a fresh process where only the entry-point shim is loaded.
    doomed = [
        name
        for name in list(sys.modules)
        if name == 'logfire'
        or name.startswith('logfire.')
        or name == 'logfire_pydantic_plugin'
        or name.startswith('logfire_pydantic_plugin.')
        or name.startswith('opentelemetry')
    ]
    for name in doomed:
        del sys.modules[name]

    mod = importlib.import_module('logfire_pydantic_plugin')
    assert 'logfire' not in sys.modules
    assert 'logfire.integrations.pydantic' not in sys.modules
    assert not any(name.startswith('opentelemetry') for name in sys.modules)

    # Default path: recording is off → no heavy import.
    assert mod.plugin.new_schema_validator(None, None, None, None, None, {}) == (None, None, None)
    assert 'logfire' not in sys.modules


def test_entry_point_loads_full_plugin_when_env_enables_recording(monkeypatch):
    monkeypatch.setenv('LOGFIRE_PYDANTIC_RECORD', 'all')
    for name in list(sys.modules):
        if name == 'logfire_pydantic_plugin' or name.startswith('logfire_pydantic_plugin.'):
            del sys.modules[name]

    mod = importlib.import_module('logfire_pydantic_plugin')
    assert mod._should_load_full_plugin({}) is True
