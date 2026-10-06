"""Tests for how the query clients classify HTTP responses.

These use an `httpx.MockTransport` rather than the cassettes used by `test_query_client.py`,
because a healthy server never produces the responses being exercised here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from logfire.query_client import (
    AsyncLogfireQueryClient,
    LogfireQueryClient,
    QueryExecutionError,
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
