from __future__ import annotations

import importlib
from unittest import mock

import pytest
from inline_snapshot import snapshot
from pymongo import monitoring

import logfire
import logfire._internal.integrations.pymongo


# TODO real test
def test_instrument_pymongo():
    command_listeners = monitoring._LISTENERS.command_listeners  # type: ignore
    assert len(command_listeners) == 0  # type: ignore
    logfire.instrument_pymongo()
    assert len(command_listeners) == 1  # type: ignore


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.pymongo': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.pymongo)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_pymongo()` requires the `opentelemetry-instrumentation-pymongo` package.
You can install this with:
    pip install 'logfire[pymongo]'\
""")
