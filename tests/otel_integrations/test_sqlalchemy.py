from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import Integer, String

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

        SQLAlchemyInstrumentor().instrument(engine=engine, enable_commenter=True, commenter_options={})

        class Base(DeclarativeBase):
            pass

        class Record(Base):
            __tablename__ = 'records'
            id: Mapped[int] = mapped_column(primary_key=True)
            number: Mapped[int] = mapped_column(Integer, nullable=False)
            content: Mapped[str] = mapped_column(String, nullable=False)

        Base.metadata.create_all(engine)

        with Session(engine) as session:
            record = Record(id=1, number=2, content='abc')
            session.add(record)
            session.commit()
            session.delete(record)
            session.commit()

    # insert_assert(exporter.exported_spans_as_dict())
    assert exporter.exported_spans_as_dict() == [
        {
            'name': 'connect',
            'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
            'parent': None,
            'start_time': 1000000000,
            'end_time': 2000000000,
            'attributes': {
                'logfire.span_type': 'span',
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
                'db.statement': 'PRAGMA main.table_info("records")',
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
                'db.statement': 'PRAGMA temp.table_info("records")',
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
                'db.statement': '\nCREATE TABLE records (\n\tid INTEGER NOT NULL, \n\tnumber INTEGER NOT NULL, \n\tcontent VARCHAR NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n',
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
                'db.name': 'example.db',
                'db.system': 'sqlite',
            },
        },
        {
            'name': 'INSERT example.db',
            'context': {'trace_id': 6, 'span_id': 11, 'is_remote': False},
            'parent': None,
            'start_time': 11000000000,
            'end_time': 12000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'db.statement': 'INSERT INTO records (id, number, content) VALUES (?, ?, ?)',
                'db.system': 'sqlite',
                'db.name': 'example.db',
            },
        },
        {
            'name': 'connect',
            'context': {'trace_id': 7, 'span_id': 13, 'is_remote': False},
            'parent': None,
            'start_time': 13000000000,
            'end_time': 14000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'db.name': 'example.db',
                'db.system': 'sqlite',
            },
        },
        {
            'name': 'SELECT example.db',
            'context': {'trace_id': 8, 'span_id': 15, 'is_remote': False},
            'parent': None,
            'start_time': 15000000000,
            'end_time': 16000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'db.statement': 'SELECT records.id AS records_id, records.number AS records_number, records.content AS records_content \nFROM records \nWHERE records.id = ?',
                'db.system': 'sqlite',
                'db.name': 'example.db',
            },
        },
        {
            'name': 'DELETE example.db',
            'context': {'trace_id': 9, 'span_id': 17, 'is_remote': False},
            'parent': None,
            'start_time': 17000000000,
            'end_time': 18000000000,
            'attributes': {
                'logfire.span_type': 'span',
                'db.statement': 'DELETE FROM records WHERE records.id = ?',
                'db.system': 'sqlite',
                'db.name': 'example.db',
            },
        },
    ]
