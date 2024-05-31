import importlib
import sqlite3
from unittest import mock

import pytest
from inline_snapshot import snapshot

import logfire
import logfire._internal
import logfire._internal.integrations
import logfire._internal.integrations.sqlite3
from logfire import instrument_sqlite3
from logfire._internal.integrations.sqlite3 import SQLite3Instrumentor


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.sqlite3': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.sqlite3)
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_sqlite3()` requires the `opentelemetry-instrumentation-sqlite3` package.
You can install this with:
    pip install 'logfire[sqlite3]'\
""")


def test_instrument_sqlite3():
    original_connect = sqlite3.connect

    instrument_sqlite3()
    assert original_connect is not sqlite3.connect
    SQLite3Instrumentor().uninstrument()  # type: ignore
    assert original_connect is sqlite3.connect
