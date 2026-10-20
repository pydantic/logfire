from __future__ import annotations

import importlib
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import sqlalchemy
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry.instrumentation._semconv import _OpenTelemetrySemanticConventionStability  # type: ignore
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.sql import text
from sqlalchemy.types import Integer, String

import logfire
import logfire._internal.integrations.sqlalchemy
from logfire.testing import TestExporter

# The tests in this module share on-disk sqlite files in the working directory, so they must not
# run concurrently in different xdist workers (`--dist=loadgroup` schedules a group sequentially
# on one worker).
pytestmark = pytest.mark.xdist_group('sqlalchemy')


@pytest.fixture(autouse=True)
def uninstrument_after_test() -> Generator[None]:
    """Clean up global instrumentation even when a test fails partway through.

    A test that fails before reaching its uninstrument calls would otherwise leave sqlalchemy
    and sqlite3 globally instrumented, sending phantom spans into every later test in the same
    process through the proxy tracer provider.
    """
    yield
    if SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry:
        SQLAlchemyInstrumentor().uninstrument()
    if SQLite3Instrumentor().is_instrumented_by_opentelemetry:
        SQLite3Instrumentor().uninstrument()


class Base(DeclarativeBase):
    pass


# `auth` is in default scrubbing patterns, but `db.statement` attribute is in scrubbing SAFE_KEYS.
# So, logfire shouldn't redact `auth` in the `db.statement` attribute.
class AuthRecord(Base):
    __tablename__ = 'auth_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)


@contextmanager
def sqlite_engine(path: Path) -> Generator[Engine]:
    path.unlink(missing_ok=True)
    engine = create_engine(f'sqlite:///{path}')
    try:
        yield engine
    finally:
        engine.dispose()
        path.unlink(missing_ok=True)


def test_sqlalchemy_instrumentation(exporter: TestExporter):
    with sqlite_engine(Path('example1.db')) as engine:
        logfire.instrument_sqlalchemy(engine=engine)

        Base.metadata.create_all(engine)

        with Session(engine) as session:
            record = AuthRecord(id=1, number=2, content='abc')
            session.execute(text('select * from auth_records'))
            session.add(record)
            session.commit()
            session.delete(record)
            session.commit()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'connect',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': 'example1.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'PRAGMA example1.db',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA main.table_info("auth_records")',
                    'db.statement': 'PRAGMA main.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'PRAGMA example1.db',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA temp.table_info("auth_records")',
                    'db.statement': 'PRAGMA temp.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'CREATE example1.db',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': """\
CREATE TABLE auth_records ( id INTEGER … t VARCHAR NOT NULL, PRIMARY KEY (id)
)\
""",
                    'db.statement': '\nCREATE TABLE auth_records (\n\tid INTEGER NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'connect',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': 'example1.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'select example1.db',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'select * from auth_records',
                    'db.statement': 'select * from auth_records',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'INSERT example1.db',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.statement': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'connect',
                'context': {'trace_id': 8, 'span_id': 15, 'is_remote': False},
                'parent': None,
                'start_time': 15000000000,
                'end_time': 16000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': 'example1.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'SELECT example1.db',
                'context': {'trace_id': 9, 'span_id': 17, 'is_remote': False},
                'parent': None,
                'start_time': 17000000000,
                'end_time': 18000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SELECT auth_recor…ds_content FROM auth_records WHERE …',
                    'db.statement': 'SELECT auth_records.id AS auth_records_id, auth_records.number AS auth_records_number, auth_records.content AS auth_records_content \nFROM auth_records \nWHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'DELETE example1.db',
                'context': {'trace_id': 10, 'span_id': 19, 'is_remote': False},
                'parent': None,
                'start_time': 19000000000,
                'end_time': 20000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.statement': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                    'db.name': 'example1.db',
                    'db.operation': IsStr(),
                },
            },
        ]
    )


