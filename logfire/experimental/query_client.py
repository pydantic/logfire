from __future__ import annotations

from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar

from typing_extensions import Self

from logfire._internal.config import get_base_url_from_token

try:
    from httpx import AsyncClient, Client, Response, Timeout
    from httpx._client import BaseClient
except ImportError as e:  # pragma: no cover
    raise ImportError('httpx is required to use the Logfire query clients') from e

if TYPE_CHECKING:
    from pyarrow import Table  # pyright: ignore[reportUnknownVariableType]

DEFAULT_TIMEOUT = Timeout(30.0)  # queries might typically be slower than the 5s default from AsyncClient


class QueryExecutionError(RuntimeError):
    """Raised when the query execution fails on the server."""

    pass


class QueryRequestError(RuntimeError):
    """Raised when the query request is invalid."""

    pass


class InfoRequestError(RuntimeError):
    """Raised when the request for read token info fails because of unavailable information."""

    pass


class ReadTokenInfo(TypedDict, total=False):
    """Information about the read token."""

    organization_name: str
    project_name: str


class ColumnDetails(TypedDict):
    """The details of a column in the row-oriented JSON-format query results."""

    name: str
    datatype: Any
    nullable: bool


class ColumnData(ColumnDetails):
    """The data of a column in the column-oriented JSON-format query results."""

    values: list[Any]


class QueryResults(TypedDict):
    """The (column-oriented) results of a JSON-format query."""

    columns: list[ColumnData]


class RowQueryResults(TypedDict):
    """The row-oriented results of a JSON-format query."""

    columns: list[ColumnDetails]
    rows: list[dict[str, Any]]


def _rows_to_columns(result: RowQueryResults) -> QueryResults:
    """Convert a row-oriented JSON query result to a column-oriented one."""
    columns_by_name: dict[str, ColumnData] = {col['name']: {**col, 'values': []} for col in result['columns']}
    for row in result['rows']:
        for col_name, col_data in columns_by_name.items():
            col_data['values'].append(row.get(col_name))
    return {'columns': list(columns_by_name.values())}


T = TypeVar('T', bound=BaseClient)


_ACCEPT = Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv']


class _BaseLogfireQueryClient(Generic[T]):
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any):
        self.base_url = base_url
        self.read_token = read_token
        self.timeout = timeout
        headers = client_kwargs.pop('headers', {})
        headers['authorization'] = read_token
        self.client: T = client(timeout=timeout, base_url=base_url, headers=headers, **client_kwargs)

    def _build_query_params(
        self,
        sql: str,
        min_timestamp: datetime | None,
        max_timestamp: datetime | None,
        limit: int | None,
        accept: _ACCEPT,
    ) -> dict[str, str]:
        params: dict[str, str] = {'sql': sql}
        if accept == 'application/json':
            params['json_rows'] = 'true'
        if limit is not None:
            params['limit'] = str(limit)
        if min_timestamp is not None:
            params['min_timestamp'] = min_timestamp.isoformat()
        if max_timestamp is not None:
            params['max_timestamp'] = max_timestamp.isoformat()
        return params

    def handle_response_errors(self, response: Response) -> None:
        if response.status_code == 400:  # pragma: no cover
            raise QueryExecutionError(response.json())
        if response.status_code == 422:  # pragma: no cover
            raise QueryRequestError(response.json())
        assert response.status_code == 200, response.content


class LogfireQueryClient(_BaseLogfireQueryClient[Client]):
    """A synchronous client for querying Logfire data."""

    def __init__(
        self,
        read_token: str,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **client_kwargs: Any,
    ):
        base_url = base_url or get_base_url_from_token(read_token)
        super().__init__(base_url, read_token, timeout, Client, **client_kwargs)

    def __enter__(self) -> Self:
        self.client.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        self.client.__exit__(exc_type, exc_value, traceback)

    def info(self) -> ReadTokenInfo:
        """Get information about the read token."""
        response = self.client.get('/v1/read-token-info')
        self.handle_response_errors(response)
        token_info = response.json()
        try:
            # Keep keys defined in ReadTokenInfo
            return {
                'organization_name': token_info['organization_name'],
                'project_name': token_info['project_name'],
            }
        except KeyError:
            raise InfoRequestError(
                'The read token info response is missing required fields: organization_name or project_name'
            )

    def query_json(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
        row_results = self.query_json_rows(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return _rows_to_columns(row_results)

    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> RowQueryResults:
        """Query Logfire data and return the results as a row-oriented dictionary."""
        response = self._query(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return response.json()

    def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.
        """
        try:
            import pyarrow
        except ImportError as e:  # pragma: no cover
            raise ImportError('pyarrow is required to use the query_arrow method') from e

        response = self._query(
            accept='application/vnd.apache.arrow.stream',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        with pyarrow.ipc.open_stream(response.content) as reader:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            arrow_table: Table = reader.read_all()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return arrow_table  # pyright: ignore[reportUnknownVariableType]

    def query_csv(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.
        """
        response = self._query(
            accept='text/csv',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return response.text

    def _query(
        self,
        accept: _ACCEPT,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> Response:
        params = self._build_query_params(
            sql=sql, accept=accept, min_timestamp=min_timestamp, max_timestamp=max_timestamp, limit=limit
        )
        response = self.client.get('/v1/query', headers={'accept': accept}, params=params)
        self.handle_response_errors(response)
        return response


class AsyncLogfireQueryClient(_BaseLogfireQueryClient[AsyncClient]):
    """An asynchronous client for querying Logfire data."""

    def __init__(
        self,
        read_token: str,
        base_url: str | None = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        **async_client_kwargs: Any,
    ):
        base_url = base_url or get_base_url_from_token(read_token)
        super().__init__(base_url, read_token, timeout, AsyncClient, **async_client_kwargs)

    async def __aenter__(self) -> Self:
        await self.client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.client.__aexit__(exc_type, exc_value, traceback)

    async def info(self) -> ReadTokenInfo:
        """Get information about the read token."""
        response = await self.client.get('/v1/read-token-info')
        self.handle_response_errors(response)
        token_info = response.json()
        # Keep keys defined in ReadTokenInfo
        try:
            return {
                'organization_name': token_info['organization_name'],
                'project_name': token_info['project_name'],
            }
        except KeyError:
            raise InfoRequestError(
                'The read token info response is missing required fields: organization_name or project_name'
            )

    async def query_json(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
        row_results = await self.query_json_rows(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return _rows_to_columns(row_results)

    async def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> RowQueryResults:
        """Query Logfire data and return the results as a row-oriented dictionary."""
        response = await self._query(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return response.json()

    async def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.
        """
        try:
            import pyarrow
        except ImportError as e:  # pragma: no cover
            raise ImportError('pyarrow is required to use the query_arrow method') from e

        response = await self._query(
            accept='application/vnd.apache.arrow.stream',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        with pyarrow.ipc.open_stream(response.content) as reader:  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
            arrow_table: Table = reader.read_all()  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        return arrow_table  # pyright: ignore[reportUnknownVariableType]

    async def query_csv(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.
        """
        response = await self._query(
            accept='text/csv',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return response.text

    async def _query(
        self,
        accept: Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv'],
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> Response:
        params = self._build_query_params(
            sql=sql, accept=accept, min_timestamp=min_timestamp, max_timestamp=max_timestamp, limit=limit
        )
        response = await self.client.get('/v1/query', headers={'accept': accept}, params=params)
        self.handle_response_errors(response)
        return response
