import importlib
from unittest import mock

import asyncpg
import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

import logfire
import logfire._internal.integrations.asyncpg


def test_asyncpg() -> None:
    original_execute = asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]
    logfire.instrument_asyncpg()
    assert original_execute is not asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]
    AsyncPGInstrumentor().uninstrument()
    assert original_execute is asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.asyncpg': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.asyncpg)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_asyncpg()` requires the `opentelemetry-instrumentation-asyncpg` package.
You can install this with:
    pip install 'logfire[asyncpg]'\
""")
