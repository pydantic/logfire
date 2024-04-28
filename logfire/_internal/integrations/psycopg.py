from __future__ import annotations

import importlib
from importlib.util import find_spec
from types import ModuleType
from typing import TYPE_CHECKING, Any

from packaging.requirements import Requirement

PACKAGE_NAMES = ('psycopg', 'psycopg2')

if TYPE_CHECKING:
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Instrumentor = PsycopgInstrumentor | Psycopg2Instrumentor


def instrument_psycopg(conn_or_module: Any = None, **kwargs: Any):
    if conn_or_module is None:
        for package in PACKAGE_NAMES:
            if find_spec(package):
                instrument_psycopg(package, **kwargs)
    elif conn_or_module in PACKAGE_NAMES:
        _instrument_psycopg(conn_or_module, **kwargs)
    elif isinstance(conn_or_module, ModuleType):
        instrument_psycopg(conn_or_module.__name__)
    else:
        for cls in conn_or_module.__mro__:
            package = cls.__module__.split('.')[0]
            if package in PACKAGE_NAMES:
                instrument_psycopg(package)
                break

    raise ValueError(f"Don't know how to instrument {conn_or_module!r}")


def _instrument_psycopg(name: str, conn: Any = None, **kwargs: Any):
    try:
        instrumentor_module = importlib.import_module(f'opentelemetry.instrumentation.{name}')
    except ImportError:
        raise ImportError("Run `pip install 'logfire[psycopg2]'` to install psycopg2 instrumentation.")

    instrumentor = getattr(instrumentor_module, f'{name.capitalize()}Instrumentor')()
    if conn is None:
        mod = importlib.import_module(name)
        skip_dep_check = check_version(name, mod.__version__, instrumentor)
        instrumentor.instrument(skip_dep_check=skip_dep_check, **kwargs)
    else:
        instrumentor.instrument_connection(conn)


def check_version(name: str, version: str, instrumentor: Instrumentor):
    for dep in instrumentor.instrumentation_dependencies():
        req = Requirement(dep)
        if req.name == name and req.specifier.contains(version):
            return True
    return False
