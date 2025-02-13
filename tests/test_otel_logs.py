from __future__ import annotations

from opentelemetry._logs import LogRecord, SeverityNumber, get_logger
from opentelemetry.sdk._logs.export import InMemoryLogExporter


def test_otel_logs(logs_exporter: InMemoryLogExporter) -> None:
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
    [log_data] = logs_exporter.get_finished_logs()
    assert log_data.log_record == record
