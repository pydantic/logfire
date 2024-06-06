from __future__ import annotations

import contextlib
import random
import time
import uuid
from collections import deque
from functools import cached_property
from pathlib import Path
from tempfile import mkdtemp
from threading import Lock, Thread
from typing import Any, Mapping, Sequence

import requests.exceptions
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from requests import Session

import logfire

from ..stack_info import STACK_INFO_KEYS
from ..utils import logger, truncate_string
from .wrapper import WrapperSpanExporter


class OTLPExporterHttpSession(Session):
    """A requests.Session subclass that raises a BodyTooLargeError if the request body is too large."""

    def __init__(self, *args: Any, max_body_size: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_body_size = max_body_size

    def post(self, url: str, data: bytes, **kwargs: Any):  # type: ignore
        self._check_body_size(len(data))
        try:
            response = super().post(url, data=data, **kwargs)
            raise_for_retryable_status(response)
        except requests.exceptions.RequestException:
            try:
                self.retryer.add_task(data, {'url': url, **kwargs})
            except Exception:  # pragma: no cover
                logger.exception('Failed to add task to export retryer')
            raise

        return response

    @cached_property
    def retryer(self) -> DiskRetryer:
        return DiskRetryer(self.headers)

    def _check_body_size(self, size: int) -> None:
        if size > self.max_body_size:
            raise BodyTooLargeError(size, self.max_body_size)


def raise_for_retryable_status(response: requests.Response):
    if response.status_code in (408, 429) or response.status_code >= 500:
        response.raise_for_status()


DiskRetryerTask = tuple[Path, dict[str, Any]]


class DiskRetryer:
    MAX_DELAY = 128
    MAX_TASKS = 100
    WARN_INTERVAL = 60

    def __init__(self, headers: Mapping[str, str | bytes]):
        self.tasks: deque[DiskRetryerTask] = deque()
        self.session = Session()
        self.session.headers.update(headers)
        self.dir = Path(mkdtemp(prefix='logfire-retryer-'))
        self.lock = Lock()
        self.thread = None
        self.last_warning_time = time.monotonic()

    def add_task(self, data: bytes, kwargs: dict[str, Any]):
        if len(self.tasks) >= self.MAX_TASKS:  # pragma: no cover
            if self._should_warn():
                logger.error('Already retrying %s export tasks, dropping an export', len(self.tasks))
            return
        path = self.dir / uuid.uuid4().hex
        path.write_bytes(data)
        with self.lock:
            self.tasks.append((path, kwargs))
            if not self.thread:
                self.thread = Thread(target=self._run, daemon=True)
                self.thread.start()
            num_tasks = len(self.tasks)

        if self._should_warn():
            logger.warning('Currently retrying %s export task(s)', num_tasks)

    def _should_warn(self):
        result = time.monotonic() - self.last_warning_time >= self.WARN_INTERVAL
        if result:
            self.last_warning_time = time.monotonic()
        return result

    def _run(self):
        delay = 1
        while True:
            with self.lock:
                if not self.tasks:
                    self.thread = None
                    break
                path, kwargs = self.tasks.popleft()
            try:
                data = path.read_bytes()
                while True:
                    time.sleep(delay * (1 + random.random()))
                    try:
                        response = self.session.post(**kwargs, data=data)
                        raise_for_retryable_status(response)
                    except requests.exceptions.RequestException:
                        delay = min(delay * 2, self.MAX_DELAY)
                    else:
                        delay = 1
                        path.unlink()
                        break
            except Exception:  # pragma: no cover
                logger.exception('Error retrying export')


class RetryFewerSpansSpanExporter(WrapperSpanExporter):
    """A SpanExporter that retries exporting spans in smaller batches if BodyTooLargeError is raised.

    This wraps another exporter, typically an OTLPSpanExporter using an OTLPExporterHttpSession.
    """

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return super().export(spans)
        except BodyTooLargeError as e:
            if len(spans) == 1:
                self._log_too_large_span(e, spans[0])
                return SpanExportResult.FAILURE

            half = len(spans) // 2
            res1 = self.export(spans[:half])
            res2 = self.export(spans[half:])
            if res1 is not SpanExportResult.SUCCESS or res2 is not SpanExportResult.SUCCESS:
                return SpanExportResult.FAILURE
            return SpanExportResult.SUCCESS

    def _log_too_large_span(self, e: BodyTooLargeError, span: ReadableSpan) -> None:
        original_attributes = span.attributes or {}
        new_attributes: dict[str, Any] = {'size': e.size, 'max_size': e.max_size}

        with contextlib.suppress(Exception):  # just being extra cautious
            for key in STACK_INFO_KEYS:
                if key in original_attributes:  # pragma: no branch
                    value = original_attributes[key]
                    if isinstance(value, str):
                        value = truncate_string(value, max_length=300)
                    new_attributes[key] = value

        with contextlib.suppress(Exception):  # separate block to isolate effects of exceptions
            new_attributes.update(
                span_name=truncate_string(span.name, max_length=1000),
                num_attributes=len(original_attributes),
                num_events=len(span.events),
                num_links=len(span.links),
                num_event_attributes=sum(len(event.attributes or {}) for event in span.events),
                num_link_attributes=sum(len(link.attributes or {}) for link in span.links),
            )

        logfire.error('Failed to export a span of size {size:,} bytes: {span_name}', **new_attributes)


class BodyTooLargeError(Exception):
    def __init__(self, size: int, max_size: int) -> None:
        super().__init__(f'Request body is too large ({size} bytes), must be less than {max_size} bytes.')
        self.size = size
        self.max_size = max_size
