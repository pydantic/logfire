from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExportResult

from ..constants import ATTRIBUTES_LOG_LEVEL_NUM_KEY, ATTRIBUTES_SPAN_TYPE_KEY
from .wrapper import WrapperSpanExporter


@dataclass
class MinLogLevelFilterSpanExporter(WrapperSpanExporter):
    """A SpanExporter that filters out spans with log levels below a specified minimum level."""

    level_num: int

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        return super().export([span for span in spans if self._include_span(span)])

    def _include_span(self, span: ReadableSpan) -> bool:
        attributes = span.attributes or {}
        if attributes.get(ATTRIBUTES_SPAN_TYPE_KEY) != 'log':
            return True
        level = attributes.get(ATTRIBUTES_LOG_LEVEL_NUM_KEY, None)
        return not (isinstance(level, int) and level < self.level_num)
