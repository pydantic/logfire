from __future__ import annotations

import contextlib
import importlib
from importlib.util import find_spec
from types import ModuleType
from typing import TYPE_CHECKING, Any

from packaging.requirements import Requirement

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor

    Instrumentor = PsycopgInstrumentor | Psycopg2Instrumentor

PACKAGE_NAMES = ('psycopg', 'psycopg2')


def instrument_psycopg(conn_or_module: Any = None, **kwargs: Any):
    """Instrument a `psycopg` connection or module so that spans are automatically created for each query.

    See the `Logfire.instrument_psycopg` method for details.
    """
    if conn_or_module is None:
        # By default, instrument whichever libraries are installed.
        for package in PACKAGE_NAMES:
            if find_spec(package):  # pragma: no branch
                instrument_psycopg(package, **kwargs)
        return
    elif conn_or_module in PACKAGE_NAMES:
        _instrument_psycopg(conn_or_module, **kwargs)
        return
    elif isinstance(conn_or_module, ModuleType):
        instrument_psycopg(conn_or_module.__name__, **kwargs)
        return
    else:
        # Given an object that's not a module or string,
        # and whose class (or an ancestor) is defined in one of the packages, assume it's a connection object.
        for cls in conn_or_module.__class__.__mro__:
            package = cls.__module__.split('.')[0]
            if package in PACKAGE_NAMES:
                if kwargs:
                    raise TypeError(
                        f'Extra keyword arguments are only supported when instrumenting the {package} module, not a connection.'
                    )
                _instrument_psycopg(package, conn_or_module, **kwargs)
                return

    raise ValueError(f"Don't know how to instrument {conn_or_module!r}")


def _instrument_psycopg(name: str, conn: Any = None, **kwargs: Any):
    try:
        instrumentor_module = importlib.import_module(f'opentelemetry.instrumentation.{name}')
    except ImportError:
        raise ImportError(f"Run `pip install 'logfire[{name}]'` to install {name} instrumentation.")

    instrumentor = getattr(instrumentor_module, f'{name.capitalize()}Instrumentor')()
    if conn is None:
        # OTEL looks at the installed packages to determine if the correct dependencies are installed.
        # This means that if a user installs `psycopg-binary` (which is commonly recommended)
        # then they can `import psycopg` but OTEL doesn't recognise this correctly.
        # So we implement an alternative strategy, which is to import `psycopg(2)` and check `__version__`.
        # If it matches, we can tell OTEL to skip the check so that it still works and doesn't log a warning.
        mod = importlib.import_module(name)
        skip_dep_check = check_version(name, mod.__version__, instrumentor)

        if kwargs.get('enable_commenter') and name == 'psycopg':
            import psycopg.pq

            # OTEL looks for __libpq_version__ which only exists in psycopg2.
            mod.__libpq_version__ = psycopg.pq.version()  # type: ignore

        instrumentor.instrument(skip_dep_check=skip_dep_check, **kwargs)
    else:
        # instrument_connection doesn't have a skip_dep_check argument.
        instrumentor.instrument_connection(conn)


def check_version(name: str, version: str, instrumentor: Instrumentor):
    with contextlib.suppress(Exception):  # it's not worth raising an exception if this fails somehow.
        for dep in instrumentor.instrumentation_dependencies():
            req = Requirement(dep)  # dep is a string like 'psycopg >= 3.1.0'
            # The module __version__ can be something like '2.9.9 (dt dec pq3 ext lo64)', hence the split.
            if req.name == name and req.specifier.contains(version.split()[0]):
                return True
    return False
