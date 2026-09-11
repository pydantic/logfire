from __future__ import annotations

from collections.abc import Sequence
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

from opentelemetry import trace as trace_api
from opentelemetry._logs import Logger, LogRecord
from opentelemetry.context import Context
from opentelemetry.sdk.trace import Tracer as SDKTracer
from opentelemetry.trace import Link, NonRecordingSpan, Span, SpanKind, Tracer
from opentelemetry.util import types as otel_types

from logfire._internal.constants import (
    ATTRIBUTES_LOG_LEVEL_NUM_KEY,
    ATTRIBUTES_MESSAGE_KEY,
    ATTRIBUTES_MESSAGE_TEMPLATE_KEY,
    ATTRIBUTES_SAMPLE_RATE_KEY,
    ATTRIBUTES_TAGS_KEY,
    DISABLE_CONSOLE_KEY,
)
from logfire._internal.formatter import logfire_format
from logfire.version import VERSION

if TYPE_CHECKING:
    from logfire import Logfire

_install_lock = Lock()
_installed = False


def instrument_monty(logfire_instance: Logfire) -> None:
    """Install process-wide Monty instrumentation using Logfire's OpenTelemetry components."""
    global _installed

    with _install_lock:
        if _installed:
            return
        try:
            from pydantic_monty import instrument_telemetry
        except ImportError:
            raise ImportError(
                '`logfire.instrument_monty()` requires a version of the `pydantic-monty` package '
                'which supports OpenTelemetry instrumentation.'
            ) from None

        scoped = logfire_instance.with_settings(custom_scope_suffix='monty')
        config = scoped._config  # pyright: ignore[reportPrivateUsage]
        tracer = LogfireMontyTracer(scoped)
        meter = None if config.metrics is False else scoped._meter  # pyright: ignore[reportPrivateUsage]
        logger = LogfireMontyLogger(
            config.get_logger_provider().get_logger(scoped._otel_scope, VERSION),  # pyright: ignore[reportPrivateUsage]
            scoped,
        )
        instrument_telemetry(tracer=tracer, meter=meter, logger=logger)
        _installed = True


class LogfireMontyTracer(Tracer):
    """Standard OTel tracer adding settings from a specific Logfire instance."""

    def __init__(self, logfire_instance: Logfire) -> None:
        self.logfire = logfire_instance

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: Sequence[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> Span:
        span_attributes: dict[str, Any] = dict(attributes or {})
        level = span_attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY)
        if isinstance(level, int) and level < self.logfire.config.min_level:
            return NonRecordingSpan(trace_api.get_current_span(context).get_span_context())

        template = span_attributes.setdefault(ATTRIBUTES_MESSAGE_TEMPLATE_KEY, name)
        if ATTRIBUTES_MESSAGE_KEY not in span_attributes:
            span_attributes[ATTRIBUTES_MESSAGE_KEY] = logfire_format(
                str(template), span_attributes, self.logfire.config.scrubber
            )
        _add_tags(span_attributes, self.logfire)
        if self.logfire._sample_rate not in (None, 1):  # pyright: ignore[reportPrivateUsage]
            span_attributes[ATTRIBUTES_SAMPLE_RATE_KEY] = self.logfire._sample_rate  # pyright: ignore[reportPrivateUsage]

        return self.logfire._spans_tracer.start_span(  # pyright: ignore[reportPrivateUsage]
            name,
            context=context,
            kind=kind,
            attributes=span_attributes,
            links=links,
            start_time=start_time,
            record_exception=record_exception,
            set_status_on_exception=set_status_on_exception,
        )

    start_as_current_span = SDKTracer.start_as_current_span


class LogfireMontyLogger(Logger):
    """Standard OTel logger adding settings from a specific Logfire instance."""

    def __init__(self, logger: Logger, logfire_instance: Logfire) -> None:
        self.logger = logger
        self.logfire = logfire_instance

    def emit(self, record: LogRecord | None = None, **kwargs: Any) -> None:
        if record is None:
            attributes = dict(kwargs.get('attributes') or {})
            body = kwargs.get('body')
            self._enrich(attributes, body, kwargs.get('severity_number'))
            kwargs['attributes'] = attributes
            self.logger.emit(**kwargs)
        else:
            attributes = dict(record.attributes or {})
            self._enrich(attributes, record.body, record.severity_number)
            record.attributes = attributes
            self.logger.emit(record)

    def _enrich(self, attributes: dict[str, Any], body: Any, severity_number: Any) -> None:
        if isinstance(body, str):
            attributes.setdefault(ATTRIBUTES_MESSAGE_TEMPLATE_KEY, body)
            attributes.setdefault(ATTRIBUTES_MESSAGE_KEY, body)
        if severity_number is not None:
            attributes.setdefault(ATTRIBUTES_LOG_LEVEL_NUM_KEY, severity_number.value)
        _add_tags(attributes, self.logfire)
        if not self.logfire._console_log:  # pyright: ignore[reportPrivateUsage]
            attributes[DISABLE_CONSOLE_KEY] = True


def _add_tags(attributes: dict[str, Any], logfire_instance: Logfire) -> None:
    tags = logfire_instance._tags  # pyright: ignore[reportPrivateUsage]
    if not tags:
        return
    existing = attributes.get(ATTRIBUTES_TAGS_KEY)
    existing_tags = (
        tuple(value for value in cast(Sequence[Any], existing) if isinstance(value, str))
        if isinstance(existing, Sequence) and not isinstance(existing, str)
        else ()
    )
    attributes[ATTRIBUTES_TAGS_KEY] = tuple(dict.fromkeys((*existing_tags, *tags)))
