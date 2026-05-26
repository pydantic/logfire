from __future__ import annotations

import os
import posixpath
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from threading import Condition, Thread
from time import monotonic
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal
from urllib.parse import unquote, urljoin
from weakref import WeakMethod

from google.protobuf.json_format import MessageToJson
from google.protobuf.message import Message
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
    from logfire.experimental.forwarding import ForwardExportRequestResponse
    from logfire.types import ServerResponseCallback

OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES = 64 * 1024 * 1024
OTLP_FORWARDING_MAX_QUEUED_ITEMS = 1000
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES = 50 * 1024 * 1024
ForwardingPath = Literal['/v1/traces', '/v1/logs', '/v1/metrics']


@dataclass(frozen=True)
class ForwardingPathConfig:
    timeout_env: str
    default_timeout: float
    partial_success_rejected_attribute: str
    response_message_type: (
        type[ExportTraceServiceResponse] | type[ExportLogsServiceResponse] | type[ExportMetricsServiceResponse]
    )

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
    headers: Mapping[str, str]

    @property
    def path_config(self) -> ForwardingPathConfig:
        return FORWARDING_CONFIGS[self.path]


@dataclass(frozen=True)
class ForwardingErrorResponse:
    status_code: int
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
        max_queued_items: int = OTLP_FORWARDING_MAX_QUEUED_ITEMS,
    ) -> None:
        self.base_url = base_url
        self.session = session
        self.max_queued_body_bytes = max_queued_body_bytes
        self.max_queued_items = max_queued_items
        self.queue: deque[ForwardingRequest] = deque()
        self.worker: Thread | None = None
        self.closed = False
        self.condition = Condition()
        self.tokens: list[str] = []

    @property
    def queued_body_bytes(self) -> int:
        return sum(len(request.body) for request in self.queue)

    def enqueue(self, queued_request: ForwardingRequest) -> bool:
        body_size = len(queued_request.body)
        with self.condition:
            if (
                self.closed
                or len(self.queue) >= self.max_queued_items
                or self.queued_body_bytes + body_size > self.max_queued_body_bytes
            ):
                return False

            self.queue.append(queued_request)

            if self.worker is None or not self.worker.is_alive():
                self.worker = Thread(target=self._run, daemon=True)
                self.worker.start()

            self.condition.notify_all()
            return True

    def _send(self, request: ForwardingRequest) -> None:
        url = urljoin(self.base_url.rstrip('/') + '/', request.path.lstrip('/'))
        timeout = request.path_config.timeout()
        for token in self.tokens:
            headers = {
                **request.headers,
                'Authorization': token,
            }
            try:
                with suppress_instrumentation():
                    self.session.post(url, data=request.body, headers=headers, timeout=timeout)
            except Exception:
                continue

    def _run(self) -> None:
        while True:
            with self.condition:
                if not self.queue:
                    self.worker = None
                    self._close_session_if_idle_locked()
                    self.condition.notify_all()
                    return

                queued_request = self.queue[0]

            try:
                self._send(queued_request)
            except Exception:
                pass
            finally:
                with self.condition:
                    if self.queue:
                        self.queue.popleft()
                    self.condition.notify_all()

    def force_flush(self, timeout_millis: int) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        with self.condition:
            return self._wait_for_queue_empty_locked(deadline)

    def _has_live_worker_locked(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _wait_for_queue_empty_locked(self, deadline: float) -> bool:
        while self.queue:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            self.condition.wait(timeout=remaining)
        return True

    def _wait_for_worker_locked(self, deadline: float) -> bool:
        while self._has_live_worker_locked():
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            self.condition.wait(timeout=remaining)
        return True

    def _drop_queue_locked(self) -> None:
        self.queue.clear()
        self.condition.notify_all()

    def _at_fork_reinit(self, *, session: OTLPExporterHttpSession) -> None:
        self.condition = Condition()
        # Queued items were accepted by the parent process; the child must not send duplicates.
        self.queue.clear()
        self.worker = None
        self.session = session

    def _close_session_if_idle_locked(self) -> None:
        if self.closed and not self.queue:
            self.session.close()

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        deadline = monotonic() + timeout_millis / 1000
        with self.condition:
            self.closed = True
            self.condition.notify_all()
            if not drain_queued:
                self._drop_queue_locked()
            elif not self._wait_for_queue_empty_locked(deadline):
                self._drop_queue_locked()
                return False

            if not self._wait_for_worker_locked(deadline):
                self._drop_queue_locked()
                return False

            self._close_session_if_idle_locked()
            return True


class OTLPForwardingManager:
    def __init__(
        self,
        destinations: Sequence[tuple[str, str]],
        *,
        server_response_hook: ServerResponseCallback | None = None,
    ) -> None:
        self.pipelines: dict[str, OTLPForwardingPipeline] = {}
        self._server_response_hook = server_response_hook
        self.closed = False
        self._pid = os.getpid()
        for base_url, token in destinations:
            pipeline = self.pipelines.get(base_url)
            if pipeline is None:
                session = self._make_session()
                pipeline = self.pipelines[base_url] = OTLPForwardingPipeline(
                    base_url=base_url,
                    session=session,
                    max_queued_body_bytes=OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES,
                    max_queued_items=OTLP_FORWARDING_MAX_QUEUED_ITEMS,
                )

            pipeline.tokens.append(token)

        if self.pipelines and hasattr(os, 'register_at_fork'):
            weak_reinit = WeakMethod(self._at_fork_reinit)
            os.register_at_fork(after_in_child=lambda: _call_weak_method(weak_reinit))

    def has_destinations(self) -> bool:
        return bool(self.pipelines)

    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult:
        self._reset_after_fork_if_needed()
        if self.closed:
            return ForwardingAdmissionResult(
                response='partial_success',
                message='Forwarding manager is closed; request was locally dropped.',
            )

        dropped_count = 0
        for pipeline in self.pipelines.values():
            if not pipeline.enqueue(request):
                dropped_count += 1

        if dropped_count == 0:
            return ForwardingAdmissionResult(response='success', message=None)
        return ForwardingAdmissionResult(
            response='partial_success',
            message=f'Forwarding request was locally dropped for {dropped_count} backend URL(s).',
        )

    def force_flush(self, timeout_millis: int) -> bool:
        self._reset_after_fork_if_needed()
        deadline = monotonic() + timeout_millis / 1000

        complete = True
        for pipeline in self.pipelines.values():
            remaining_millis = max(0, int((deadline - monotonic()) * 1000))
            if not pipeline.force_flush(remaining_millis):
                complete = False
        return complete

    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool:
        self._reset_after_fork_if_needed()
        deadline = monotonic() + timeout_millis / 1000
        self.closed = True

        complete = True
        for pipeline in self.pipelines.values():
            remaining_millis = max(0, int((deadline - monotonic()) * 1000))
            if not pipeline.shutdown(remaining_millis, drain_queued=drain_queued):
                complete = False
        return complete

    def _reset_after_fork_if_needed(self) -> None:
        if self._pid != os.getpid():
            self._at_fork_reinit()

    def _at_fork_reinit(self) -> None:
        self._pid = os.getpid()
        for pipeline in self.pipelines.values():
            pipeline._at_fork_reinit(session=self._make_session())  # pyright: ignore[reportPrivateUsage]

    def _make_session(self) -> OTLPExporterHttpSession:
        session = OTLPExporterHttpSession()
        install_logfire_response_hook(session, self._server_response_hook)
        return session


def _call_weak_method(method_ref: WeakMethod[Callable[[], None]]) -> None:
    method = method_ref()
    if method is not None:
        method()


def _get_header(headers: Mapping[str, str], name: str) -> str | None:
    for header_name, value in headers.items():
        if header_name.lower() == name:
            return value
    return None


def _build_forwarding_request_headers(headers: Mapping[str, str], *, content_type: str) -> Mapping[str, str]:
    request_headers = {
        'Content-Type': content_type,
        'User-Agent': _forwarding_user_agent(_get_header(headers, 'user-agent')),
    }

    content_encoding = _get_header(headers, 'content-encoding')
    if content_encoding is not None:
        request_headers['Content-Encoding'] = content_encoding

    return MappingProxyType(request_headers)


def parse_forwarding_content_type(content_type: str) -> ForwardingContentType | None:
    normalized_content_type = content_type.lower()
    for forwarding_content_type in ForwardingContentType:
        if forwarding_content_type.value in normalized_content_type:
            return forwarding_content_type
    return None


def _invalid_path_response() -> ForwardingErrorResponse:
    paths = tuple(FORWARDING_CONFIGS)
    return ForwardingErrorResponse(
        status_code=400,
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


def build_forwarding_request(
    *,
    path: str,
    headers: Mapping[str, str],
    body: bytes,
    max_body_size: int = OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES,
) -> ForwardingRequest | ForwardingErrorResponse:
    normalized_path = _normalize_forwarding_path(path)
    if isinstance(normalized_path, ForwardingErrorResponse):
        return normalized_path

    if len(body) > max_body_size:
        return ForwardingErrorResponse(
            status_code=413,
            content=b'Payload too large',
        )

    content_type_header = _get_header(headers, 'content-type')
    if content_type_header is None:
        return ForwardingErrorResponse(
            status_code=415,
            content=b'Missing content type header',
        )

    content_type = parse_forwarding_content_type(content_type_header)
    if content_type is None:
        return ForwardingErrorResponse(
            status_code=415,
            content=b'Unsupported content type, must be application/json or application/x-protobuf',
        )

    return ForwardingRequest(
        path=normalized_path,
        body=body,
        content_type=content_type,
        headers=_build_forwarding_request_headers(headers, content_type=content_type_header),
    )


def build_success_response(request: ForwardingRequest) -> ForwardExportRequestResponse:
    message = request.path_config.response_message_type()
    return _build_response(message, request)


def build_partial_success_response(
    request: ForwardingRequest,
    *,
    message: str,
) -> ForwardExportRequestResponse:
    response_message = request.path_config.response_message_type()
    partial_success = response_message.partial_success
    setattr(partial_success, request.path_config.partial_success_rejected_attribute, 0)
    partial_success.error_message = message

    return _build_response(response_message, request)


def _build_response(message: Message, request: ForwardingRequest) -> ForwardExportRequestResponse:
    from logfire.experimental.forwarding import ForwardExportRequestResponse

    if request.content_type is ForwardingContentType.PROTOBUF:
        content = message.SerializeToString()
    else:
        content = MessageToJson(
            message,
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
