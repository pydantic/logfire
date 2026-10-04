"""Tests for how the query clients classify HTTP responses.

These use an `httpx.MockTransport` rather than the cassettes used by `test_query_client.py`,
because a healthy server never produces the responses being exercised here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from logfire.query_client import (
    AsyncLogfireQueryClient,
    LogfireQueryClient,
    QueryExecutionError,
    QueryRateLimitedError,
    QueryRequestError,
    UnexpectedResponseError,
)

BASE_URL = 'http://localhost:3000'
READ_TOKEN = 'fake-read-token'
SQL = 'SELECT message FROM records'
MIN_TIMESTAMP = datetime(2020, 1, 1, tzinfo=timezone.utc)


def mock_transport(status_code: int, **response_kwargs: Any) -> httpx.MockTransport:
    """A transport answering every request with the given status code and body."""
    return httpx.MockTransport(lambda request: httpx.Response(status_code, **response_kwargs))


UNEXPECTED_STATUS_CODES = [
    204,  # no content, so the client would otherwise parse an empty body as a result
    301,  # a redirect the client isn't configured to follow
    404,
    500,
    502,
    503,
]


@pytest.mark.parametrize('status_code', UNEXPECTED_STATUS_CODES)
def test_query_unexpected_status_code_sync(status_code: int):
    with LogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(status_code, text='upstream is unhappy')
    ) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert str(status_code) in str(exc_info.value)
    assert 'upstream is unhappy' in str(exc_info.value)


@pytest.mark.anyio
@pytest.mark.parametrize('status_code', UNEXPECTED_STATUS_CODES)
async def test_query_unexpected_status_code_async(status_code: int):
    async with AsyncLogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(status_code, text='upstream is unhappy')
    ) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            await client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert str(status_code) in str(exc_info.value)
    assert 'upstream is unhappy' in str(exc_info.value)


def test_query_unexpected_status_code_with_undecodable_json_body():
    """An unexpected response may claim to be JSON while being truncated, and must still raise our own error."""
    transport = mock_transport(500, headers={'content-type': 'application/json'}, text='{"detail": "trunca')
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert '{"detail": "trunca' in str(exc_info.value)


def test_info_unexpected_status_code_sync():
    with LogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(503, text='unavailable')
    ) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.info()

    assert 'unavailable' in str(exc_info.value)


@pytest.mark.anyio
async def test_info_unexpected_status_code_async():
    async with AsyncLogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(503, text='unavailable')
    ) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            await client.info()

    assert 'unavailable' in str(exc_info.value)


@pytest.mark.parametrize(
    ['status_code', 'expected_error'],
    [(400, QueryExecutionError), (422, QueryRequestError)],
)
@pytest.mark.parametrize(
    ['response_kwargs', 'expected_arg'],
    [
        pytest.param({'json': {'detail': 'nope'}}, {'detail': 'nope'}, id='json'),
        pytest.param({'text': 'nope'}, 'nope', id='text'),
        pytest.param(
            {'headers': {'content-type': 'APPLICATION/JSON; charset=utf-8'}, 'json': 1},
            1,
            id='json-content-type-with-parameters',
        ),
    ],
)
def test_query_request_errors_sync(
    status_code: int, expected_error: type[Exception], response_kwargs: dict[str, Any], expected_arg: Any
):
    with LogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(status_code, **response_kwargs)
    ) as client:
        with pytest.raises(expected_error) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.args == (expected_arg,)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ['status_code', 'expected_error'],
    [(400, QueryExecutionError), (422, QueryRequestError)],
)
async def test_query_request_errors_async(status_code: int, expected_error: type[Exception]):
    async with AsyncLogfireQueryClient(
        read_token=READ_TOKEN, base_url=BASE_URL, transport=mock_transport(status_code, json={'detail': 'nope'})
    ) as client:
        with pytest.raises(expected_error) as exc_info:
            await client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.args == ({'detail': 'nope'},)


# The structured error body a server sends for a failed query, with or without a problem detail.
LEGACY_ERROR = {'detail': [{'type': 'query_error', 'msg': 'column "nope" does not exist'}]}


def problem_body(status: int, problem_type: str, **extra: Any) -> dict[str, Any]:
    return {
        'type': f'https://logfire.pydantic.dev/-/errors/{problem_type}',
        'title': 'Query failed',
        'status': status,
        'detail': 'column "nope" does not exist',
        'error_details': LEGACY_ERROR,
        **extra,
    }


def negotiating_transport(status_code: int, problem: dict[str, Any], headers: dict[str, str] | None = None):
    """A server that sends a problem detail only when the request's `Accept` names `application/problem+json`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if 'application/problem+json' in request.headers.get('accept', ''):
            return httpx.Response(
                status_code,
                headers={'content-type': 'application/problem+json', **(headers or {})},
                content=json.dumps(problem).encode(),
            )
        return httpx.Response(status_code, json=LEGACY_ERROR, headers=headers)

    return httpx.MockTransport(handler)