@pytest.mark.parametrize('parameter', ['engine', 'engines'])
def test_sqlalchemy_instrumentation_commenter(parameter: str, exporter: TestExporter):
    with sqlite_engine(Path('example3.db')) as engine:
        instrumentation_parameters: dict[str, Any] = {
            'enable_commenter': True,
            'commenter_options': {'db_framework': False},
        }
        if parameter == 'engine':
            instrumentation_parameters['engine'] = engine
        else:
            instrumentation_parameters['engines'] = [engine]

        logfire.instrument_sqlalchemy(**instrumentation_parameters)
        logfire.instrument_sqlite3()

        Base.metadata.create_all(engine)

    assert exporter.exported_spans_as_dict(include_instrumentation_scope=True) == snapshot(
        [
            {
                'name': 'PRAGMA',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlite3',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA read_uncommitted',
                    'db.system': 'sqlite',
                    'db.statement': 'PRAGMA read_uncommitted',
                },
            },
            {
                'name': 'connect',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlalchemy',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': 'example3.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'PRAGMA',
                'context': {'trace_id': 3, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 6000000000,
                'end_time': 7000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlite3',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA main.table_info("auth_records") … 000000000000002-0000000000000005-01\'*/',
                    'db.system': 'sqlite',
                    'db.statement': "PRAGMA main.table_info(\"auth_records\") /*db_driver='pysqlite',traceparent='00-00000000000000000000000000000002-0000000000000005-01'*/",
                },
            },
            {
                'name': 'PRAGMA example3.db',
                'context': {'trace_id': 2, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 8000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlalchemy',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA main.table_info("auth_records")',
                    'db.statement': 'PRAGMA main.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example3.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'PRAGMA',
                'context': {'trace_id': 5, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 10000000000,
                'end_time': 11000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlite3',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA temp.table_info("auth_records") … 000000000000004-0000000000000009-01\'*/',
                    'db.system': 'sqlite',
                    'db.statement': "PRAGMA temp.table_info(\"auth_records\") /*db_driver='pysqlite',traceparent='00-00000000000000000000000000000004-0000000000000009-01'*/",
                },
            },
            {
                'name': 'PRAGMA example3.db',
                'context': {'trace_id': 4, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 12000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlalchemy',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA temp.table_info("auth_records")',
                    'db.statement': 'PRAGMA temp.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example3.db',
                    'db.operation': IsStr(),
                },
            },
            {
                'name': 'CREATE',
                'context': {'trace_id': 7, 'span_id': 15, 'is_remote': False},
                'parent': None,
                'start_time': 14000000000,
                'end_time': 15000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlite3',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': "CREATE TABLE auth_records ( id INTEGER … 000000000000006-000000000000000d-01'*/",
                    'db.system': 'sqlite',
                    'db.statement': """\

CREATE TABLE auth_records (
	id INTEGER NOT NULL, \n\
	number INTEGER NOT NULL, \n\
	content VARCHAR NOT NULL, \n\
	PRIMARY KEY (id)
) /*db_driver='pysqlite',traceparent='00-00000000000000000000000000000006-000000000000000d-01'*/\
""",
                },
            },
            {
                'name': 'CREATE example3.db',
                'context': {'trace_id': 6, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 16000000000,
                'instrumentation_scope': 'opentelemetry.instrumentation.sqlalchemy',
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': """\
CREATE TABLE auth_records ( id INTEGER … t VARCHAR NOT NULL, PRIMARY KEY (id)
)\
""",
                    'db.statement': """\

CREATE TABLE auth_records (
	id INTEGER NOT NULL, \n\
	number INTEGER NOT NULL, \n\
	content VARCHAR NOT NULL, \n\
	PRIMARY KEY (id)
)

""",
                    'db.system': 'sqlite',
                    'db.name': 'example3.db',
                    'db.operation': IsStr(),
                },
            },
        ]
    )


@contextmanager
def sqlite_async_engine(path: Path) -> Generator[AsyncEngine]:
    path.unlink(missing_ok=True)
    engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    try:
        yield engine
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.anyio
@pytest.mark.parametrize('parameter', ['engine', 'engines'])
async def test_sqlalchemy_async_instrumentation(parameter: str, exporter: TestExporter, tmp_path: Path):
    with sqlite_async_engine(tmp_path / f'test_{parameter}.db') as engine:
        if parameter == 'engine':
            logfire.instrument_sqlalchemy(engine=engine)
        else:
            logfire.instrument_sqlalchemy(engines=[engine])

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSession(engine) as session:
            record = AuthRecord(id=1, number=2, content='abc')
            await session.execute(text('select * from auth_records'))
            session.add(record)
            await session.commit()
            await session.delete(record)
            await session.commit()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    for span in spans:
        attributes = span['attributes']
        if 'db.statement' not in attributes:
            continue

        # SQLAlchemy async spans may include the database path in the span name and db attributes.
        db_name = attributes.pop('db.name', None)
        db_operation = attributes.pop('db.operation', None)
        if db_name is None:
            assert db_operation is None
            continue

        assert isinstance(db_name, str)
        assert isinstance(span['name'], str)
        assert span['name'].endswith(f' {db_name}')
        assert db_operation == span['name']
        span['name'] = span['name'][: -(len(db_name) + 1)]

    assert spans == snapshot(
        [
            {
                'name': 'connect',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': IsStr(regex=r'.*test_(engine|engines)\.db$'),
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'PRAGMA',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA main.table_info("auth_records")',
                    'db.statement': 'PRAGMA main.table_info("auth_records")',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'PRAGMA',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA temp.table_info("auth_records")',
                    'db.statement': 'PRAGMA temp.table_info("auth_records")',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'CREATE',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'CREATE TABLE auth_records ( id INTEGER … t VARCHAR NOT NULL, PRIMARY KEY (id)\n)',
                    'db.statement': '\nCREATE TABLE auth_records (\n\tid INTEGER NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'connect',
                'context': {'trace_id': 5, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 10000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': IsStr(regex=r'.*test_(engine|engines)\.db$'),
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'select',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'select * from auth_records',
                    'db.statement': 'select * from auth_records',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'INSERT',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.statement': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'connect',
                'context': {'trace_id': 8, 'span_id': 15, 'is_remote': False},
                'parent': None,
                'start_time': 15000000000,
                'end_time': 16000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.name': IsStr(regex=r'.*test_(engine|engines)\.db$'),
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'SELECT',
                'context': {'trace_id': 9, 'span_id': 17, 'is_remote': False},
                'parent': None,
                'start_time': 17000000000,
                'end_time': 18000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SELECT auth_recor…ds_content FROM auth_records WHERE …',
                    'db.statement': """\
SELECT auth_records.id AS auth_records_id, auth_records.number AS auth_records_number, auth_records.content AS auth_records_content \nFROM auth_records \nWHERE auth_records.id = ?\
""",
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'DELETE',
                'context': {'trace_id': 10, 'span_id': 19, 'is_remote': False},
                'parent': None,
                'start_time': 19000000000,
                'end_time': 20000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.statement': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                },
            },
        ]
    )


def test_sqlalchemy_instrumentation_stable_semconv(exporter: TestExporter):
    """With the stable database semantic conventions, the query is in `db.query.text` rather than `db.statement`."""
    with mock.patch.dict('os.environ', {'OTEL_SEMCONV_STABILITY_OPT_IN': 'database'}):
        # Pick up the new value of OTEL_SEMCONV_STABILITY_OPT_IN
        _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore
        try:
            with sqlite_engine(Path('example_stable_semconv.db')) as engine:
                logfire.instrument_sqlalchemy(engine=engine)
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            'select name, type, tbl_name, rootpage, sql from sqlite_master '
                            "where type = 'table' and name = 'auth_records'"
                        )
                    )
        finally:
            # Now let other tests get the original value set in conftest.py
            _OpenTelemetrySemanticConventionStability._initialized = False  # type: ignore

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'connect',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'connect',
                    'db.namespace': 'example_stable_semconv.db',
                    'db.system.name': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'select example_stable_semconv.db',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SELECT name, type…tpage, sql FROM sqlite_master WHERE …',
                    'db.namespace': 'example_stable_semconv.db',
                    'db.query.text': "select name, type, tbl_name, rootpage, sql from sqlite_master where type = 'table' and name = 'auth_records'",
                    'db.system.name': 'sqlite',
                    'db.operation.name': IsStr(),
                },
            },
        ]
    )


def _sqlalchemy_range_excluding_installed(self: object) -> tuple[str, ...]:
    return ('sqlalchemy < 1.0',)


@contextmanager
def memory_sqlite_engine() -> Generator[Engine]:
    """In-memory engine that closes pooled sqlite connections and drops instrumentation."""
    engine = create_engine('sqlite:///:memory:')
    try:
        yield engine
    finally:
        engine.dispose()
        if SQLAlchemyInstrumentor().is_instrumented_by_opentelemetry:
            SQLAlchemyInstrumentor().uninstrument()


def test_unsupported_sqlalchemy_version_is_not_silent(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch) -> None:
    """A SQLAlchemy version outside the instrumentor's range must not look instrumented.

    opentelemetry-instrumentation-sqlalchemy (for example 0.66b1) declares
    `sqlalchemy >= 1.0.0, < 2.1.0`. On SQLAlchemy 2.1 it logs that conflict and
    returns before attaching listeners, so `instrument_sqlalchemy()` used to
    return while queries produced no spans.
    """
    monkeypatch.setattr(SQLAlchemyInstrumentor, 'instrumentation_dependencies', _sqlalchemy_range_excluding_installed)
    with memory_sqlite_engine() as engine:
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_sqlalchemy(engine=engine)

        message = str(exc_info.value)
        assert message == (
            '`logfire.instrument_sqlalchemy()` could not instrument SQLAlchemy.\n'
            'This instrumentation only instruments "sqlalchemy < 1.0", '
            f'but currently installed version ("sqlalchemy {sqlalchemy.__version__}") falls outside of that range, '
            'so nothing can be instrumented.\n'
            'Install a SQLAlchemy version in that range, or upgrade '
            '`opentelemetry-instrumentation-sqlalchemy` if a newer release supports this version.\n'
            'You can upgrade the instrumentation with:\n'
            "    pip install -U 'logfire[sqlalchemy]'\n"
            'Pass `skip_dep_check=True` to bypass this check. '
            'That may produce no spans or errors if the version really is incompatible.'
        )
        with engine.connect() as conn:
            conn.execute(text('select 1'))
        assert exporter.exported_spans == []


def test_skip_dep_check_still_instruments_sqlalchemy(exporter: TestExporter, monkeypatch: pytest.MonkeyPatch) -> None:
    """`skip_dep_check` is forwarded, so callers can instrument outside the declared range."""
    monkeypatch.setattr(SQLAlchemyInstrumentor, 'instrumentation_dependencies', _sqlalchemy_range_excluding_installed)
    with memory_sqlite_engine() as engine:
        logfire.instrument_sqlalchemy(engine=engine, skip_dep_check=True)
        with engine.connect() as conn:
            conn.execute(text('select 1'))
        assert exporter.exported_spans


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.sqlalchemy': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.sqlalchemy)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_sqlalchemy()` requires the `opentelemetry-instrumentation-sqlalchemy` package.
You can install this with:
    pip install 'logfire[sqlalchemy]'\
""")
