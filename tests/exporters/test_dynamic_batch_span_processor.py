from __future__ import annotations

from typing import Any

from opentelemetry.sdk.trace.export import BatchSpanProcessor

import logfire
from logfire._internal.exporters.dynamic_batch import DynamicBatchSpanProcessor
from logfire.testing import TestExporter


def test_dynamic_batch_span_processor(exporter: TestExporter, config_kwargs: dict[str, Any]):
    processor = DynamicBatchSpanProcessor(exporter)
    config_kwargs['additional_span_processors'] = [processor]
    logfire.configure(**config_kwargs)
    for _ in range(9):
        logfire.info('test')
    assert processor.num_processed == 9
    assert isinstance(processor.processor, BatchSpanProcessor)
    assert processor.processor.schedule_delay_millis == 100
    logfire.info('test')
    assert processor.num_processed == 10
    assert processor.processor.schedule_delay_millis == 500
    logfire.force_flush()
    assert len(exporter.exported_spans) == 10
