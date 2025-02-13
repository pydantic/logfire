from __future__ import annotations

from opentelemetry._logs import LogRecord, SeverityNumber, get_logger
from opentelemetry.sdk._logs.export import InMemoryLogExporter

import logfire


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
    logfire.suppress_scopes('scope1')
    logger1 = get_logger('scope1')
    logger2 = get_logger('scope2')
    logger3 = get_logger('scope3')
    logfire.suppress_scopes('scope2')
    logger1.emit(record)
    logger2.emit(record)
    assert not logs_exporter.get_finished_logs()
    logger3.emit(record)
    [log_data] = logs_exporter.get_finished_logs()
    assert log_data.log_record == record
    assert log_data.instrumentation_scope.name == 'scope3'
