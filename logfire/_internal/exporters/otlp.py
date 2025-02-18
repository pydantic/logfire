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
from opentelemetry.sdk._logs import LogData
from opentelemetry.sdk._logs._internal.export import LogExportResult
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from requests import Session

import logfire

from ..stack_info import STACK_INFO_KEYS
from ..utils import logger, platform_is_emscripten, truncate_string
from .wrapper import WrapperLogExporter, WrapperSpanExporter


class OTLPExporterHttpSession(Session):
    """A requests.Session subclass that raises a BodyTooLargeError if the request body is too large.

    Also defers failed requests to a DiskRetryer.
    """

    def __init__(self, *args: Any, max_body_size: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_body_size = max_body_size

    def post(self, url: str, data: bytes, **kwargs: Any):  # type: ignore
        self._check_body_size(len(data))
        try:
            response = super().post(url, data=data, **kwargs)
            raise_for_retryable_status(response)
        except requests.exceptions.RequestException:
            # Retry in another thread so that the BatchSpanProcessor can continue creating batches
            # and not fill up its queue in memory.
            # TODO consider first immediately retrying a little bit.
            #   In particular this would help with very transient errors (as opposed to logfire being down)
            #   that happen when the process is shutting down.
            #   DiskRetryer uses a daemon thread so it will shut down when the main thread does,
            #   meaning that kind of failed export would be lost.
            #   BatchSpanProcessor on the other hand stays alive for a bit with a deadline.
            #   If we do this we must measure and limit the amount of time spent requesting and retrying.
            # TODO consider increasing the BatchSpanProcessor export delay here
            #   to reduce the number of small inefficient requests.
            # No threads in Emscripten, we can't add a task to try later, just raise
            if not platform_is_emscripten():  # pragma: no branch
                self.retryer.add_task(data, {'url': url, **kwargs})
            raise

        return response

    @cached_property
    def retryer(self) -> DiskRetryer:
        # Only create this when needed to save resources,
        # and because the full set of headers are only set some time after this session is created.
        return DiskRetryer(self.headers)

    def _check_body_size(self, size: int) -> None:
        if size > self.max_body_size:
            raise BodyTooLargeError(size, self.max_body_size)


def raise_for_retryable_status(response: requests.Response):
    # These are status codes that OTEL should retry.
    # We want to do the retrying ourselves, so we raise an exception instead of returning.
    if response.status_code in (408, 429) or response.status_code >= 500:
        response.raise_for_status()


class DiskRetryer:
    """Retries requests failed by OTLPExporterHttpSession, saving the request body to disk to save memory."""

    # The maximum delay between retries, in seconds
    MAX_DELAY = 128

    # The maximum number of exports to retry. Each export is a file on disk.
    # This amount should allow comfortably handling a few minutes of backend downtime
    # while the BatchSpanProcessor produces a batch every half a second.
    # If the number of failed exports exceeds this limit, new exports will be dropped.
    # TODO ideally we should be measuring the total size of exports instead of the number of files,
    #   and compare it to a limit based on disk space.
    MAX_TASKS = 1000

    # Log about problems at most once a minute.
    LOG_INTERVAL = 60

    def __init__(self, headers: Mapping[str, str | bytes]):
        # Reading/writing `thread` and `tasks` should generally be protected by `lock`.
        self.lock = Lock()
        self.thread: Thread | None = None
        self.tasks: deque[tuple[Path, dict[str, Any]]] = deque()

        # Make a new session rather than using the OTLPExporterHttpSession directly
        # because thread safety of Session is questionable.
        # This assumes that the only important state is the headers.
        self.session = Session()
        self.session.headers.update(headers)

        # The directory where the export files are stored.
        self.dir = Path(mkdtemp(prefix='logfire-retryer-'))

        self.last_log_time = -float('inf')

    def add_task(self, data: bytes, kwargs: dict[str, Any]):
        try:
            if len(self.tasks) >= self.MAX_TASKS:  # pragma: no cover
                if self._should_log():
                    logger.error('Already retrying %s failed exports, dropping an export', len(self.tasks))
                return

            # TODO consider keeping the first few tasks in memory to avoid disk I/O and possible errors.
            path = self.dir / uuid.uuid4().hex
            path.write_bytes(data)

            with self.lock:
                self.tasks.append((path, kwargs))
                if not (self.thread and self.thread.is_alive()):
                    # daemon=True to avoid hanging the program on exit, since this might never finish.
                    # See caveat about this where add_task is called.
                    self.thread = Thread(target=self._run, daemon=True)
                    self.thread.start()
                num_tasks = len(self.tasks)

            if self._should_log():
                logger.warning('Currently retrying %s failed export(s)', num_tasks)
        except Exception as e:  # pragma: no cover
            if self._should_log():
                logger.error('Export and retry failed: %s', e)

    def _should_log(self) -> bool:
        result = time.monotonic() - self.last_log_time >= self.LOG_INTERVAL
        if result:
            self.last_log_time = time.monotonic()
        return result

    def _run(self):
        delay = 1
        while True:
            with self.lock:
                if not self.tasks:
                    # All done, end the thread.
                    self.thread = None
                    break

                # Keep this outside the try block below so that if somehow this part fails
                # the queue still gets smaller, and we don't get stuck in a hot infinite loop.
                task = self.tasks.popleft()

            try:
                path, kwargs = task
                data = path.read_bytes()
                while True:
                    # Exponential backoff with jitter.
                    # The jitter is proportional to the delay, in particular so that if we go down for a while
                    # and then come back up then retry requests will be spread out over a time of MAX_DELAY.
                    time.sleep(delay * (1 + random.random()))
                    try:
                        with logfire.suppress_instrumentation():
                            response = self.session.post(**kwargs, data=data)
                        raise_for_retryable_status(response)
                    except requests.exceptions.RequestException:
                        # Failed, increase delay exponentially up to MAX_DELAY.
                        delay = min(delay * 2, self.MAX_DELAY)
                    else:
                        # Success, reset the delay (so that remaining tasks can be done quickly),
                        # remove the file, and move on to the next task.
                        delay = 1
                        path.unlink()
                        break

            except Exception:  # pragma: no cover
                if self._should_log():
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


class QuietSpanExporter(WrapperSpanExporter):
    """A SpanExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            return super().export(spans)
        except requests.exceptions.RequestException:
            # Rely on OTLPExporterHttpSession/DiskRetryer to log this kind of error periodically.
            return SpanExportResult.FAILURE


class QuietLogExporter(WrapperLogExporter):
    """A LogExporter that catches request exceptions to prevent OTEL from logging a huge traceback."""

    def export(self, batch: Sequence[LogData]):
        try:
            return super().export(batch)
        except requests.exceptions.RequestException:
            # Rely on OTLPExporterHttpSession/DiskRetryer to log this kind of error periodically.
            return LogExportResult.FAILURE
