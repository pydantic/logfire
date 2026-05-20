from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from logfire._internal.forwarding import (
    OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
    OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
    ForwardingContentType,
    ForwardingErrorResponse,
    ForwardingRequest,
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
