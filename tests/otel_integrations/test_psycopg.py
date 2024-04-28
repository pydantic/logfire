import psycopg
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