@pytest.mark.parametrize(
    ['status_code', 'expected_error'],
    [(400, QueryExecutionError), (422, QueryRequestError)],
)
@pytest.mark.parametrize('new_server', [False, True], ids=['old-server', 'new-server'])
def test_query_error_args_match_across_server_versions(
    status_code: int, expected_error: type[Exception], new_server: bool
):
    problem = problem_body(status_code, 'query-error', retryable=False)
    transport = (
        negotiating_transport(status_code, problem) if new_server else mock_transport(status_code, json=LEGACY_ERROR)
    )
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(expected_error) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    error = exc_info.value
    assert type(error) is expected_error
    assert error.args == (LEGACY_ERROR,)
    assert isinstance(error, (QueryExecutionError, QueryRequestError))
    if new_server:
        assert error.problem == problem
        assert error.problem_type == 'https://logfire.pydantic.dev/-/errors/query-error'
        assert error.retryable is False
    else:
        assert error.problem is None
        assert error.problem_type is None
        assert error.retryable is None
    assert error.retry_after is None


def test_old_client_against_new_server_gets_legacy_body():
    """A client that does not name `application/problem+json` gets the legacy body and content type."""
    transport = negotiating_transport(400, problem_body(400, 'query-error'))
    with httpx.Client(transport=transport, base_url=BASE_URL) as client:
        response = client.post('/v2/query', headers={'accept': 'application/json'}, json={})
    assert response.headers['content-type'] == 'application/json'
    assert response.json() == LEGACY_ERROR


@pytest.mark.parametrize(
    ['method', 'data_type'],
    [
        ('query_json_rows', 'application/json'),
        ('query_csv', 'text/csv'),
    ],
)
def test_accept_header_ranks_data_type_first(method: str, data_type: str):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers['accept'])
        return httpx.Response(400, json=LEGACY_ERROR)

    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(QueryExecutionError):
            getattr(client, method)(SQL, min_timestamp=MIN_TIMESTAMP)

    assert seen == [f'{data_type}, application/problem+json;q=0.9']


def test_rate_limited_problem_sync():
    problem = problem_body(
        429, 'rate-limit', retryable=True, retry_after=30, rule_id='rule-1', expires_at='2030-01-01T00:00:00Z'
    )
    transport = negotiating_transport(429, problem, headers={'retry-after': '30'})
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    error = exc_info.value
    assert isinstance(error, QueryRateLimitedError)
    assert str(error).startswith('Unexpected response status code 429: ')
    assert error.retry_after == 30.0
    assert error.retryable is True
    assert error.problem_type == 'https://logfire.pydantic.dev/-/errors/rate-limit'
    assert error.problem is not None
    assert error.problem['rule_id'] == 'rule-1'
    assert error.problem['expires_at'] == '2030-01-01T00:00:00Z'


@pytest.mark.anyio
async def test_rate_limited_problem_async():
    problem = problem_body(429, 'rate-limit', retryable=True, retry_after=12)
    transport = negotiating_transport(429, problem, headers={'retry-after': '12'})
    async with AsyncLogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(QueryRateLimitedError) as exc_info:
            await client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.retry_after == 12.0


@pytest.mark.parametrize(
    ['headers', 'expected'],
    [
        pytest.param({'retry-after': '7'}, 7.0, id='seconds'),
        pytest.param({'retry-after': 'Wed, 21 Oct 2015 07:28:00 GMT'}, None, id='http-date'),
        pytest.param({}, None, id='absent'),
    ],
)
def test_rate_limited_legacy_server(headers: dict[str, str], expected: float | None):
    """A server without problem details still raises a subclass of the error raised before."""
    transport = mock_transport(429, text='slow down', headers=headers)
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(QueryRateLimitedError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.args == ("Unexpected response status code 429: 'slow down'",)
    assert exc_info.value.problem is None
    assert exc_info.value.retry_after == expected


def test_retry_after_from_problem_body_when_header_missing():
    problem = problem_body(503, 'query-timeout', retryable=True, retry_after=5)
    transport = negotiating_transport(503, problem)
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert type(exc_info.value) is UnexpectedResponseError
    assert exc_info.value.retry_after == 5.0
    assert exc_info.value.problem_type == 'https://logfire.pydantic.dev/-/errors/query-timeout'


@pytest.mark.parametrize(
    'content',
    [pytest.param(b'{"trunca', id='undecodable'), pytest.param(b'[1]', id='not-an-object')],
)
def test_malformed_problem_body(content: bytes):
    transport = mock_transport(500, headers={'content-type': 'application/problem+json'}, content=content)
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(UnexpectedResponseError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.problem is None


def test_problem_body_without_error_details_is_passed_whole():
    problem = {'type': 'about:blank', 'title': 'Bad Request', 'status': 400, 'detail': 'bad'}
    transport = mock_transport(400, headers={'content-type': 'application/problem+json'}, json=problem)
    with LogfireQueryClient(read_token=READ_TOKEN, base_url=BASE_URL, transport=transport) as client:
        with pytest.raises(QueryExecutionError) as exc_info:
            client.query_json_rows(SQL, min_timestamp=MIN_TIMESTAMP)

    assert exc_info.value.args == (problem,)
