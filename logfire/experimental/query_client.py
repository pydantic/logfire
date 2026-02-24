from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar, cast

from typing_extensions import Self

from logfire._internal.config import get_base_url_from_token

try:
    from httpx import AsyncClient, Client, Response, Timeout
    from httpx._client import BaseClient
except ImportError as e:  # pragma: no cover
    raise ImportError('httpx is required to use the Logfire query clients') from e

if TYPE_CHECKING:
    from pyarrow import Table  # type: ignore

DEFAULT_TIMEOUT = Timeout(30.0)  # queries might typically be slower than the 5s default from AsyncClient

MAX_QUERY_LIMIT = 10_000


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


class PaginationCursor(TypedDict, total=False):
    """Cursor for pagination through query results.

    For records with use_created_at=False: start_timestamp, trace_id, span_id.
    For records with use_created_at=True: created_at, trace_id, span_id, kind.
    """

    start_timestamp: str
    trace_id: str
    span_id: str
    created_at: str
    kind: str


T = TypeVar('T', bound=BaseClient)


class _BaseLogfireQueryClient(Generic[T]):
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any):
        self.base_url = base_url
        self.read_token = read_token
        self.timeout = timeout
        headers = client_kwargs.pop('headers', {})
        headers['authorization'] = read_token
        self.client: T = client(timeout=timeout, base_url=base_url, headers=headers, **client_kwargs)

    def build_query_params(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        row_oriented: bool = False,
    ) -> dict[str, str]:
        params: dict[str, str] = {'sql': sql}
        if limit is not None:
            params['limit'] = str(limit)
        if row_oriented:
            params['json_rows'] = 'true'
        if min_timestamp:
            params['min_timestamp'] = min_timestamp.isoformat()
        if max_timestamp:
            params['max_timestamp'] = max_timestamp.isoformat()
        return params

    def handle_response_errors(self, response: Response) -> None:
        if response.status_code == 400:  # pragma: no cover
            raise QueryExecutionError(response.json())
        if response.status_code == 422:  # pragma: no cover
            raise QueryRequestError(response.json())
        assert response.status_code == 200, response.content


def _build_paginated_records_sql(
    select: str = '*',
    where: str | None = None,
    page_size: int = MAX_QUERY_LIMIT,
    cursor: PaginationCursor | None = None,
    use_created_at: bool = False,
    table: str = 'records',
) -> str:
    """Build SQL for paginated records query."""
    if use_created_at:
        table = 'records_all'
        order_cols = 'created_at, trace_id, span_id, kind'
        cursor_cols = ['created_at', 'trace_id', 'span_id', 'kind']
        cursor_keys = ['created_at', 'trace_id', 'span_id', 'kind']
    else:
        order_cols = 'start_timestamp, trace_id, span_id'
        cursor_cols = ['start_timestamp', 'trace_id', 'span_id']
        cursor_keys = ['start_timestamp', 'trace_id', 'span_id']

    parts = [f'SELECT {select} FROM {table}']

    if where:
        parts.append(f'WHERE {where}')
        if cursor:
            cursor_vals = [cursor.get(k) for k in cursor_keys]
            if all(v is not None for v in cursor_vals):
                placeholders = ', '.join(f"'{str(v).replace(chr(39), chr(39) + chr(39))}'" for v in cursor_vals)
                parts.append(f'AND ({", ".join(cursor_cols)}) > ({placeholders})')
    elif cursor:
        cursor_vals = [cursor.get(k) for k in cursor_keys]
        if all(v is not None for v in cursor_vals):
            placeholders = ', '.join(f"'{str(v).replace(chr(39), chr(39) + chr(39))}'" for v in cursor_vals)
            parts.append(f'WHERE ({", ".join(cursor_cols)}) > ({placeholders})')

    parts.append(f'ORDER BY {order_cols}')
    parts.append(f'LIMIT {page_size}')
    return ' '.join(parts)


