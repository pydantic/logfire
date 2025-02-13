from __future__ import annotations

from typing import Any

from opentelemetry._logs import LogRecord, SeverityNumber, get_logger, get_logger_provider
from opentelemetry.sdk._logs.export import InMemoryLogExporter
from opentelemetry.sdk.resources import Resource

import logfire


def test_otel_logs_supress_scopes(logs_exporter: InMemoryLogExporter, config_kwargs: dict[str, Any]) -> None:
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
    logfire.configure(**config_kwargs)
    logfire.suppress_scopes('scope2')
    logger1.emit(record)
    logger2.emit(record)
    assert not logs_exporter.get_finished_logs()
    logger3.emit(record)
    [log_data] = logs_exporter.get_finished_logs()
    assert log_data.log_record == record
    assert log_data.instrumentation_scope.name == 'scope3'


def test_get_logger_provider() -> None:
    provider = get_logger_provider()
    assert provider is logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_logger_provider()
    assert isinstance(provider.resource, Resource)  # type: ignore
