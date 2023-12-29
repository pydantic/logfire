"""This module provides functions for interacting with the Logfire "Explore" page.

The public functions in this module can be used both locally and in the Logfire "Explore" page,
and should behave similarly in both. This allows you to develop and test your code locally,
and then use it in the Logfire "Explore" page without changes.
"""
import asyncio
import inspect
import sys
import tempfile
import warnings
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, TypedDict

_in_pyodide = 'pyodide' in sys.modules

try:
    import httpx
except ImportError as e:
    if _in_pyodide:
        # httpx should only be used outside pyodide
        # it cannot be used inside pyodide due to lack of sockets
        # pyodide provides pyodide.http.fetch to work around this
        httpx = None
    else:
        raise ImportError('httpx is a requirement for local development of Logfire snippets') from e

try:
    _in_jupyter = get_ipython().__class__.__name__ == 'ZMQInteractiveShell'  # type: ignore
except NameError:
    _in_jupyter = False

_TOKEN_VAR: ContextVar[str | None] = ContextVar('_TOKEN_VAR', default=None)
_BASE_URL_VAR: ContextVar[str | None] = ContextVar('_BASE_URL_VAR', default=None)


async def query(sql: str) -> list[dict[str, Any]]:
    """Accepts a raw SQL query string, and executes it directly."""
    data = await _raw_query(sql)
    if data['status'] == 'success':
        return data['data']
    else:
        error_details = data['error_details']
        raise ValueError(f'Error running query:\n{error_details}')


def show(item: Any) -> None:
    """Display the provided item in the UI appropriately.

    In a jupyter notebook, this will show the item under the cell as usual, and in the Logfire "Explore" page, this will
    show the item in the "Display" area. When called in a standard python script, this function behaves as `print`.
    """
    if _in_pyodide:
        raise RuntimeError('This function should have been injected into pyodide by the web worker.')
    elif _in_jupyter:
        from IPython.display import display  # type: ignore

        display(item)
    elif hasattr(item, '_repr_mimebundle_'):
        # If included in the output of `_repr_mimebundle_`, save the HTML to a file and open with the browser.
        # Note: in principle, we could probably do the same thing with `_repr_html_`, but this handles altair charts.
        repr_mimebundle = item._repr_mimebundle_()
        html = repr_mimebundle.get('text/html')
        if html is None:
            print(item)
            return

        temp_dir = Path(tempfile.gettempdir()) / 'logfire_dash_show'
        temp_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(
            delete=False, dir=temp_dir, prefix='chart-', suffix='.html', mode='w'
        ) as temp_file:
            temp_file.write(html)
            print(f'{item} saved to temporary file: {temp_file.name}')

            import webbrowser

            webbrowser.open_new_tab(f'file://{temp_file.name}')

    else:
        print(item)


def snippet(
    snippet_func: Callable[[], Awaitable[None] | None],
    token: str | None = None,
    data_dir: Path = Path('.logfire'),
    base_url: str | None = None,
) -> None:
    """This function provides an entrypoint into working locally with a Logfire snippet.

    This function is _only_ intended for use during local development, not in the Logfire UI.

    Today, it is only used to call a function whose contents form the Logfire snippet. In the future we plan
    to add a "mode" argument (or similar) to this function to do things like sync the snippet to Logfire, etc.
    """
    if _in_pyodide:
        # Call the snippet function. We can't use `asyncio.run` in pyodide, but this still results
        # in the snippet function's code being executed, the main difference relative to execution
        # outside pyodide is that it won't block subsequent code from executing until it has finished.
        snippet_func()
        return

    token_token, base_url_token = _configure_dash(token, data_dir, base_url)
    try:
        if inspect.iscoroutinefunction(snippet_func):
            asyncio.run(snippet_func())
        else:
            snippet_func()
    finally:
        _TOKEN_VAR.reset(token_token)
        _BASE_URL_VAR.reset(base_url_token)


def configure_dash(token: str | None = None, data_dir: Path = Path('.logfire'), base_url: str | None = None) -> None:
    """Configures the token and base_url for the `logfire.dash` functions.

    If not provided, the token is obtained using the same logic as `logfire.configure`.

    We provide this standalone function for configuring the dash functions to make it easier to develop charts
    iteratively, e.g. in a Jupyter notebook, so you don't have to run a single function top-to-bottom, as would
    be necessary with `logfire.snippet`.

    This function is _only_ intended for use during local development, not in the Logfire UI.
    """
    if _in_pyodide:
        # Do nothing inside pyodide, to make it easier to copy/paste code that works outside pyodide.
        # However, still emit a descriptive warning to attempt to eliminate any possible confusion.
        warnings.warn('Calling `logfire.dash.configure_dash` has no effect inside the Logfire UI', UserWarning)
        return

    _configure_dash(token, data_dir, base_url)


def _configure_dash(
    token: str | None = None, data_dir: Path = Path('.logfire'), base_url: str | None = None
) -> tuple[Token[str | None], Token[str | None]]:
    from ._config import LogfireConfig
    from .exceptions import LogfireConfigError

    token, _ = LogfireConfig.load_token(token=token, data_dir=data_dir)
    if token is None:
        raise LogfireConfigError(
            'No logfire token provided or found in the default locations.'
            ' You can set the token via the environment variable `LOGFIRE_TOKEN`,'
            ' or through the `token` argument to `logfire.dash.configure_dash` or `logfire.dash.snippet`.'
        )

    token_token = _TOKEN_VAR.set(token)
    base_url_token = _BASE_URL_VAR.set(base_url)
    return token_token, base_url_token


class _Success(TypedDict):
    status: Literal['success']
    data: list[dict[str, Any]]


class _Error(TypedDict):
    status: Literal['error']
    error_details: str


async def _raw_query(q: str) -> _Success | _Error:
    """Accepts a raw query string, and returns the results as a list of dicts mapping column-name to value.

    This can be converted into a pandas `DataFrame` via `pd.DataFrame.from_records(results)`.
    """
    if _in_pyodide:
        raise RuntimeError('This function should have been injected into pyodide by the web worker.')

    assert httpx is not None
    from ._constants import LOGFIRE_BASE_URL

    base_url = _BASE_URL_VAR.get() or LOGFIRE_BASE_URL
    token = _TOKEN_VAR.get()
    if token is None:
        _configure_dash()
        token = _TOKEN_VAR.get()
        assert token is not None, 'An error should have been raised in `_configure_dash` if token is now None'

    client = httpx.AsyncClient(headers={'Authorization': token})
    response = await client.get(f'{base_url}/dash/query', params={'q': q})
    response.raise_for_status()
    return response.json()
