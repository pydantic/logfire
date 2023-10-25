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
) -> None:
    """
    This function sets the arguments used to obtain the logfire token used in the `logfire.dash` module.
    """
    if _in_pyodide:
        # Ignore this call in pyodide, to make it easier to copy/paste code that works outside pyodide.
        return
        # Alternatively, we could raise an error:
        # raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    global _configured, _logfire_token, _logfire_dir, _logfire_api_root
    _logfire_token = logfire_token
    _logfire_dir = logfire_dir
    _logfire_api_root = logfire_api_root

    _get_token.cache_clear()

    _configured = True


async def query(q: str) -> list[dict[str, Any]]:
    """
    Accepts a raw query string, and returns the results as a list of dicts mapping column-name to value.

    This can be converted into a pandas dataframe via `pd.DataFrame.from_records(results)`.
    """
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)

    assert httpx is not None
    from ._constants import LOGFIRE_API_ROOT

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


@cache
def _get_token() -> str:
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    if not _configured:
        configure()

    from logfire._config import LogfireConfig, LogfireConfigError

    token, _ = LogfireConfig.load_token(logfire_token=_logfire_token, logfire_dir=_logfire_dir)
    if token is None:
        raise LogfireConfigError(
            'No logfire token provided or found in the default locations.'
            ' You can set the token via the environment variable `LOGFIRE_TOKEN`,'
            ' or with a call to `logfire.dash.configure`.'
        )
    return token
