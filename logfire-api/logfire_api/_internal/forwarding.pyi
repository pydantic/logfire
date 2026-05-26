from _typeshed import Incomplete
from collections import deque
from collections.abc import Callable as Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from logfire._internal.exporters.otlp import OTLPExporterHttpSession as OTLPExporterHttpSession
from logfire._internal.server_response import install_logfire_response_hook as install_logfire_response_hook
from logfire._internal.utils import suppress_instrumentation as suppress_instrumentation
from logfire.experimental.forwarding import ForwardExportRequestResponse as ForwardExportRequestResponse
from logfire.types import ServerResponseCallback as ServerResponseCallback
from logfire.version import VERSION as VERSION
from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceResponse
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceResponse
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceResponse
from threading import Thread
from typing import Literal

OTLP_FORWARDING_MAX_QUEUED_BODY_BYTES: Incomplete
OTLP_FORWARDING_MAX_QUEUED_ITEMS: int
OTLP_FORWARDING_MAX_REQUEST_BODY_BYTES: Incomplete
ForwardingPath: Incomplete

@dataclass(frozen=True)
class ForwardingPathConfig:
    timeout_env: str
    default_timeout: float
    partial_success_rejected_attribute: str
    response_message_type: type[ExportTraceServiceResponse] | type[ExportLogsServiceResponse] | type[ExportMetricsServiceResponse]
    def timeout(self) -> float: ...

FORWARDING_CONFIGS: dict[ForwardingPath, ForwardingPathConfig]

class ForwardingContentType(Enum):
    PROTOBUF: str
    JSON: str

@dataclass(frozen=True)
class ForwardingRequest:
    path: ForwardingPath
    body: bytes
    content_type: ForwardingContentType
    headers: Mapping[str, str]
    @property
    def path_config(self) -> ForwardingPathConfig: ...

@dataclass(frozen=True)
class ForwardingErrorResponse:
    status_code: int
    content: bytes

@dataclass(frozen=True)
class ForwardingAdmissionResult:
    response: Literal['success', 'partial_success']
    message: str | None

class OTLPForwardingPipeline:
    base_url: Incomplete
    session: Incomplete
    max_queued_body_bytes: Incomplete
    max_queued_items: Incomplete
    queue: deque[ForwardingRequest]
    worker: Thread | None
    closed: bool
    condition: Incomplete
    tokens: list[str]
    def __init__(self, *, base_url: str, session: OTLPExporterHttpSession, max_queued_body_bytes: int, max_queued_items: int = ...) -> None: ...
    @property
    def queued_body_bytes(self) -> int: ...
    def enqueue(self, queued_request: ForwardingRequest) -> bool: ...
    def force_flush(self, timeout_millis: int) -> bool: ...
    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool: ...

class OTLPForwardingManager:
    pipelines: dict[str, OTLPForwardingPipeline]
    closed: bool
    def __init__(self, destinations: Sequence[tuple[str, str]], *, server_response_hook: ServerResponseCallback | None = None) -> None: ...
    def has_destinations(self) -> bool: ...
    def submit(self, request: ForwardingRequest) -> ForwardingAdmissionResult: ...
    def force_flush(self, timeout_millis: int) -> bool: ...
    def shutdown(self, timeout_millis: int, *, drain_queued: bool = True) -> bool: ...

def parse_forwarding_content_type(content_type: str) -> ForwardingContentType | None: ...
def build_forwarding_request(*, path: str, headers: Mapping[str, str], body: bytes, max_body_size: int = ...) -> ForwardingRequest | ForwardingErrorResponse: ...
def build_success_response(request: ForwardingRequest) -> ForwardExportRequestResponse: ...
def build_partial_success_response(request: ForwardingRequest, *, message: str) -> ForwardExportRequestResponse: ...
