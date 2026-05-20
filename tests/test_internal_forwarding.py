from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from logfire._internal.forwarding import (
    OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
    OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
    ForwardingAdmissionResult,
    ForwardingContentType,
    ForwardingErrorResponse,
    ForwardingRequest,
    QueuedForwardingRequest,
    _extract_forwarding_representation_headers,  # pyright: ignore[reportPrivateUsage]
    _normalize_forwarding_path,  # pyright: ignore[reportPrivateUsage]
    build_forwarding_request,
    parse_forwarding_content_type,
)


def test_forwarding_byte_limit_constants() -> None:
    assert OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES == 64 * 1024 * 1024
    assert OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES == 50 * 1024 * 1024


def test_forwarding_content_type_values() -> None:
    assert ForwardingContentType.PROTOBUF.value == 'application/x-protobuf'
    assert ForwardingContentType.JSON.value == 'application/json'


def test_forwarding_request_record() -> None:
    request = ForwardingRequest(
        path='/v1/traces',
        body=b'trace-data',
        content_type=ForwardingContentType.PROTOBUF,
        content_type_header='application/x-protobuf',
        content_encoding='gzip',
        user_agent='browser-agent',
    )

    assert request.path == '/v1/traces'
    assert request.body == b'trace-data'
    assert request.content_type is ForwardingContentType.PROTOBUF
    assert request.content_type_header == 'application/x-protobuf'
    assert request.content_encoding == 'gzip'
    assert request.user_agent == 'browser-agent'
    with pytest.raises(FrozenInstanceError):
        setattr(request, 'body', b'other')


def test_forwarding_error_response_record() -> None:
    response = ForwardingErrorResponse(
        status_code=415,
        content_type='text/plain',
        content=b'Unsupported content type',
    )

    assert response.status_code == 415
    assert response.content_type == 'text/plain'
    assert response.content == b'Unsupported content type'
    with pytest.raises(FrozenInstanceError):
        setattr(response, 'status_code', 400)


def test_forwarding_admission_result_record() -> None:
    success = ForwardingAdmissionResult(response='success', message=None)
    partial_success = ForwardingAdmissionResult(response='partial_success', message='queue full')

    assert success.response == 'success'
    assert success.message is None
    assert partial_success.response == 'partial_success'
    assert partial_success.message == 'queue full'
    with pytest.raises(FrozenInstanceError):
        setattr(partial_success, 'message', 'closed')


def test_queued_forwarding_request_record() -> None:
    request = ForwardingRequest(
        path='/v1/logs',
        body=b'log-data',
        content_type=ForwardingContentType.JSON,
        content_type_header='application/json',
        content_encoding=None,
        user_agent=None,
    )
    queued_request = QueuedForwardingRequest(request=request, tokens=('token-1', 'token-2'))

    assert queued_request.request is request
    assert queued_request.tokens == ('token-1', 'token-2')
    with pytest.raises(FrozenInstanceError):
        setattr(queued_request, 'tokens', ('token-3',))


@pytest.mark.parametrize(
    ('headers', 'expected'),
    [
        ({'Content-Type': 'application/x-protobuf'}, ForwardingContentType.PROTOBUF),
        ({'Content-Type': 'application/json'}, ForwardingContentType.JSON),
        ({'Content-Type': 'application/json; charset=utf-8'}, ForwardingContentType.JSON),
        ({'content-type': 'Application/JSON'}, ForwardingContentType.JSON),
        ({}, None),
        ({'Content-Type': ''}, None),
        ({'Content-Type': 'not a media type'}, None),
        ({'Content-Type': 'application/json; charset'}, None),
        ({'Content-Type': 'text/plain'}, None),
    ],
)
def test_parse_forwarding_content_type(headers: dict[str, str], expected: ForwardingContentType | None) -> None:
    assert parse_forwarding_content_type(headers) is expected


@pytest.mark.parametrize(
    ('path', 'expected'),
    [
        ('/v1/traces', '/v1/traces'),
        ('/v1/logs', '/v1/logs'),
        ('/v1/metrics', '/v1/metrics'),
        ('v1/traces', '/v1/traces'),
    ],
)
def test_normalize_forwarding_path_valid(path: str, expected: str) -> None:
    assert _normalize_forwarding_path(path) == expected


