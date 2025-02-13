from __future__ import annotations

import json
from typing import Any

from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry._events import Event, get_event_logger, get_event_logger_provider
from opentelemetry._logs import LogRecord, SeverityNumber, get_logger, get_logger_provider
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
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
    logfire.suppress_scopes('scope2')
    logger1.emit(record)
    logger2.emit(record)
    assert not logs_exporter.get_finished_logs()

    logs_exporter = InMemoryLogExporter()
    config_kwargs['advanced'].log_record_processors = [SimpleLogRecordProcessor(logs_exporter)]
    logfire.configure(**config_kwargs)

    logger1 = get_logger('scope1')
    logger2 = get_logger('scope2')
    logger3 = get_logger('scope3')
    logger1.emit(record)
    logger2.emit(record)
    assert not logs_exporter.get_finished_logs()

    logger3.emit(record)
    [log_data] = logs_exporter.get_finished_logs()
    assert log_data.log_record == record
    assert log_data.instrumentation_scope.name == 'scope3'


def test_get_logger_provider() -> None:
    logger_provider = get_logger_provider()
    event_logger_provider = get_event_logger_provider()
    config = logfire.DEFAULT_LOGFIRE_INSTANCE.config
    assert logger_provider is config.get_logger_provider()
    assert event_logger_provider is config.get_event_logger_provider()
    assert event_logger_provider._logger_provider is logger_provider  # type: ignore
    assert isinstance(logger_provider.resource, Resource)  # type: ignore


def test_log_events(logs_exporter: InMemoryLogExporter, config_kwargs: dict[str, Any]) -> None:
    logger = get_event_logger('scope')
    record = Event(
        name='my_event',
        timestamp=2,
        severity_number=SeverityNumber.INFO,
        body='body',
        attributes={'key': 'value'},
    )
    with logfire.span('span'):
        logger.emit(record)

    [log_data] = logs_exporter.get_finished_logs()
    assert log_data.instrumentation_scope.name == 'scope'
    assert json.loads(log_data.log_record.to_json()) == snapshot(
        {
            'body': 'body',
            'severity_number': 9,
            'severity_text': None,
            'attributes': {'key': 'value', 'event.name': 'my_event'},
            'dropped_attributes': 0,
            'timestamp': '1970-01-01T00:00:00.000000Z',
            'observed_timestamp': IsStr(),
            'trace_id': '0x00000000000000000000000000000001',
            'span_id': '0x0000000000000001',
            'trace_flags': 1,
            'resource': {
                'attributes': {
                    'telemetry.sdk.language': 'python',
                    'telemetry.sdk.name': 'opentelemetry',
                    'telemetry.sdk.version': IsStr(),
                    'service.name': 'unknown_service',
                },
                'schema_url': '',
            },
        }
    )
