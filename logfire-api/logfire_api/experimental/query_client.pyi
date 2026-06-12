from _typeshed import Incomplete
from datetime import datetime
from httpx import AsyncClient, Client, Response, Timeout
from httpx._client import BaseClient
from logfire import VERSION as VERSION
from logfire._internal.config import get_base_url_from_token as get_base_url_from_token
from logfire._internal.stack_info import warn_at_user_stacklevel as warn_at_user_stacklevel
from pyarrow import Table
from types import TracebackType
from typing import Any, Generic, TypeVar, TypedDict, overload
from typing_extensions import Self

DEFAULT_TIMEOUT: Incomplete

class QueryExecutionError(RuntimeError):
    """Raised when the query execution fails on the server."""
class QueryRequestError(RuntimeError):
    """Raised when the query request is invalid."""
class InfoRequestError(RuntimeError):
    """Raised when the request for read token info fails because of unavailable information."""

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
T = TypeVar('T', bound=BaseClient)

class _BaseLogfireQueryClient(Generic[T]):
    base_url: Incomplete
    read_token: Incomplete
    timeout: Incomplete
    client: T
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any) -> None: ...
    def handle_response_errors(self, response: Response) -> None: ...

class LogfireQueryClient(_BaseLogfireQueryClient[Client]):
    """A synchronous client for querying Logfire data."""
    def __init__(self, read_token: str, base_url: str | None = None, timeout: Timeout = ..., **client_kwargs: Any) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: type[BaseException] | None = None, exc_value: BaseException | None = None, traceback: TracebackType | None = None) -> None: ...
    def info(self) -> ReadTokenInfo:
        """Get information about the read token."""
    def query_json(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
    @overload
    def query_json_rows(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> RowQueryResults: ...
    @overload
    def query_json_rows(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> RowQueryResults: ...
    @overload
    def query_arrow(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> Table: ...
    @overload
    def query_arrow(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> Table: ...
    @overload
    def query_csv(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> str: ...
    @overload
    def query_csv(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> str: ...

class AsyncLogfireQueryClient(_BaseLogfireQueryClient[AsyncClient]):
    """An asynchronous client for querying Logfire data."""
    def __init__(self, read_token: str, base_url: str | None = None, timeout: Timeout = ..., **async_client_kwargs: Any) -> None: ...
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: type[BaseException] | None = None, exc_value: BaseException | None = None, traceback: TracebackType | None = None) -> None: ...
    async def info(self) -> ReadTokenInfo:
        """Get information about the read token."""
    @overload
    async def query_json_rows(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> RowQueryResults: ...
    @overload
    async def query_json_rows(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> RowQueryResults: ...
    async def query_json(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
    async def query_json_rows(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> RowQueryResults:
        """Query Logfire data and return the results as a row-oriented dictionary.

        Args:
            sql: The SQL `SELECT` query to execute.
            min_timestamp: The minimum timestamp to use when querying data. If the provided
                [`datetime`][datetime.datetime] doesn't have a timezone set, it is assumed to
                be UTC.

                /// version-deprecated | v4.35.0
                Not providing a `min_timestamp` is deprecated.
                ///
            max_timestamp: The maximum timestamp to use when querying data. If the provided
                [`datetime`][datetime.datetime] doesn't have a timezone set, it is assumed to
                be UTC.
            limit: The maximum number of rows to query. This value takes priority over the
                `LIMIT` clause in the `sql` query.
            timezone: The timezone to use for the query execution context.
            environment: Restrict rows to the provided environment(s). To only query rows where no environment is set,
                use the empty string (`''`).

        Returns:
            A dictionary with two entries:
              * `columns`: A list of column details including the name, datatype and whether the column is nullable.
              * `rows`: The list of rows matching the query.
        """
    @overload
    async def query_arrow(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> Table: ...
    @overload
    async def query_arrow(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> Table: ...
    @overload
    async def query_csv(self, sql: str, min_timestamp: None = None, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> str: ...
    @overload
    async def query_csv(self, sql: str, min_timestamp: datetime, max_timestamp: datetime | None = None, limit: int | None = None, *, timezone: str | None = None, environment: str | list[str] | None = None) -> str: ...
