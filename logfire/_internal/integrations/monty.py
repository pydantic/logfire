from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from opentelemetry import trace as trace_api
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
)
from logfire._internal.formatter import logfire_format

if TYPE_CHECKING:
    from logfire import Logfire


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
