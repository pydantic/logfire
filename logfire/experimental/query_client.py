from __future__ import annotations

import json
import platform
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from types import TracebackType
from typing import TYPE_CHECKING, Any, Generic, Literal, TypedDict, TypeVar, overload

from typing_extensions import NotRequired, Self, TypeAlias, deprecated

from logfire import VERSION
from logfire._internal.config import get_base_url_from_token

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


class RowQueryResultsV2(TypedDict):
    """The row-oriented results of a JSON-format query."""

    columns: list[ColumnDetails]
    rows: list[dict[str, Any]]


class RowQueryResultsV2Explained(RowQueryResultsV2):
    logical_plan: Any
    physical_plan: Any
    physical_plan_with_metrics: Any


class StreamSchemaMessage(TypedDict):
    """First line of the NDJSON stream (omitted when ``include_schema=False``)."""

    type: Literal['schema']
    schema: dict[str, Any]


class StreamExplainMessage(TypedDict):
    """Emitted when ``explain=True``, after ``schema`` and before any ``data``."""

    type: Literal['explain']
    logical_plan: NotRequired[Any]
    physical_plan: NotRequired[Any]


class StreamDataMessage(TypedDict):
    """One per Arrow record batch; repeats."""

    type: Literal['data']
    rows: list[dict[str, Any]]


class StreamErrorMessage(TypedDict):
    """Emitted when a record batch fails. Always followed by an ``end`` message."""

    type: Literal['error']
    message: str


class StreamEndMessage(TypedDict):
    """Final line of the stream. ``error`` is set if the stream failed mid-flight."""

    type: Literal['end']
    row_count: int
    physical_plan_with_metrics: NotRequired[Any]
    error: NotRequired[str]


StreamMessage: TypeAlias = (
    StreamSchemaMessage | StreamExplainMessage | StreamDataMessage | StreamErrorMessage | StreamEndMessage
)


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


def _map_v2_result(obj: dict[str, Any]) -> RowQueryResultsV2 | RowQueryResultsV2Explained:
    mapped: RowQueryResultsV2 | RowQueryResultsV2Explained = {
        'columns': _transform_fields_for_backwards_compatibility(obj['schema']['fields']),
        'rows': obj['data'],
    }
    if 'logical_plan' in obj:
        # All the plan keys are guaranteed to be present:
        for k in ['logical_plan', 'physical_plan', 'physical_plan_with_metrics']:
            mapped[k] = obj[k]

    return mapped


T = TypeVar('T', bound=BaseClient)


_ACCEPT = Literal['application/json', 'application/vnd.apache.arrow.stream', 'text/csv']
_USER_AGENT = f'logfire-sdk-python/{VERSION} (Python {platform.python_version()}, os {platform.platform()}, arch {platform.machine()})'
_MIN_DATETIME = datetime(2020, 1, 1, tzinfo=timezone.utc)


class _BaseLogfireQueryClient(Generic[T]):
    def __init__(self, base_url: str, read_token: str, timeout: Timeout, client: type[T], **client_kwargs: Any):
        self.base_url = base_url
        self.read_token = read_token
        self.timeout = timeout
        headers = client_kwargs.pop('headers', {})
        headers['authorization'] = read_token
        headers.setdefault('user-agent', _USER_AGENT)
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

    def _build_v2_body(
        self,
        sql: str,
        min_timestamp: datetime | None,
        max_timestamp: datetime | None,
        limit: int | None,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: bool = False,
        include_schema: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {'sql': sql, 'explain': explain, 'include_schema': include_schema}

        if limit is not None:
            body['limit'] = limit
        body['min_timestamp'] = (min_timestamp or _MIN_DATETIME).isoformat()
        if max_timestamp is not None:
            body['max_timestamp'] = max_timestamp.isoformat()
        if params is not None:
            body['params'] = params
        if timezone is not None:
            body['timezone'] = timezone
        if isinstance(deployment_environment, str):
            deployment_environment = [deployment_environment]
        if deployment_environment is not None:
            body['deployment_environment'] = deployment_environment
        return body

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

    @deprecated('query_json() is deprecated, use query_json_rows() instead', stacklevel=2)
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
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: Literal[True],
    ) -> RowQueryResultsV2Explained: ...

    @overload
    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: Literal[True],
    ) -> RowQueryResultsV2Explained: ...

    @overload
    @deprecated('Using query_json_rows() without a min_timestamp is deprecated')
    def query_json_rows(
        self,
        sql: str,
        min_timestamp: None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: Literal[False] = ...,
    ) -> RowQueryResultsV2: ...

    @overload
    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: Literal[False] = ...,
    ) -> RowQueryResultsV2: ...

    def query_json_rows(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: bool = False,
    ) -> RowQueryResultsV2 | RowQueryResultsV2Explained:
        """Query Logfire data and return the results as a row-oriented dictionary."""
        response = self._query_v2(
            accept='application/json',
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            params=params,
            timezone=timezone,
            deployment_environment=deployment_environment,
            explain=explain,
        )
        return _map_v2_result(response.json())

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
        with pyarrow.ipc.open_stream(response.content) as reader:
            arrow_table: Table = reader.read_all()
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

    @contextmanager
    def query_stream(
        self,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        *,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: bool = False,
        include_schema: bool = True,
    ) -> Generator[Generator[StreamMessage]]:
        body = self._build_v2_body(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            params=params,
            timezone=timezone,
            deployment_environment=deployment_environment,
            explain=explain,
            include_schema=include_schema,
        )
        with self.client.stream('POST', '/v2/query', headers={'accept': 'application/x-ndjson'}, json=body) as response:
            if response.status_code != 200:
                response.read()
                self.handle_response_errors(response)
            yield from (json.loads(line) for line in response.iter_lines() if line)

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

    def _query_v2(
        self,
        *,
        accept: _ACCEPT,
        sql: str,
        min_timestamp: datetime | None = None,
        max_timestamp: datetime | None = None,
        limit: int | None = None,
        params: dict[str, str] | None = None,
        timezone: str | None = None,
        deployment_environment: str | list[str] | None = None,
        explain: bool = False,
    ) -> Response:

        body = self._build_v2_body(
            sql=sql,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            limit=limit,
            params=params,
            timezone=timezone,
            deployment_environment=deployment_environment,
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
        with pyarrow.ipc.open_stream(response.content) as reader:
            arrow_table: Table = reader.read_all()
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
