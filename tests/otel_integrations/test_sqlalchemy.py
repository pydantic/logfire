from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from inline_snapshot import snapshot
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.sql import text
from sqlalchemy.types import Integer, String

import logfire
from logfire.testing import TestExporter


@contextmanager
def sqlite_engine(path: Path) -> Iterator[Engine]:
    path.unlink(missing_ok=True)
    engine = create_engine(f'sqlite:///{path}')
    try:
        yield engine
    finally:
        path.unlink()


def test_sqlalchemy_instrumentation(exporter: TestExporter):
    with sqlite_engine(Path('example.db')) as engine:
        # Need to  ensure this import happens _after_ importing sqlalchemy
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        logfire.instrument_sqlalchemy(engine=engine, enable_commenter=True, commenter_options={})

        class Base(DeclarativeBase):
            pass

        # `auth` is in default scrubbing patterns, but `db.statement` attribute is in scrubbing SAFE_KEYS.
        # So, logfire shouldn't redact `auth` in the `db.statement` attribute.
        class AuthRecord(Base):
            __tablename__ = 'auth_records'
            id: Mapped[int] = mapped_column(primary_key=True)
            number: Mapped[int] = mapped_column(Integer, nullable=False)
            content: Mapped[str] = mapped_column(String, nullable=False)

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
                    'db.name': 'example.db',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'PRAGMA example.db',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA example.db',
                    'db.statement': 'PRAGMA main.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
                },
            },
            {
                'name': 'PRAGMA example.db',
                'context': {'trace_id': 3, 'span_id': 5, 'is_remote': False},
                'parent': None,
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'PRAGMA example.db',
                    'db.statement': 'PRAGMA temp.table_info("auth_records")',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
                },
            },
            {
                'name': 'CREATE example.db',
                'context': {'trace_id': 4, 'span_id': 7, 'is_remote': False},
                'parent': None,
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'CREATE example.db',
                    'db.statement': '\nCREATE TABLE auth_records (\n\tid INTEGER NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
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
                    'db.name': 'example.db',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'select example.db',
                'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
                'parent': None,
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'select example.db',
                    'db.statement': 'select * from auth_records',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
                },
            },
            {
                'name': 'INSERT example.db',
                'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
                'parent': None,
                'start_time': 13000000000,
                'end_time': 14000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'INSERT example.db',
                    'db.statement': 'INSERT INTO auth_records (id, number, content) VALUES (?, ?, ?)',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
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
                    'db.name': 'example.db',
                    'db.system': 'sqlite',
                },
            },
            {
                'name': 'SELECT example.db',
                'context': {'trace_id': 9, 'span_id': 17, 'is_remote': False},
                'parent': None,
                'start_time': 17000000000,
                'end_time': 18000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SELECT example.db',
                    'db.statement': 'SELECT auth_records.id AS auth_records_id, auth_records.number AS auth_records_number, auth_records.content AS auth_records_content \nFROM auth_records \nWHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
                },
            },
            {
                'name': 'DELETE example.db',
                'context': {'trace_id': 10, 'span_id': 19, 'is_remote': False},
                'parent': None,
                'start_time': 19000000000,
                'end_time': 20000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'DELETE example.db',
                    'db.statement': 'DELETE FROM auth_records WHERE auth_records.id = ?',
                    'db.system': 'sqlite',
                    'db.name': 'example.db',
                },
            },
        ]
    )

    SQLAlchemyInstrumentor().uninstrument()  # type: ignore[reportUnknownMemberType]