@pytest.mark.parametrize(
    'path',
    [
        '/invalid',
        '/v1/traces/../secret',
        '/v1/traces/%2e%2e/secret',
        'https://example.com/v1/traces',
        '/v1/traces?foo=bar',
        '/v1/traces#fragment',
    ],
)
def test_normalize_forwarding_path_rejections(path: str) -> None:
    response = _normalize_forwarding_path(path)

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400
    assert response.content_type == 'text/plain'
    assert response.content == b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics'


def test_extract_forwarding_representation_headers() -> None:
    headers = {
        'content-type': 'application/json; charset=utf-8',
        'CONTENT-ENCODING': 'gzip',
        'User-Agent': 'browser-agent',
        'Authorization': 'client-token',
        'Cookie': 'session=secret',
        'Host': 'example.com',
        'X-Api-Key': 'secret',
    }

    content_type, content_encoding, user_agent = _extract_forwarding_representation_headers(headers)

    assert content_type == 'application/json; charset=utf-8'
    assert content_encoding == 'gzip'
    assert user_agent == 'browser-agent'


def test_extract_forwarding_representation_headers_missing_optional_values() -> None:
    content_type, content_encoding, user_agent = _extract_forwarding_representation_headers(
        {'Content-Type': 'application/x-protobuf'}
    )

    assert content_type == 'application/x-protobuf'
    assert content_encoding is None
    assert user_agent is None


def test_build_forwarding_request_valid_protobuf() -> None:
    request = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf', 'Content-Encoding': 'gzip', 'User-Agent': 'browser'},
        body=b'trace-data',
    )

    assert isinstance(request, ForwardingRequest)
    assert request.path == '/v1/traces'
    assert request.body == b'trace-data'
    assert request.content_type is ForwardingContentType.PROTOBUF
    assert request.content_type_header == 'application/x-protobuf'
    assert request.content_encoding == 'gzip'
    assert request.user_agent == 'browser'


def test_build_forwarding_request_valid_json_with_parameters() -> None:
    request = build_forwarding_request(
        path='/v1/logs',
        headers={'Content-Type': 'application/json; charset=utf-8'},
        body=b'{"resourceLogs":[]}',
    )

    assert isinstance(request, ForwardingRequest)
    assert request.path == '/v1/logs'
    assert request.body == b'{"resourceLogs":[]}'
    assert request.content_type is ForwardingContentType.JSON
    assert request.content_type_header == 'application/json; charset=utf-8'
    assert request.content_encoding is None
    assert request.user_agent is None


def test_build_forwarding_request_none_body_normalizes_to_empty_bytes() -> None:
    request = build_forwarding_request(
        path='/v1/metrics',
        headers={'Content-Type': 'application/x-protobuf'},
        body=None,
    )

    assert isinstance(request, ForwardingRequest)
    assert request.body == b''


@pytest.mark.parametrize(
    ('body', 'max_body_size'),
    [
        (b'12345', 4),
        (b'12345', 3),
    ],
)
def test_build_forwarding_request_oversized_body(body: bytes, max_body_size: int) -> None:
    response = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=body,
        max_body_size=max_body_size,
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 413
    assert response.content_type == 'text/plain'
    assert response.content == b'Payload too large'


def test_build_forwarding_request_custom_max_body_size_allows_body_at_limit() -> None:
    request = build_forwarding_request(
        path='/v1/traces',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'12345',
        max_body_size=5,
    )

    assert isinstance(request, ForwardingRequest)
    assert request.body == b'12345'


@pytest.mark.parametrize(
    'headers',
    [
        {},
        {'Content-Type': 'text/plain'},
    ],
)
def test_build_forwarding_request_unsupported_content_type(headers: dict[str, str]) -> None:
    response = build_forwarding_request(path='/v1/traces', headers=headers, body=b'')

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 415
    assert response.content_type == 'text/plain'
    assert response.content == b'Unsupported content type'


def test_build_forwarding_request_invalid_path() -> None:
    response = build_forwarding_request(
        path='/invalid',
        headers={'Content-Type': 'application/x-protobuf'},
        body=b'',
    )

    assert isinstance(response, ForwardingErrorResponse)
    assert response.status_code == 400
