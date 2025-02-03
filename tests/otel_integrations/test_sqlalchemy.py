from __future__ import annotations

import importlib
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.sql import text
from sqlalchemy.types import Integer, String

import logfire
import logfire._internal.integrations.sqlalchemy
from logfire.testing import TestExporter


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
def sqlite_engine(path: Path) -> Iterator[Engine]:
    path.unlink(missing_ok=True)
    engine = create_engine(f'sqlite:///{path}')
    try:
        yield engine
    finally:
        engine.dispose()
        path.unlink()


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

    assert exporter.exported_spans_as_dict() == snapshot(
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
                },
            },
        ]
    )

    SQLAlchemyInstrumentor().uninstrument()


@contextmanager
def sqlite_async_engine(path: Path) -> Iterator[AsyncEngine]:
    path.unlink(missing_ok=True)
    engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
    try:
        yield engine
    finally:
        path.unlink()


@pytest.mark.anyio
async def test_sqlalchemy_async_instrumentation(exporter: TestExporter):
    with sqlite_async_engine(Path('example2.db')) as engine:
        logfire.instrument_sqlalchemy(engine=engine)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with AsyncSession(engine) as session:
            record = AuthRecord(id=1, number=2, content='abc')
            await session.execute(text('select * from auth_records'))
            session.add(record)
            await session.commit()
            await session.delete(record)
            await session.commit()

    assert exporter.exported_spans_as_dict() == snapshot(
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
                    'db.name': 'example2.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'PRAGMA example2.db',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA main.table_info("auth_records")',
                    'db.statement': 'PRAGMA main.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
                },
            },
            {
                'name': 'PRAGMA example2.db',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA temp.table_info("auth_records")',
                    'db.statement': 'PRAGMA temp.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
                },
            },
            {
                'name': 'CREATE example2.db',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'CREATE TABLE auth_records ( id INTEGER … t VARCHAR NOT NULL, PRIMARY KEY (id)\n)',
                    'db.statement': '\nCREATE TABLE auth_records (\n\tid INTEGER NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
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
                    'db.name': 'example2.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'select example2.db',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'select * from auth_records',
                    'db.statement': 'select * from auth_records',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
                },
            },
            {
                'name': 'INSERT example2.db',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.statement': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
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
                    'db.name': 'example2.db',
                    'db.system': 'sqlite',
                    'logfire.level_num': 5,
                },
            },
            {
                'name': 'SELECT example2.db',
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
                    'db.name': 'example2.db',
                },
            },
            {
                'name': 'DELETE example2.db',
                'context': {'trace_id': 10, 'span_id': 19, 'is_remote': False},
                'parent': None,
                'start_time': 19000000000,
                'end_time': 20000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.statement': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                    'db.name': 'example2.db',
                },
            },
        ]
    )

    SQLAlchemyInstrumentor().uninstrument()


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.sqlalchemy': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.sqlalchemy)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_sqlalchemy()` requires the `opentelemetry-instrumentation-sqlalchemy` package.
You can install this with:
    pip install 'logfire[sqlalchemy]'\
""")
