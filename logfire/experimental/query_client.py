from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar, overload

from typing_extensions import Self, deprecated

from logfire import VERSION
from logfire._internal.config import get_base_url_from_token
from logfire._internal.stack_info import warn_at_user_stacklevel

if sys.version_info >= (3, 11):
    from datetime import UTC
else:
    UTC = timezone.utc

try:
    from httpx import AsyncClient, Client, Response, Timeout
    from httpx._client import BaseClient
except ImportError as e:  # pragma: no cover
    raise ImportError('httpx is required to use the Logfire query clients') from e

if TYPE_CHECKING:
    from pyarrow import Table

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
    """The name of the column."""

    datatype: Any
    """The datatype of the column."""

    nullable: bool
    """Whether the column is nullable or not."""


class ColumnData(ColumnDetails):
    """The data of a column in the column-oriented JSON-format query results."""

    values: list[Any]


class QueryResults(TypedDict):
    """The (column-oriented) results of a JSON-format query."""

    columns: list[ColumnData]


class RowQueryResults(TypedDict):
    """The row-oriented results of a JSON-format query."""

    columns: list[ColumnDetails]
    """The list of column details (e.g. `[{"name": "service_name", "datatype": "Utf8", "nullable": false}]`)."""

    rows: list[dict[str, Any]]
    """The list of rows matching the query (e.g. `[{"service_name": "backend"}]`)."""


def _rows_to_columns(result: RowQueryResults) -> QueryResults:
    """Convert a row-oriented JSON query result to a column-oriented one."""
    columns_by_name: dict[str, ColumnData] = {col['name']: {**col, 'values': []} for col in result['columns']}
    for row in result['rows']:
        for col_name, col_data in columns_by_name.items():
            col_data['values'].append(row.get(col_name))
    return {'columns': list(columns_by_name.values())}


_FF_DATA_TYPE_KEYS_TO_REMOVE = {'dict_id', 'dict_is_ordered', 'metadata'}


def _transform_fields_for_backwards_compatibility(obj: Any) -> Any:
    """Recursively removes all occurrences of _FF_DATA_TYPE_KEYS_TO_REMOVE as keys from arbitrary nesting within `obj`."""
    if isinstance(obj, dict):
        new_obj: dict[str, Any] = {}
        for k, v in obj.items():  # type: ignore
            if k in _FF_DATA_TYPE_KEYS_TO_REMOVE:
                continue
            if k == 'data_type':
                k = 'datatype'
            new_obj[k] = _transform_fields_for_backwards_compatibility(v)
        return new_obj

    elif isinstance(obj, list):
        return [_transform_fields_for_backwards_compatibility(item) for item in obj]  # type: ignore

    else:
        return obj


def _map_v2_result(obj: dict[str, Any]) -> RowQueryResults:
    mapped: RowQueryResults = {
        'columns': _transform_fields_for_backwards_compatibility(obj['schema']['fields']),
        'rows': obj['data'],
    }
    if 'logical_plan' in obj:  # pragma: no cover (plan option not provided for now)
        # TODO when exposing the plan option, add these fields to the RowQueryResults type:
        # All the plan keys are guaranteed to be present:
        for k in ['logical_plan', 'physical_plan', 'physical_plan_with_metrics']:
            mapped[k] = obj[k]

    return mapped


T = TypeVar('T', bound=BaseClient)


_ACCEPT = Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv']
_USER_AGENT = f'logfire-sdk-python/{VERSION} (Python {platform.python_version()}, os {platform.platform()}, arch {platform.machine()})'
_MIN_DATETIME = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()


