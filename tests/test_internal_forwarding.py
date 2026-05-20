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
