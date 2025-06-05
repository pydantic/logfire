from __future__ import annotations

import os
from typing import TYPE_CHECKING

from opentelemetry.sdk.environment_variables import OTEL_BSP_SCHEDULE_DELAY
from opentelemetry.sdk.trace import ReadableSpan, Span
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from logfire._internal.exporters.wrapper import WrapperSpanProcessor

if TYPE_CHECKING:
    from opentelemetry.sdk._shared_internal import BatchProcessor


class DynamicBatchSpanProcessor(WrapperSpanProcessor):
    """A wrapper around a BatchSpanProcessor that dynamically adjusts the schedule delay.

    The initial schedule delay is set to 100ms, and after processing 10 spans, it is set to the value of
    the `OTEL_BSP_SCHEDULE_DELAY` environment variable (default: 500ms).
    This makes the initial experience of the SDK more responsive.
    """

    processor: BatchSpanProcessor  # type: ignore

    def __init__(self, exporter: SpanExporter) -> None:
        self.final_delay = float(os.environ.get(OTEL_BSP_SCHEDULE_DELAY) or 500)
        # Start with the configured value immediately if it's less than 100ms.
        initial_delay = min(self.final_delay, 100)
        super().__init__(BatchSpanProcessor(exporter, schedule_delay_millis=initial_delay))
        self.num_processed = 0

    def on_end(self, span: ReadableSpan) -> None:
        self.num_processed += 1
        if self.num_processed == 10:
            if hasattr(self.batch_processor, '_schedule_delay_millis'):
                self.batch_processor._schedule_delay = self.final_delay / 1e3  # type: ignore
            else:  # pragma: no cover
                self.processor.schedule_delay_millis = self.final_delay  # type: ignore
        super().on_end(span)

    @property
    def batch_processor(self) -> BatchSpanProcessor | BatchProcessor[Span]:
        return getattr(self.processor, '_batch_processor', self.processor)

    @property
    def span_exporter(self) -> SpanExporter:
        if isinstance(self.batch_processor, BatchSpanProcessor):  # pragma: no cover
            return self.batch_processor.span_exporter  # type: ignore
        else:
            return self.batch_processor._exporter  # type: ignore
