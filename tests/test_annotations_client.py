from __future__ import annotations

import httpx
import pytest

from logfire._internal.annotations_client import AnnotationsClient


def _make_client(handler: httpx.MockTransport) -> AnnotationsClient:
    """Create an AnnotationsClient backed by a mock transport."""
    mock_httpx = httpx.AsyncClient(transport=handler, base_url='https://test.logfire.dev')
    return AnnotationsClient(base_url='https://test.logfire.dev', token='test-token', client=mock_httpx)


@pytest.mark.anyio
async def test_create_annotations_batch_success() -> None:
    """Successful batch creation sends the correct payload."""
    recorded_requests: list[httpx.Request] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={'ok': True})

    client = _make_client(httpx.MockTransport(mock_handler))

    annotations = [
        {'trace_id': 'abc123', 'span_id': 'def456', 'name': 'helpfulness', 'value': True},
    ]
    await client.create_annotations_batch(annotations)

    assert len(recorded_requests) == 1
    assert recorded_requests[0].url.path == '/v1/annotations'


@pytest.mark.anyio
async def test_create_annotations_batch_auth_header() -> None:
    """Write token is sent as Authorization header without Bearer prefix."""
    recorded_headers: list[httpx.Headers] = []

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_headers.append(request.headers)
        return httpx.Response(200, json={'ok': True})

    mock_httpx = httpx.AsyncClient(
        transport=httpx.MockTransport(mock_handler),
        base_url='https://test.logfire.dev',
        headers={'Authorization': 'my-write-token'},
    )
    client = AnnotationsClient(base_url='https://test.logfire.dev', token='my-write-token', client=mock_httpx)

    await client.create_annotations_batch([{'name': 'test'}])

    assert recorded_headers[0]['authorization'] == 'my-write-token'


@pytest.mark.anyio
async def test_create_annotations_batch_retries_on_5xx() -> None:
    """5xx errors trigger a single retry."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(500, text='Internal Server Error')
        return httpx.Response(200, json={'ok': True})

    client = _make_client(httpx.MockTransport(mock_handler))
    await client.create_annotations_batch([{'name': 'test'}])

    assert call_count == 2


@pytest.mark.anyio
async def test_create_annotations_batch_4xx_no_retry() -> None:
    """4xx errors do not trigger a retry."""
    call_count = 0

    async def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(400, text='Bad Request')

    client = _make_client(httpx.MockTransport(mock_handler))
    await client.create_annotations_batch([{'name': 'test'}])

    assert call_count == 1


@pytest.mark.anyio
async def test_close() -> None:
    """close() shuts down the underlying client."""
    client = AnnotationsClient(base_url='https://test.logfire.dev', token='test-token')
    await client.close()
