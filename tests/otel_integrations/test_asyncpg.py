import asyncpg
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

import logfire


def test_asyncpg() -> None:
    original_execute = asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]
    logfire.instrument_asyncpg()
    assert original_execute is not asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]
    AsyncPGInstrumentor().uninstrument()  # type: ignore[reportUnknownMemberType]
    assert original_execute is asyncpg.Connection.execute  # type: ignore[reportUnknownMemberType]
