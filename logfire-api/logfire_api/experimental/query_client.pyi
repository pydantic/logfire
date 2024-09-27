from _typeshed import Incomplete
from datetime import datetime
from httpx import AsyncClient, Client, Response, Timeout
from httpx._client import BaseClient
from pyarrow import Table
from types import TracebackType
from typing import Any, Generic, TypeVar, TypedDict

DEFAULT_TIMEOUT: Incomplete

class QueryExecutionError(RuntimeError):
    """Raised when the query execution fails on the server."""
class QueryRequestError(RuntimeError):
    """Raised when the query request is invalid."""

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
S = TypeVar('S', bound='LogfireQueryClient')
R = TypeVar('R', bound='AsyncLogfireQueryClient')

class _BaseLogfireQueryClient(Generic[T]):
    base_url: Incomplete
    read_token: Incomplete
    timeout: Incomplete
    client: Incomplete
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any) -> None: ...
    def build_query_params(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None, row_oriented: bool = False) -> dict[str, str]: ...
    def handle_response_errors(self, response: Response) -> None: ...

class LogfireQueryClient(_BaseLogfireQueryClient[Client]):
    """A synchronous client for querying Logfire data."""
    def __init__(self, read_token: str, base_url: str = 'https://logfire-api.pydantic.dev/', timeout: Timeout = ..., **client_kwargs: Any) -> None: ...
    def __enter__(self) -> S: ...
    def __exit__(self, exc_type: type[BaseException] | None = None, exc_value: BaseException | None = None, traceback: TracebackType | None = None) -> None: ...
    def query_json(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
    def query_json_rows(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> RowQueryResults:
        """Query Logfire data and return the results as a row-oriented dictionary."""
    def query_arrow(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.
        """
    def query_csv(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.
        """

class AsyncLogfireQueryClient(_BaseLogfireQueryClient[AsyncClient]):
    """An asynchronous client for querying Logfire data."""
    def __init__(self, read_token: str, base_url: str = 'https://logfire-api.pydantic.dev/', timeout: Timeout = ..., **async_client_kwargs: Any) -> None: ...
    async def __aenter__(self) -> R: ...
    async def __aexit__(self, exc_type: type[BaseException] | None = None, exc_value: BaseException | None = None, traceback: TracebackType | None = None) -> None: ...
    async def query_json(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
    async def query_json_rows(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> RowQueryResults:
        """Query Logfire data and return the results as a row-oriented dictionary."""
    async def query_arrow(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.
        """
    async def query_csv(self, sql: str, min_timestamp: datetime | None = None, max_timestamp: datetime | None = None, limit: int | None = None) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.
        """
