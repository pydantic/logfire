from __future__ import annotations

import os
import posixpath
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from threading import Condition, Thread, current_thread
from time import monotonic
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import unquote, urljoin

from google.protobuf.json_format import MessageToJson
from opentelemetry.exporter.otlp.proto.http._log_exporter import DEFAULT_TIMEOUT as DEFAULT_LOGS_TIMEOUT
from opentelemetry.exporter.otlp.proto.http.metric_exporter import DEFAULT_TIMEOUT as DEFAULT_METRICS_TIMEOUT
from opentelemetry.exporter.otlp.proto.http.trace_exporter import DEFAULT_TIMEOUT as DEFAULT_TRACES_TIMEOUT
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceResponse,
)
from opentelemetry.sdk.environment_variables import (
    OTEL_EXPORTER_OTLP_LOGS_TIMEOUT,
    OTEL_EXPORTER_OTLP_METRICS_TIMEOUT,
    OTEL_EXPORTER_OTLP_TIMEOUT,
    OTEL_EXPORTER_OTLP_TRACES_TIMEOUT,
)

from logfire._internal.exporters.otlp import OTLPExporterHttpSession
from logfire.version import VERSION

if TYPE_CHECKING:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES = 64 * 1024 * 1024
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024
_MEDIA_TYPE_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+/[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PARAMETER_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+=")
ForwardingPath = Literal['/v1/traces', '/v1/logs', '/v1/metrics']
_SIGNAL_TIMEOUT_ENV: dict[ForwardingPath, str] = {
    '/v1/traces': OTEL_EXPORTER_OTLP_TRACES_TIMEOUT,
    '/v1/logs': OTEL_EXPORTER_OTLP_LOGS_TIMEOUT,
    '/v1/metrics': OTEL_EXPORTER_OTLP_METRICS_TIMEOUT,
}
_DEFAULT_TIMEOUT: dict[ForwardingPath, float] = {
    '/v1/traces': float(DEFAULT_TRACES_TIMEOUT),
    '/v1/logs': float(DEFAULT_LOGS_TIMEOUT),
    '/v1/metrics': float(DEFAULT_METRICS_TIMEOUT),
}


class ForwardingContentType(Enum):
    PROTOBUF = 'application/x-protobuf'
    JSON = 'application/json'


@dataclass(frozen=True)
class ForwardingRequest:
    path: ForwardingPath
    body: bytes
    content_type: ForwardingContentType
    content_type_header: str
    content_encoding: str | None
    user_agent: str | None


@dataclass(frozen=True)
class ForwardingErrorResponse:
    status_code: int
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ForwardingAdmissionResult:
    response: Literal['success', 'partial_success']
    message: str | None


@dataclass(frozen=True)
class QueuedForwardingRequest:
    request: ForwardingRequest
    tokens: tuple[str, ...]


class OTLPForwardingPipeline:
    def __init__(
        self,
        *,
        base_url: str,
        session: OTLPExporterHttpSession,
        max_queued_body_bytes: int,
    ) -> None:
        self.base_url = base_url
        self.session = session
        self.max_queued_body_bytes = max_queued_body_bytes
        self.queue: deque[QueuedForwardingRequest] = deque()
        self.queued_body_bytes = 0
        self.active_send_count = 0
        self.worker: Thread | None = None
        self.closed = False
        self.session_closed = False
        self.condition = Condition()

    def enqueue(self, queued_request: QueuedForwardingRequest) -> bool:
        body_size = len(queued_request.request.body)
        with self.condition:
            if self.closed or self.queued_body_bytes + body_size > self.max_queued_body_bytes:
                return False

            self.queue.append(queued_request)
            self.queued_body_bytes += body_size
            self._ensure_worker_locked()
            self.condition.notify_all()
            return True

    def _ensure_worker_locked(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return

        self.worker = Thread(target=self._run, daemon=False)
        self.worker.start()
        self.condition.notify_all()

    def _send(self, queued_request: QueuedForwardingRequest) -> None:
        import logfire

        request = queued_request.request
        url = urljoin(self.base_url.rstrip('/') + '/', request.path.lstrip('/'))
        timeout = forwarding_timeout_for_path(request.path)
        for token in queued_request.tokens:
            headers = build_forwarding_headers(request, token=token)
            try:
                with logfire.suppress_instrumentation():
                    self.session.post(url, data=request.body, headers=headers, timeout=timeout)
            except Exception:
                continue

    def _run(self) -> None:
        try:
            while True:
                with self.condition:
                    if not self.queue:
                        return

                    queued_request = self.queue.popleft()
                    self.queued_body_bytes -= len(queued_request.request.body)
                    self.active_send_count += 1
                    self.condition.notify_all()

                try:
                    self._send(queued_request)
                except Exception:
                    pass
                finally:
                    with self.condition:
                        self.active_send_count -= 1
                        self.condition.notify_all()
        finally:
            with self.condition:
                if self.worker is current_thread():
                    self.worker = None
                    self.condition.notify_all()

    def force_flush(self, timeout_millis: int) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        with self.condition:
            while self.queue or self.active_send_count:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self.condition.wait(timeout=remaining)
            return True

    def _has_live_worker_locked(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _close_session_once(self) -> None:
        if not self.session_closed:
            self.session.close()
            self.session_closed = True

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        complete = True
        with self.condition:
            self.closed = True
            self.condition.notify_all()
            if drain_queued and self.queue:
                self._ensure_worker_locked()

            while self.queue:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    self.queue.clear()
                    self.queued_body_bytes = 0
                    complete = False
                    self.condition.notify_all()
                    break
                self.condition.wait(timeout=remaining)

            while self.active_send_count or self._has_live_worker_locked():
                self.condition.wait()

            self._close_session_once()
            return complete


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name:
            return value
    return None


def parse_forwarding_content_type(headers: Mapping[str, str]) -> ForwardingContentType | None:
    content_type = _get_header(headers, 'content-type')
    if content_type is None:
        return None

    parts = [part.strip() for part in content_type.split(';')]
    media_type = parts[0]
    if not media_type or not _MEDIA_TYPE_RE.fullmatch(media_type):
        return None

    for parameter in parts[1:]:
        if parameter and not _PARAMETER_RE.match(parameter):
            return None

    media_type = media_type.lower()
    if media_type == ForwardingContentType.PROTOBUF.value:
        return ForwardingContentType.PROTOBUF
    if media_type == ForwardingContentType.JSON.value:
        return ForwardingContentType.JSON
    return None


def _invalid_path_response() -> ForwardingErrorResponse:
    return ForwardingErrorResponse(
        status_code=400,
        content_type='text/plain',
        content=b'Invalid path: must be /v1/traces, /v1/logs, or /v1/metrics',
    )


def _normalize_forwarding_path(path: str) -> ForwardingPath | ForwardingErrorResponse:
    if '://' in path or '?' in path or '#' in path:
        return _invalid_path_response()

    if not path.startswith('/'):
        path = '/' + path

    normalized_path = posixpath.normpath(unquote(path))
    if normalized_path == '/v1/traces':
        return '/v1/traces'
    if normalized_path == '/v1/logs':
        return '/v1/logs'
    if normalized_path == '/v1/metrics':
        return '/v1/metrics'
    return _invalid_path_response()


def _extract_forwarding_representation_headers(
    headers: Mapping[str, str],
) -> tuple[str | None, str | None, str | None]:
    return (
        _get_header(headers, 'content-type'),
        _get_header(headers, 'content-encoding'),
        _get_header(headers, 'user-agent'),
    )


def build_forwarding_request(
    *,
    path: str,
    headers: Mapping[str, str],
    body: bytes | None,
    max_body_size: int = OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
) -> ForwardingRequest | ForwardingErrorResponse:
    normalized_path = _normalize_forwarding_path(path)
    if isinstance(normalized_path, ForwardingErrorResponse):
        return normalized_path

    normalized_body = body or b''
    if len(normalized_body) > max_body_size:
        return ForwardingErrorResponse(
            status_code=413,
            content_type='text/plain',
            content=b'Payload too large',
        )

    content_type = parse_forwarding_content_type(headers)
    if content_type is None:
        return ForwardingErrorResponse(
            status_code=415,
            content_type='text/plain',
            content=b'Unsupported content type',
        )

    content_type_header, content_encoding, user_agent = _extract_forwarding_representation_headers(headers)
    assert content_type_header is not None
    return ForwardingRequest(
        path=normalized_path,
        body=normalized_body,
        content_type=content_type,
        content_type_header=content_type_header,
        content_encoding=content_encoding,
        user_agent=user_agent,
    )


def response_content_type(content_type: ForwardingContentType) -> str:
    return content_type.value


def response_message_for_path(path: ForwardingPath) -> type[Any]:
    if path == '/v1/traces':
        return ExportTraceServiceResponse
    if path == '/v1/logs':
        return ExportLogsServiceResponse
    return ExportMetricsServiceResponse


def build_success_response(request: ForwardingRequest) -> ForwardExportRequestResponse:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

    message = response_message_for_path(request.path)()
    if request.content_type is ForwardingContentType.PROTOBUF:
        content = message.SerializeToString()
    else:
        content = MessageToJson(message, indent=None).encode()

    return ForwardExportRequestResponse(
        status_code=200,
        headers={'Content-Type': response_content_type(request.content_type)},
        content=content,
    )


def build_partial_success_response(
    request: ForwardingRequest,
    *,
    message: str,
) -> ForwardExportRequestResponse:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

    response_message = response_message_for_path(request.path)()
    partial_success = response_message.partial_success
    if request.path == '/v1/traces':
        partial_success.rejected_spans = 0
    elif request.path == '/v1/logs':
        partial_success.rejected_log_records = 0
    else:
        partial_success.rejected_data_points = 0
    partial_success.error_message = message

    if request.content_type is ForwardingContentType.PROTOBUF:
        content = response_message.SerializeToString()
    else:
        content = MessageToJson(
            response_message,
            indent=None,
            always_print_fields_with_no_presence=True,
        ).encode()

    return ForwardExportRequestResponse(
        status_code=200,
        headers={'Content-Type': response_content_type(request.content_type)},
        content=content,
    )


def _forwarding_user_agent(user_agent: str | None) -> str:
    forwarding_user_agent = f'logfire-proxy/{VERSION}'
    if user_agent:
        return f'{forwarding_user_agent} {user_agent}'
    return forwarding_user_agent


def build_forwarding_headers(request: ForwardingRequest, *, token: str) -> dict[str, str]:
    headers = {
        'Content-Type': request.content_type_header,
        'User-Agent': _forwarding_user_agent(request.user_agent),
        'Authorization': token,
    }
    if request.content_encoding is not None:
        headers['Content-Encoding'] = request.content_encoding
    return headers


def forwarding_timeout_for_path(path: ForwardingPath) -> float:
    signal_timeout = os.environ.get(_SIGNAL_TIMEOUT_ENV[path])
    if signal_timeout is not None:
        return float(signal_timeout)

    generic_timeout = os.environ.get(OTEL_EXPORTER_OTLP_TIMEOUT)
    if generic_timeout is not None:
        return float(generic_timeout)

    return _DEFAULT_TIMEOUT[path]
