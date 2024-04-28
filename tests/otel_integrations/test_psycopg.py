from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

from logfire._internal.integrations.psycopg import check_version


def test_check_version():
    assert check_version('psycopg2', '2.7.3.1', Psycopg2Instrumentor())
    assert not check_version('psycopg2', '2.7.3.0', Psycopg2Instrumentor())
    assert check_version('psycopg', '3.1.0', PsycopgInstrumentor())
    assert not check_version('psycopg', '3.0.1', PsycopgInstrumentor())
