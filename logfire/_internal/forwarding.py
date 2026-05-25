from __future__ import annotations

import os
import posixpath
import re
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from threading import Condition, RLock, Thread, current_thread
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
from logfire._internal.server_response import install_logfire_response_hook
from logfire._internal.utils import suppress_instrumentation
from logfire.version import VERSION

if TYPE_CHECKING:
    from logfire._internal.config import LogfireConfig
    from logfire.experimental.forwarding import ForwardExportRequestResponse

OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES = 64 * 1024 * 1024
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024
_MEDIA_TYPE_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+/[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_PARAMETER_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+=")
ForwardingPath = Literal['/v1/traces', '/v1/logs', '/v1/metrics']


@dataclass(frozen=True)
class ForwardingPathConfig:
    timeout_env: str
    default_timeout: float
    partial_success_rejected_attribute: str
    response_message_type: type[Any]

    def timeout(self) -> float:
        signal_timeout = os.environ.get(self.timeout_env)
        if signal_timeout is not None:
            return float(signal_timeout)

        generic_timeout = os.environ.get(OTEL_EXPORTER_OTLP_TIMEOUT)
        if generic_timeout is not None:
            return float(generic_timeout)

        return self.default_timeout


FORWARDING_CONFIGS: dict[ForwardingPath, ForwardingPathConfig] = {
    '/v1/traces': ForwardingPathConfig(
        timeout_env=OTEL_EXPORTER_OTLP_TRACES_TIMEOUT,
        default_timeout=float(DEFAULT_TRACES_TIMEOUT),
        partial_success_rejected_attribute='rejected_spans',
        response_message_type=ExportTraceServiceResponse,
    ),
    '/v1/logs': ForwardingPathConfig(
        timeout_env=OTEL_EXPORTER_OTLP_LOGS_TIMEOUT,
        default_timeout=float(DEFAULT_LOGS_TIMEOUT),
        partial_success_rejected_attribute='rejected_log_records',
        response_message_type=ExportLogsServiceResponse,
    ),
    '/v1/metrics': ForwardingPathConfig(
        timeout_env=OTEL_EXPORTER_OTLP_METRICS_TIMEOUT,
        default_timeout=float(DEFAULT_METRICS_TIMEOUT),
        partial_success_rejected_attribute='rejected_data_points',
        response_message_type=ExportMetricsServiceResponse,
    ),
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

    @property
    def path_config(self) -> ForwardingPathConfig:
        return FORWARDING_CONFIGS[self.path]


@dataclass(frozen=True)
class ForwardingErrorResponse:
    status_code: int
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ForwardingAdmissionResult:
    response: Literal['success', 'partial_success']
    message: str | None


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
        self.queue: deque[ForwardingRequest] = deque()
        self.queued_body_bytes = 0
        self.active_send_count = 0
        self.worker: Thread | None = None
        self.closed = False
        self.session_closed = False
        self.condition = Condition()
        self.tokens: list[str] = []

    def enqueue(self, queued_request: ForwardingRequest) -> bool:
        body_size = len(queued_request.body)
        with self.condition:
            if self.closed or self.queued_body_bytes + body_size > self.max_queued_body_bytes:
                return False

            self.queue.append(queued_request)
            self.queued_body_bytes += body_size

            if self.worker is None or not self.worker.is_alive():
                self.worker = Thread(target=self._run, daemon=False)
                self.worker.start()

            self.condition.notify_all()
            return True

    def _send(self, request: ForwardingRequest) -> None:
        url = urljoin(self.base_url.rstrip('/') + '/', request.path.lstrip('/'))
        timeout = request.path_config.timeout()
        for token in self.tokens:
            headers = build_forwarding_headers(request, token=token)
            try:
                with suppress_instrumentation():
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
                    self.queued_body_bytes -= len(queued_request.body)
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
                if self.closed and not self.queue and self.active_send_count == 0:
                    self._close_session_once()
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
            if not drain_queued:
                self.queue.clear()
                self.queued_body_bytes = 0
                self.condition.notify_all()

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
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self.condition.wait(timeout=remaining)

            self._close_session_once()
            return complete


class OTLPForwardingManager:
    def __init__(self, config: LogfireConfig) -> None:
        self.config = config
        self.pipelines: dict[str, OTLPForwardingPipeline] = {}
        self.closed = False
        self.lock = RLock()

    def has_destinations(self) -> bool:
        with self.lock:
            return bool(self.pipelines)

    def add_destination(self, *, base_url: str, token: str) -> None:
        with self.lock:
            if self.closed:
                return

            pipeline = self.pipelines.get(base_url)
            if pipeline is None:
                session = OTLPExporterHttpSession()
                install_logfire_response_hook(session, self.config.advanced.server_response_hook)
                pipeline = self.pipelines[base_url] = OTLPForwardingPipeline(
                    base_url=base_url,
                    session=session,
                    max_queued_body_bytes=OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
                )

            pipeline.tokens.append(token)

    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult:
        with self.lock:
            if self.closed:
                return ForwardingAdmissionResult(
                    response='partial_success',
                    message='Forwarding manager is closed; request was locally dropped.',
                )
            pipelines = tuple(self.pipelines.values())

        dropped_count = 0
        for pipeline in pipelines:
            if not pipeline.enqueue(request):
                dropped_count += 1

        if dropped_count == 0:
            return ForwardingAdmissionResult(response='success', message=None)
        return ForwardingAdmissionResult(
            response='partial_success',
            message=f'Forwarding request was locally dropped for {dropped_count} backend URL(s).',
        )

    def force_flush(self, timeout_millis: int) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        with self.lock:
            pipelines = tuple(self.pipelines.values())

        complete = True
        for pipeline in pipelines:
            remaining_millis = max(0, int((deadline - monotonic()) * 1000))
            if not pipeline.force_flush(remaining_millis):
                complete = False
        return complete

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        with self.lock:
            self.closed = True
            pipelines = tuple(self.pipelines.values())

        complete = True
        if not drain_queued:
            for pipeline in pipelines:
                if not pipeline.shutdown(0, drain_queued=False):
                    complete = False
            return complete

        for pipeline in pipelines:
            remaining_millis = max(0, int((deadline - monotonic()) * 1000))
            if not pipeline.shutdown(remaining_millis, drain_queued=drain_queued):
                complete = False
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
    paths = tuple(FORWARDING_CONFIGS)
    return ForwardingErrorResponse(
        status_code=400,
        content_type='text/plain',
        content=f'Invalid path: must be {", ".join(paths[:-1])}, or {paths[-1]}'.encode(),
    )


def _normalize_forwarding_path(path: str) -> ForwardingPath | ForwardingErrorResponse:
    if '://' in path or '?' in path or '#' in path:
        return _invalid_path_response()

    if not path.startswith('/'):
        path = '/' + path

    normalized_path = posixpath.normpath(unquote(path))
    if normalized_path in FORWARDING_CONFIGS:
        return normalized_path
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


def build_success_response(request: ForwardingRequest) -> ForwardExportRequestResponse:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

    message = request.path_config.response_message_type()
    if request.content_type is ForwardingContentType.PROTOBUF:
        content = message.SerializeToString()
    else:
        content = MessageToJson(message, indent=None).encode()

    return ForwardExportRequestResponse(
        status_code=200,
        headers={'Content-Type': request.content_type.value},
        content=content,
    )


def build_partial_success_response(
    request: ForwardingRequest,
    *,
    message: str,
) -> ForwardExportRequestResponse:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

    response_message = request.path_config.response_message_type()
    partial_success = response_message.partial_success
    setattr(partial_success, request.path_config.partial_success_rejected_attribute, 0)
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
        headers={'Content-Type': request.content_type.value},
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
