from __future__ import annotations

from typing import Any

from opentelemetry._logs import LogRecord, SeverityNumber, get_logger
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor

import logfire


def test_otel_logs(config_kwargs: dict[str, Any]):
    exporter = InMemoryLogExporter()
    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(exporter)]
    logfire.configure(**config_kwargs)
    record = LogRecord(
        timestamp=1,
        observed_timestamp=2,
        trace_id=3,
        span_id=4,
        severity_text='INFO',
        severity_number=SeverityNumber.INFO,
        body='body',
        attributes={'key': 'value'},
    )
    get_logger(__name__).emit(record)
    [log_data] = exporter.get_finished_logs()
    assert log_data.log_record == record