def _extract_cursor_from_row(row: dict[str, Any], use_created_at: bool = False) -> PaginationCursor | None:
    """Extract pagination cursor from the last row."""
    if use_created_at:
        keys = ['created_at', 'trace_id', 'span_id', 'kind']
    else:
        keys = ['start_timestamp', 'trace_id', 'span_id']
    if all(k in row and row[k] is not None for k in keys):
        return cast(PaginationCursor, {k: str(row[k]) for k in keys})
    return None


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
        response = self._query(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            row_oriented=False,
        )
        return response.json()

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
            row_oriented=True,
        )
        return response.json()

    def query_arrow(  # type: ignore
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
        with pyarrow.ipc.open_stream(response.content) as reader:  # type: ignore
            arrow_table: Table = reader.read_all()  # type: ignore
        return arrow_table  # type: ignore

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

    def iter_paginated_records(
        self,
        select: str = '*',
        where: str | None = None,
        page_size: int = MAX_QUERY_LIMIT,
        cursor: PaginationCursor | None = None,
        use_created_at: bool = False,
    ) -> Iterator[tuple[list[dict[str, Any]], PaginationCursor | None]]:
        """Iterate over records in pages, yielding (rows, next_cursor) for each page.

        Uses cursor-based pagination to retrieve more than the 10,000 row API limit.
        The cursor is derived from (start_timestamp, trace_id, span_id) or, when
        use_created_at=True, from (created_at, trace_id, span_id, kind).

        Use use_created_at=True when paginating over recent data where new rows may
        be inserted during pagination. Otherwise use start_timestamp-based pagination.

        Args:
            select: SQL columns to select. Must include cursor columns for pagination
                to continue: start_timestamp, trace_id, span_id (or created_at, kind
                when use_created_at=True). Use '*' to select all.
            where: Optional WHERE clause (without the leading WHERE keyword).
            page_size: Number of rows per page (max 10,000).
            cursor: Cursor from previous page to continue from.
            use_created_at: Use created_at for cursor when new data may be inserted.

        Yields:
            Tuples of (rows, next_cursor). next_cursor is None when no more pages.
        """
        page_size = min(page_size, MAX_QUERY_LIMIT)
        while True:
            sql = _build_paginated_records_sql(
                select=select,
                where=where,
                page_size=page_size,
                cursor=cursor,
                use_created_at=use_created_at,
            )
            result = self.query_json_rows(sql=sql)
            rows = result.get('rows', [])
            if not rows:
                yield rows, None
                return
            next_cursor = _extract_cursor_from_row(rows[-1], use_created_at=use_created_at)
            yield rows, next_cursor
            if next_cursor is None or len(rows) < page_size:
                return
            cursor = next_cursor

    def _query(
        self,
        accept: Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv'],
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        row_oriented: bool = False,
    ) -> Response:
        params = self.build_query_params(sql, min_timestamp, max_timestamp, limit, row_oriented)
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
        response = await self._query(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            row_oriented=False,
        )
        return response.json()

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
            row_oriented=True,
        )
        return response.json()

    async def query_arrow(  # type: ignore
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
        with pyarrow.ipc.open_stream(response.content) as reader:  # type: ignore
            arrow_table: Table = reader.read_all()  # type: ignore
        return arrow_table  # type: ignore

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

    async def iter_paginated_records(
        self,
        select: str = '*',
        where: str | None = None,
        page_size: int = MAX_QUERY_LIMIT,
        cursor: PaginationCursor | None = None,
        use_created_at: bool = False,
    ) -> AsyncIterator[tuple[list[dict[str, Any]], PaginationCursor | None]]:
        """Iterate over records in pages, yielding (rows, next_cursor) for each page.

        Uses cursor-based pagination to retrieve more than the 10,000 row API limit.
        The cursor is derived from (start_timestamp, trace_id, span_id) or, when
        use_created_at=True, from (created_at, trace_id, span_id, kind).

        Use use_created_at=True when paginating over recent data where new rows may
        be inserted during pagination. Otherwise use start_timestamp-based pagination.

        Args:
            select: SQL columns to select. Must include cursor columns for pagination
                to continue: start_timestamp, trace_id, span_id (or created_at, kind
                when use_created_at=True). Use '*' to select all.
            where: Optional WHERE clause (without the leading WHERE keyword).
            page_size: Number of rows per page (max 10,000).
            cursor: Cursor from previous page to continue from.
            use_created_at: Use created_at for cursor when new data may be inserted.

        Yields:
            Tuples of (rows, next_cursor). next_cursor is None when no more pages.
        """
        page_size = min(page_size, MAX_QUERY_LIMIT)
        while True:
            sql = _build_paginated_records_sql(
                select=select,
                where=where,
                page_size=page_size,
                cursor=cursor,
                use_created_at=use_created_at,
            )
            result = await self.query_json_rows(sql=sql)
            rows = result.get('rows', [])
            if not rows:
                yield rows, None
                return
            next_cursor = _extract_cursor_from_row(rows[-1], use_created_at=use_created_at)
            yield rows, next_cursor
            if next_cursor is None or len(rows) < page_size:
                return
            cursor = next_cursor

    async def _query(
        self,
        accept: Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv'],
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        row_oriented: bool = False,
    ) -> Response:
        params = self.build_query_params(sql, min_timestamp, max_timestamp, limit, row_oriented)
        response = await self.client.get('/v1/query', headers={'accept': accept}, params=params)
        self.handle_response_errors(response)
        return response
