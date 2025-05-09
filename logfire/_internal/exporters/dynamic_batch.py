from __future__ import annotations

import os
from dataclasses import dataclass

from opentelemetry.sdk.environment_variables import OTEL_BSP_SCHEDULE_DELAY
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from logfire._internal.exporters.wrapper import WrapperSpanProcessor


@dataclass(init=False)
class DynamicBatchSpanProcessor(WrapperSpanProcessor):
    def __init__(self, exporter: SpanExporter) -> None:
        self.final_delay = float(os.environ.get(OTEL_BSP_SCHEDULE_DELAY) or 500)
        initial_delay = min(self.final_delay, 100)
        super().__init__(BatchSpanProcessor(exporter, schedule_delay_millis=initial_delay))
        self.num_processed = 0

    def on_end(self, span: ReadableSpan) -> None:
        self.num_processed += 1
        if self.num_processed == 10:
            assert isinstance(self.processor, BatchSpanProcessor)
            self.processor.schedule_delay_millis = self.final_delay
        super().on_end(span)
