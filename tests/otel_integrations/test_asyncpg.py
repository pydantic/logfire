import asyncpg
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

import logfire


def test_asyncpg():
    original_execute = asyncpg.Connection.execute
    logfire.instrument_asyncpg()
    assert original_execute is not asyncpg.Connection.execute
    AsyncPGInstrumentor().uninstrument()
    assert original_execute is asyncpg.Connection.execute
