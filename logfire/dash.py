import re
import sys
from functools import cache
from pathlib import Path
from typing import Any

_in_pyodide = 'pyodide' in sys.modules

try:
    import httpx
except ImportError:
    if _in_pyodide:
        # httpx should only be used outside pyodide
        # it cannot be used inside pyodide due to lack of sockets
        # pyodide provides pyodide.http.fetch to work around this
        httpx = None
    else:
        raise

try:
    _in_jupyter = get_ipython().__class__.__name__ == 'ZMQInteractiveShell'  # type: ignore
except NameError:
    _in_jupyter = False

_PYODIDE_NOT_ALLOWED_MESSAGE = 'This function should not be called in the logfire frontend.'
_PYODIDE_MUST_INJECT_MESSAGE = 'This function should be injected into pyodide by the web worker.'


def configure(
    logfire_token: str | None = None,
    logfire_dir: Path = Path('.logfire'),
    logfire_api_root: str | None = None,
    named_queries_path: Path = Path('logfire_queries.sql'),
) -> None:
    """
    This function sets the arguments used to obtain the logfire token used in the `logfire.dash` module.
    """
    if _in_pyodide:
        # Ignore this call in pyodide, to make it easier to copy/paste code that works outside pyodide.
        return
        # Alternatively, we could raise an error:
        # raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    global _configured, _logfire_token, _logfire_dir, _logfire_api_root, _named_queries_path
    _logfire_token = logfire_token
    _logfire_dir = logfire_dir
    _logfire_api_root = logfire_api_root
    _named_queries_path = named_queries_path

    _get_token.cache_clear()

    _configured = True


async def named_query(name: str) -> list[dict[str, Any]]:
    """
    Accepts a query name, and attempts to obtain it from the named queries SQL file.
    If successful, uses the `query` function to execute the query and return the results.
    """
    named_queries_sql = _get_named_queries_sql()
    named_queries = _get_named_queries(named_queries_sql)

    q = named_queries.get(name)
    if q is None:
        names = list(named_queries.keys())
        raise ValueError(f'No such named query: {name!r}. Allowed values: {names}.')

    return await query(q)


async def query(q: str) -> list[dict[str, Any]]:
    """
    Accepts a raw query string, and returns the results as a list of dicts mapping column-name to value.

    This can be converted into a pandas dataframe via `pd.DataFrame.from_records(results)`.
    """
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)

    assert httpx is not None
    from logfire.config import LOGFIRE_API_ROOT

    # Need to use a logfire configuration
    # Should we expose the token as part of the configuration
    token = _get_token()
    client = httpx.AsyncClient(headers={'Authorization': token})
    route = (_logfire_api_root or LOGFIRE_API_ROOT) + '/dash/query'
    response = await client.get(route, params={'q': q})
    response.raise_for_status()
    return response.json()


def show(item: Any) -> None:
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)
    elif _in_jupyter:
        from IPython.display import display  # type: ignore

        display(item)
    else:
        print(item)


_configured: bool = False
_logfire_token: str | None = None
_logfire_dir: Path = Path('.logfire')
_logfire_api_root: str | None = None
_named_queries_path: Path = Path('logfire_queries.sql')


def _get_named_queries(raw_sql: str) -> dict[str, str]:
    split_items = re.split(r'^--\s*(logfire-query:)\s*([a-zA-Z-_]+)$', raw_sql, flags=re.MULTILINE)
    named_queries: dict[str, str] = {}
    for i, item in enumerate(split_items):
        if item == 'logfire-query:' and i < len(split_items) - 2:
            named_queries[split_items[i + 1]] = split_items[i + 2].strip('\n')
    return named_queries


@cache
def _get_token() -> str:
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    if not _configured:
        configure()

    from logfire.config import LogfireConfig, LogfireConfigError

    token, _ = LogfireConfig.load_token(logfire_token=_logfire_token, logfire_dir=_logfire_dir)
    if token is None:
        raise LogfireConfigError(
            'No logfire token provided or found in the default locations.'
            ' You can set the token via the environment variable `LOGFIRE_TOKEN`,'
            ' or with a call to `logfire.dash.configure`.'
        )
    return token


def _get_named_queries_sql() -> str:
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)

    if not _named_queries_path.exists():
        return ''

    return _named_queries_path.read_text()
