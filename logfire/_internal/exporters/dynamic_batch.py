from __future__ import annotations

import os

from opentelemetry.sdk.environment_variables import OTEL_BSP_SCHEDULE_DELAY
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from logfire._internal.exporters.wrapper import WrapperSpanProcessor

try:
    from opentelemetry.sdk._shared_internal import BatchProcessor
except ImportError:
    BatchProcessor = None


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
            self.schedule_delay_millis = self.final_delay
        super().on_end(span)

    if BatchProcessor:

        @property
        def batch_processor(self):  # type: ignore
            return self.processor._batch_processor  # type: ignore

        @property
        def span_exporter(self) -> SpanExporter:  # type: ignore
            return self.batch_processor._exporter  # type: ignore

        @property
        def schedule_delay_millis(self) -> float:  # type: ignore
            return self.batch_processor._schedule_delay * 1000  # type: ignore

        @schedule_delay_millis.setter
        def schedule_delay_millis(self, value: float):  # type: ignore
            self.batch_processor._schedule_delay = value / 1000  # type: ignore
    else:

        @property
        def batch_processor(self):
            return self.processor

        @property
        def span_exporter(self) -> SpanExporter:
            return self.processor.span_exporter  # type: ignore

        @property
        def schedule_delay_millis(self) -> float:
            return self.processor.schedule_delay_millis  # type: ignore

        @schedule_delay_millis.setter
        def schedule_delay_millis(self, value: float):
            self.processor.schedule_delay_millis = value  # type: ignore
