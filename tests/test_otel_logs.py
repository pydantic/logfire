from __future__ import annotations

from typing import Any, Sequence
from unittest import mock

import pytest
import requests.exceptions
from dirty_equals import IsStr
from inline_snapshot import snapshot
from opentelemetry._events import Event, get_event_logger, get_event_logger_provider
from opentelemetry._logs import LogRecord, SeverityNumber, get_logger, get_logger_provider
from opentelemetry.sdk._logs import LogData
from opentelemetry.sdk._logs.export import (
    InMemoryLogExporter,
    LogExporter,
    LogExportResult,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.resources import Resource

import logfire
from logfire import suppress_instrumentation
from logfire._internal.exporters.otlp import QuietLogExporter
from logfire.testing import TestLogExporter


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
    with suppress_instrumentation():
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
    resource = logger_provider.resource  # type: ignore
    assert isinstance(resource, Resource)
    assert get_logger('scope').resource is resource  # type: ignore


def test_log_events(logs_exporter: TestLogExporter) -> None:
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

    assert logs_exporter.exported_logs_as_dicts(include_resources=True, include_instrumentation_scope=True) == snapshot(
        [
            {
                'body': 'body',
                'severity_number': 9,
                'severity_text': None,
                'attributes': {'key': 'value', 'event.name': 'my_event'},
                'timestamp': 2000000000,
                'observed_timestamp': 3000000000,
                'trace_id': 1,
                'span_id': 1,
                'trace_flags': 1,
                'resource': {
                    'attributes': {
                        'service.instance.id': '00000000000000000000000000000000',
                        'telemetry.sdk.language': 'python',
                        'telemetry.sdk.name': 'opentelemetry',
                        'telemetry.sdk.version': '0.0.0',
                        'service.name': 'unknown_service',
                        'process.pid': 1234,
                        'process.runtime.name': 'cpython',
                        'process.runtime.version': IsStr(),
                        'process.runtime.description': IsStr(),
                        'service.version': IsStr(),
                    },
                },
                'instrumentation_scope': 'scope',
            }
        ]
    )


def test_quiet_log_exporter(caplog: pytest.LogCaptureFixture):
    class ConnectionErrorExporter(LogExporter):
        shutdown_called = False

        def shutdown(self):
            self.shutdown_called = True

        def export(self, batch: Sequence[LogData]):
            raise requests.exceptions.ConnectionError()

    connection_error_exporter = ConnectionErrorExporter()
    exporter = QuietLogExporter(connection_error_exporter)

    assert exporter.export([]) == LogExportResult.FAILURE
    assert not caplog.messages

    assert not connection_error_exporter.shutdown_called
    exporter.shutdown()
    assert connection_error_exporter.shutdown_called


def test_no_events_sdk():
    assert logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_event_logger_provider() is not None
    with mock.patch.dict('sys.modules', {'opentelemetry.sdk._events': None}):
        logfire_instance = logfire.configure(send_to_logfire=False, local=True)
        assert logfire_instance.config.get_event_logger_provider() is None
        logfire_instance.force_flush()
        logfire_instance.shutdown()
