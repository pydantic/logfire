from __future__ import annotations

import importlib
from unittest import mock

import pymssql
import pytest
from dirty_equals import IsInt
from inline_snapshot import snapshot
from opentelemetry.instrumentation.pymssql import PyMSSQLInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from testcontainers.mssql import SqlServerContainer

import logfire
import logfire._internal.integrations.pymssql
from logfire.testing import TestExporter


@pytest.fixture
def pymssql_instrumentor():
    instrumentor = PyMSSQLInstrumentor()
    yield instrumentor
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


@pytest.fixture(scope='module')
def mssql_container():
    with SqlServerContainer('mcr.microsoft.com/mssql/server:2022-latest').with_kwargs(
        platform='linux/amd64'
    ) as container:
        yield container


def test_pymssql_instrumentation_with_sql_server(
    exporter: TestExporter,
    pymssql_instrumentor: PyMSSQLInstrumentor,
    mssql_container: SqlServerContainer,
) -> None:
    logfire.instrument_pymssql()

    with pymssql.connect(
        server=mssql_container.get_container_host_ip(),
        port=mssql_container.get_exposed_port(1433),
        user=mssql_container.username,
        password=mssql_container.password,
        database=mssql_container.dbname,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 42')
            assert cursor.fetchone() == (42,)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'SELECT',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'SELECT 42',
                    'db.system': 'mssql',
                    'db.name': 'tempdb',
                    'db.statement': 'SELECT 42',
                    'db.user': 'SA',
                    'net.peer.name': 'localhost',
                    'server.address': 'localhost',
                    'net.peer.port': IsInt(),
                    'server.port': IsInt(),
                },
            }
        ]
    )


def test_pymssql_instrumentation(exporter: TestExporter, pymssql_instrumentor: PyMSSQLInstrumentor) -> None:
    cursor = mock.MagicMock()
    connection = mock.MagicMock()
    connection.cursor.return_value = cursor

    with mock.patch.object(pymssql, 'connect', return_value=connection) as connect:
        logfire.instrument_pymssql()
        instrumented_connection = pymssql.connect(
            server='db.example.com', port='1433', user='app-user', password='secret', database='orders'
        )
        with logfire.span('parent'):
            instrumented_connection.cursor().execute('SELECT * FROM orders WHERE id = %s', (42,))

        connect.assert_called_once_with(
            server='db.example.com', port='1433', user='app-user', password='secret', database='orders'
        )
        cursor.execute.assert_called_once_with('SELECT * FROM orders WHERE id = %s', (42,))

        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': 'SELECT',
                    'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 2000000000,
                    'end_time': 3000000000,
                    'attributes': {
                        'logfire.span_type': 'span',
                        'logfire.msg': 'SELECT * FROM orders WHERE id = %s',
                        'db.system': 'mssql',
                        'db.name': 'orders',
                        'db.statement': 'SELECT * FROM orders WHERE id = %s',
                        'db.user': 'app-user',
                        'net.peer.name': 'db.example.com',
                        'server.address': 'db.example.com',
                        'net.peer.port': 1433,
                        'server.port': 1433,
                    },
                },
                {
                    'name': 'parent',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 4000000000,
                    'attributes': {
                        'code.filepath': 'test_pymssql.py',
                        'code.lineno': 123,
                        'code.function': 'test_pymssql_instrumentation',
                        'logfire.msg_template': 'parent',
                        'logfire.span_type': 'span',
                        'logfire.msg': 'parent',
                    },
                },
            ]
        )

        pymssql_instrumentor.uninstrument()
        pymssql.connect(server='db.example.com').cursor().execute('SELECT 2')
        assert len(exporter.exported_spans_as_dict(parse_json_attributes=True)) == 2


def test_tracer_provider_override() -> None:
    tracer_provider = TracerProvider()
    with mock.patch.object(PyMSSQLInstrumentor, 'instrument') as instrument:
        logfire.instrument_pymssql(tracer_provider=tracer_provider)
    instrument.assert_called_once_with(tracer_provider=tracer_provider)


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.pymssql': None}):
        with pytest.raises(RuntimeError) as exc_info:
            importlib.reload(logfire._internal.integrations.pymssql)
        assert str(exc_info.value) == snapshot("""\
`logfire.instrument_pymssql()` requires the `opentelemetry-instrumentation-pymssql` package.
You can install this with:
    pip install 'logfire[pymssql]'\
""")
