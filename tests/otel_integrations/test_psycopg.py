from unittest import mock

import psycopg
import psycopg.pq
import psycopg2
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

from logfire._internal.integrations.psycopg import check_version, instrument_psycopg


def test_check_version():
    assert check_version('psycopg2', '2.7.3.1', Psycopg2Instrumentor())
    assert not check_version('psycopg2', '2.7.3.0', Psycopg2Instrumentor())
    assert check_version('psycopg', '3.1.0', PsycopgInstrumentor())
    assert not check_version('psycopg', '3.0.1', PsycopgInstrumentor())

    assert check_version(psycopg.__name__, psycopg.__version__, PsycopgInstrumentor())
    assert check_version(psycopg2.__name__, psycopg2.__version__, Psycopg2Instrumentor())


def test_instrument_psycopg():
    original_connect = psycopg.connect

    instrument_psycopg(psycopg)
    assert original_connect is not psycopg.connect
    PsycopgInstrumentor().uninstrument()
    assert original_connect is psycopg.connect

    instrument_psycopg('psycopg')
    assert original_connect is not psycopg.connect
    PsycopgInstrumentor().uninstrument()
    assert original_connect is psycopg.connect


def test_instrument_psycopg2():
    original_connect = psycopg2.connect

    instrument_psycopg(psycopg2)
    assert original_connect is not psycopg2.connect
    Psycopg2Instrumentor().uninstrument()
    assert original_connect is psycopg2.connect

    instrument_psycopg('psycopg2')
    assert original_connect is not psycopg2.connect
    Psycopg2Instrumentor().uninstrument()
    assert original_connect is psycopg2.connect


def test_instrument_both():
    original_connect = psycopg.connect
    original_connect2 = psycopg2.connect

    instrument_psycopg()
    assert original_connect is not psycopg.connect
    assert original_connect2 is not psycopg2.connect
    PsycopgInstrumentor().uninstrument()
    Psycopg2Instrumentor().uninstrument()
    assert original_connect is psycopg.connect
    assert original_connect2 is psycopg2.connect


def test_instrument_psycopg_connection():
    pgconn = mock.Mock()
    conn = psycopg.Connection(pgconn)
    original_cursor_factory = conn.cursor_factory

    instrument_psycopg(conn)
    assert original_cursor_factory is not conn.cursor_factory
    assert conn._is_instrumented_by_opentelemetry
    PsycopgInstrumentor().uninstrument_connection(conn)
    assert original_cursor_factory is conn.cursor_factory

    pgconn.status = psycopg.pq.ConnStatus.BAD
    conn.close()
