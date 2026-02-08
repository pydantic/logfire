from datetime import datetime
from logfire.experimental.query_client import LogfireQueryClient
from typing import Any, Sequence

apilevel: str
threadsafety: int
paramstyle: str
DEFAULT_LIMIT: int

class Warning(Exception):
    """Exception raised for important warnings, e.g. data truncation."""

class Error(Exception):
    """Base class for all DB API errors."""

class InterfaceError(Error):
    """Exception raised for errors related to the database interface."""

class DatabaseError(Error):
    """Exception raised for errors related to the database."""

class OperationalError(DatabaseError):
    """Exception raised for errors related to the database's operation."""

class ProgrammingError(DatabaseError):
    """Exception raised for programming errors, e.g. bad SQL or using a closed cursor."""

class NotSupportedError(DatabaseError):
    """Exception raised when an unsupported operation is attempted."""

class Connection:
    """PEP 249 Connection wrapping a `LogfireQueryClient`."""

    client: LogfireQueryClient
    closed: bool
    min_timestamp: datetime | None
    max_timestamp: datetime | None
    limit: int
    def __init__(
        self,
        client: LogfireQueryClient,
        *,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int = ...,
    ) -> None: ...
    def close(self) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def cursor(self) -> Cursor: ...
    def __enter__(self) -> Connection: ...
    def __exit__(self, *args: Any) -> None: ...

class Cursor:
    """PEP 249 Cursor that executes queries via `LogfireQueryClient.query_json_rows()`."""

    rowcount: int
    arraysize: int
    min_timestamp: datetime | None
    max_timestamp: datetime | None
    limit: int | None
    def __init__(self, connection: Connection) -> None: ...
    @property
    def description(self) -> list[tuple[Any, ...]] | None: ...
    def execute(self, operation: str, parameters: dict[str, Any] | Sequence[Any] | None = None) -> None: ...
    def executemany(self, operation: str, seq_of_parameters: Sequence[dict[str, Any] | Sequence[Any]]) -> None: ...
    def fetchone(self) -> tuple[Any, ...] | None: ...
    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]: ...
    def fetchall(self) -> list[tuple[Any, ...]]: ...
    def close(self) -> None: ...
    def setinputsizes(self, _sizes: Any) -> None: ...
    def setoutputsize(self, _size: Any, _column: Any = None) -> None: ...
    def __enter__(self) -> Cursor: ...
    def __exit__(self, *args: Any) -> None: ...

def connect(
    read_token: str,
    base_url: str | None = None,
    timeout: float = 30.0,
    *,
    min_timestamp: datetime | None = None,
    max_timestamp: datetime | None = None,
    limit: int = ...,
    **kwargs: Any,
) -> Connection:
    """Create a PEP 249 connection to the Logfire query API."""