class _BaseLogfireQueryClient(Generic[T]):
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any):
        self.base_url = base_url
        self.read_token = read_token
        self.timeout = timeout
        headers = client_kwargs.pop('headers', {})
        headers['authorization'] = read_token
        headers.setdefault('user-agent', _USER_AGENT)
        self.client: T = client(timeout=timeout, base_url=base_url, headers=headers, **client_kwargs)

    def _build_v2_body(
        self,
        sql: str,
        min_timestamp: datetime | None,
        max_timestamp: datetime | None,
        limit: int | None,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
        explain: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {'sql': sql, 'explain': explain, 'include_schema': True}

        if limit is not None:
            body['limit'] = limit

        # /v2/query requires aware datetimes, assume UTC:
        if min_timestamp is not None:
            if min_timestamp.tzinfo is None:
                min_timestamp = min_timestamp.replace(tzinfo=UTC)
            body['min_timestamp'] = min_timestamp.isoformat()
        else:
            # For when `min_timestamp` is not provided (deprecated):
            warn_at_user_stacklevel('Querying without a min_timestamp is deprecated', DeprecationWarning)
            body['min_timestamp'] = _MIN_DATETIME
        if max_timestamp is not None:
            if max_timestamp.tzinfo is None:
                max_timestamp = max_timestamp.replace(tzinfo=UTC)
            body['max_timestamp'] = max_timestamp.isoformat()

        if timezone is not None:
            body['timezone'] = timezone
        if isinstance(environment, str):
            environment = [environment]
        if environment is not None:
            body['deployment_environment'] = environment
        return body

    def handle_response_errors(self, response: Response) -> None:
        # Note: the MDN spec does not specify any default for content types,
        # although it is common to assume `application/octet-stream`.
        # In our case, our API isn't supposed to return binary data, so
        # we assume text/plain if not set.
        content_type = response.headers.get('content-type', 'text/plain')
        media_type = content_type.split(';', 1)[0].strip().lower()
        if response.status_code == 400:  # pragma: no cover
            data = response.json() if media_type == 'application/json' else response.text
            raise QueryExecutionError(data)
        if response.status_code == 422:  # pragma: no cover
            data = response.json() if media_type == 'application/json' else response.text
            raise QueryRequestError(data)
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
        except KeyError:  # pragma: no cover
            raise InfoRequestError(
                'The read token info response is missing required fields: organization_name or project_name'
            )

    @deprecated('query_json() is deprecated, use query_json_rows() instead', stacklevel=2)
    def query_json(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
        row_results = self.query_json_rows(  # type: ignore[reportDeprecated]
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
        )
        return _rows_to_columns(row_results)

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_json_rows() without a min_timestamp is deprecated')
    def query_json_rows(
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults: ...

    @overload
    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults: ...

    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults:
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
        response = self._query_v2(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        return _map_v2_result(response.json())

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_arrow() without a min_timestamp is deprecated')
    def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table: ...

    @overload
    def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table: ...

    def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.

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
        """
        try:
            import pyarrow
        except ImportError as e:  # pragma: no cover
            raise ImportError('pyarrow is required to use the query_arrow method') from e

        response = self._query_v2(
            accept='application/vnd.apache.arrow.stream',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        with pyarrow.ipc.open_stream(response.content) as reader:
            arrow_table: Table = reader.read_all()
        return arrow_table  # pyright: ignore[reportUnknownVariableType]

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_csv() without a min_timestamp is deprecated')
    def query_csv(
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str: ...

    @overload
    def query_csv(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str: ...

    def query_csv(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.

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
        """
        response = self._query_v2(
            accept='text/csv',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        return response.text

    def _query_v2(
        self,
        *,
        accept: _ACCEPT,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
        explain: bool = False,
    ) -> Response:

        body = self._build_v2_body(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=explain,
        )
        response = self.client.post('/v2/query', headers={'accept': accept}, json=body)
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
        except KeyError:  # pragma: no cover
            raise InfoRequestError(
                'The read token info response is missing required fields: organization_name or project_name'
            )

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_json_rows() without a min_timestamp is deprecated')
    async def query_json_rows(
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults: ...

    @overload
    async def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults: ...

    @deprecated('query_json() is deprecated, use query_json_rows() instead', stacklevel=2)
    async def query_json(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
    ) -> QueryResults:
        """Query Logfire data and return the results as a column-oriented dictionary."""
        row_results = await self.query_json_rows(  # type: ignore[reportDeprecated]
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
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> RowQueryResults:
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
        response = await self._query_v2(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        return _map_v2_result(response.json())

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_arrow() without a min_timestamp is deprecated')
    async def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table: ...

    @overload
    async def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table: ...

    async def query_arrow(  # pyright: ignore[reportUnknownParameterType]
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> Table:
        """Query Logfire data and return the results as a pyarrow Table.

        Note that pyarrow must be installed for this method to succeed.

        You can use `polars.from_arrow(result)` to convert the returned table to a polars DataFrame.

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
        """
        try:
            import pyarrow
        except ImportError as e:  # pragma: no cover
            raise ImportError('pyarrow is required to use the query_arrow method') from e

        response = await self._query_v2(
            accept='application/vnd.apache.arrow.stream',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        with pyarrow.ipc.open_stream(response.content) as reader:
            arrow_table: Table = reader.read_all()
        return arrow_table  # pyright: ignore[reportUnknownVariableType]

    # Note: on the next major version, move the keyword-only marker after `sql`:
    @overload
    @deprecated('Using query_csv() without a min_timestamp is deprecated')
    async def query_csv(
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str: ...

    @overload
    async def query_csv(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str: ...

    async def query_csv(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
    ) -> str:
        """Query Logfire data and return the results as a CSV-format string.

        Use `polars.read_csv(StringIO(result))` to convert the returned CSV to a polars DataFrame.

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
        """
        response = await self._query_v2(
            accept='text/csv',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=False,  # Note: we can expose this in the future
        )
        return response.text

    async def _query_v2(
        self,
        *,
        accept: _ACCEPT,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        timezone: str | None = None,
        environment: str | list[str] | None = None,
        explain: bool = False,
    ) -> Response:

        body = self._build_v2_body(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            timezone=timezone,
            environment=environment,
            explain=explain,
        )
        response = await self.client.post('/v2/query', headers={'accept': accept}, json=body)
        self.handle_response_errors(response)
        return response
