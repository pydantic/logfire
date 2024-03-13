from __future__ import annotations

import contextlib
from typing import Any, Iterable, Sequence, cast

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult
from requests import Session
from requests.models import PreparedRequest, Response

import logfire
from logfire._stack_info import STACK_INFO_KEYS
from logfire._utils import truncate_string
from logfire.exporters._wrapper import WrapperSpanExporter


class OTLPExporterHttpSession(Session):
    """A requests.Session subclass that raises a BodyTooLargeError if the request body is too large."""

    def __init__(self, *args: Any, max_body_size: int, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.max_body_size = max_body_size

    def send(self, request: PreparedRequest, **kwargs: Any) -> Response:
        if request.body is not None:  # pragma: no branch
            if isinstance(request.body, (str, bytes)):  # type: ignore
                self._check_body_size(len(request.body))
            else:
                # assume a generator
                body = cast('Iterable[bytes]', request.body)

                def gen() -> Iterable[bytes]:
                    total = 0
                    for chunk in body:
                        total += len(chunk)
                        self._check_body_size(total)
                        yield chunk

                request.body = gen()  # type: ignore
        return super().send(request, **kwargs)

    def _check_body_size(self, size: int) -> None:
        if size > self.max_body_size:
            raise BodyTooLargeError(size, self.max_body_size)


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
                if key in original_attributes:
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
