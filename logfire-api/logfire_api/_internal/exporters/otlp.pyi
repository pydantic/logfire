import atexit
import logging
import requests
from ..constants import ATTRIBUTES_MESSAGE_KEY as ATTRIBUTES_MESSAGE_KEY, ATTRIBUTES_SPAN_TYPE_KEY as ATTRIBUTES_SPAN_TYPE_KEY, HTTP_CONNECT_TIMEOUT as HTTP_CONNECT_TIMEOUT, OTLP_MAX_INT_SIZE as OTLP_MAX_INT_SIZE, log_level_attributes as log_level_attributes
from ..http_transport import install_connection_policy as install_connection_policy
from ..stack_info import STACK_INFO_KEYS as STACK_INFO_KEYS
from ..utils import logger as logger, platform_is_emscripten as platform_is_emscripten, truncate_string as truncate_string
from .wrapper import WrapperLogExporter as WrapperLogExporter, WrapperSpanExporter as WrapperSpanExporter
from _typeshed import Incomplete
from collections import deque
from collections.abc import Mapping, Sequence
from functools import cached_property
from logfire._internal.utils import handle_internal_errors as handle_internal_errors
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import ReadableLogRecord as ReadableLogRecord
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from pathlib import Path
from requests import Session
from threading import Thread
from typing import Any, Protocol
from typing_extensions import Buffer

class _OTLPExportResult(Protocol):
    success: bool
    status_code: int | None
    error: Exception | None

class _OTLPClient(Protocol):
    def export(self, data: bytes) -> _OTLPExportResult: ...
    def shutdown(self) -> None: ...

class _QuietConnectionErrorLogger(logging.LoggerAdapter):
    def error(self, msg: object, *args: Any, **kwargs: Any) -> None: ...

class _BodySizeCheckingOTLPClient:
    client: Incomplete
    exporter: Incomplete
    def __init__(self, client: _OTLPClient, exporter: BodySizeCheckingOTLPSpanExporter) -> None: ...
    def export(self, data: bytes) -> _OTLPExportResult: ...
    def shutdown(self) -> None: ...

class ZstdCompressFn(Protocol):
    """Signature of `compression.zstd.compress` and `backports.zstd.compress`."""
    def __call__(self, data: Buffer, level: int | None = None, options: Mapping[int, int] | None = None, zstd_dict: Any = None) -> bytes: ...

zstd_compress: ZstdCompressFn | None

@atexit.register
def cleanup_disk_retryers() -> None: ...

class BodySizeCheckingOTLPSpanExporter(OTLPSpanExporter):
    max_body_size: Incomplete
    current_num_spans: int
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def export(self, spans: Sequence[ReadableSpan]): ...

class OTLPExporterHttpSession(Session):
    """A requests.Session subclass that defers failed requests to a DiskRetryer."""
    def __init__(self, *, _use_zstd: bool = False) -> None: ...
    def request(self, method: str, url: str, **kwargs: Any): ...
    def post(self, url: str, data: bytes, **kwargs: Any): ...
    @cached_property
    def retryer(self) -> DiskRetryer: ...
    def close(self) -> None: ...

def raise_for_retryable_status(response: requests.Response): ...

class DiskRetryer:
    """Retries requests failed by OTLPExporterHttpSession, saving the request body to disk to save memory."""
    MAX_DELAY: int
    MAX_TASK_SIZE: Incomplete
    LOG_INTERVAL: int
    lock: Incomplete
    thread: Thread | None
    tasks: deque[tuple[Path, dict[str, Any]]]
    total_size: int
    closed: bool
    session: Incomplete
    dir: Incomplete
    last_log_time: Incomplete
    def __init__(self, headers: Mapping[str, str | bytes]) -> None: ...
    def close(self) -> None: ...
    def add_task(self, data: bytes, kwargs: dict[str, Any]): ...

class RetryFewerSpansSpanExporter(WrapperSpanExporter):
    """A SpanExporter that retries exporting spans in smaller batches if BodyTooLargeError is raised.

    This wraps another exporter, typically an OTLPSpanExporter using an OTLPExporterHttpSession.
    """
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...

class BodyTooLargeError(Exception):
    size: Incomplete
    max_size: Incomplete
    def __init__(self, size: int, max_size: int | None) -> None: ...

class SuppressedConnectionError(Exception): ...

class QuietSpanExporter(WrapperSpanExporter):
    """A SpanExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...

class QuietLogExporter(WrapperLogExporter):
    """A LogExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""
    def export(self, batch: Sequence[ReadableLogRecord]): ...
