import requests
from ..stack_info import STACK_INFO_KEYS as STACK_INFO_KEYS
from ..utils import logger as logger, platform_is_emscripten as platform_is_emscripten, truncate_string as truncate_string
from .wrapper import WrapperLogExporter as WrapperLogExporter, WrapperSpanExporter as WrapperSpanExporter
from _typeshed import Incomplete
from functools import cached_property
from opentelemetry.sdk._logs import LogData as LogData
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from requests import Session
from typing import Any, Mapping, Sequence

class OTLPExporterHttpSession(Session):
    """A requests.Session subclass that raises a BodyTooLargeError if the request body is too large.

    Also defers failed requests to a DiskRetryer.
    """
    max_body_size: Incomplete
    def __init__(self, *args: Any, max_body_size: int, **kwargs: Any) -> None: ...
    def post(self, url: str, data: bytes, **kwargs: Any): ...
    @cached_property
    def retryer(self) -> DiskRetryer: ...

def raise_for_retryable_status(response: requests.Response): ...

class DiskRetryer:
    """Retries requests failed by OTLPExporterHttpSession, saving the request body to disk to save memory."""
    MAX_DELAY: int
    MAX_TASKS: int
    LOG_INTERVAL: int
    lock: Incomplete
    thread: Incomplete
    tasks: Incomplete
    session: Incomplete
    dir: Incomplete
    last_log_time: Incomplete
    def __init__(self, headers: Mapping[str, str | bytes]) -> None: ...
    def add_task(self, data: bytes, kwargs: dict[str, Any]): ...

class RetryFewerSpansSpanExporter(WrapperSpanExporter):
    """A SpanExporter that retries exporting spans in smaller batches if BodyTooLargeError is raised.

    This wraps another exporter, typically an OTLPSpanExporter using an OTLPExporterHttpSession.
    """
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...

class BodyTooLargeError(Exception):
    size: Incomplete
    max_size: Incomplete
    def __init__(self, size: int, max_size: int) -> None: ...

class QuietSpanExporter(WrapperSpanExporter):
    """A SpanExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult: ...

class QuietLogExporter(WrapperLogExporter):
    """A LogExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""
    def export(self, batch: Sequence[LogData]): ...
