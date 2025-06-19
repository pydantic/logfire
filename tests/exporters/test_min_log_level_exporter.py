from inline_snapshot import snapshot
from opentelemetry._events import Event, get_event_logger
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs.export import InMemoryLogExporter, LogExportResult
from opentelemetry.sdk.trace.export import SpanExportResult

import logfire
from logfire._internal.exporters.min_log_level import MinLogLevelFilterLogExporter, MinLogLevelFilterSpanExporter
from logfire.testing import TestExporter, TestLogExporter


def test_remove_debug_spans(exporter: TestExporter):
    logfire.debug('debug1')
    batch1 = exporter.exported_spans
    exporter.clear()
    with logfire.span('span1', _level='debug'):  # spans aren't removed, even if they are debug spans
        logfire.info('info1')
        logfire.debug('debug2')
    batch2 = exporter.exported_spans

    inner_exporter = TestExporter()
    remove_exporter = MinLogLevelFilterSpanExporter(inner_exporter, level_num=9)  # info

    assert remove_exporter.export(batch1) == SpanExportResult.SUCCESS
    assert not inner_exporter.exported_spans

    assert remove_exporter.export(batch2) == SpanExportResult.SUCCESS
    # span1 appears twice because of pending spans
    assert [span.name for span in inner_exporter.exported_spans] == snapshot(['span1', 'info1', 'span1'])


def test_remove_debug_otel_logs(logs_exporter: TestLogExporter) -> None:
    logger = get_event_logger('scope')
    logger.emit(Event(name='ev', severity_number=SeverityNumber.DEBUG, body='debug1'))
    logger.emit(Event(name='ev', severity_number=SeverityNumber.INFO, body='info1'))
    logger.emit(Event(name='ev', body='no_severity'))
    batch = logs_exporter.get_finished_logs()
    inner_exporter = InMemoryLogExporter()
    remove_exporter = MinLogLevelFilterLogExporter(inner_exporter, level_num=9)  # info
    assert remove_exporter.export(batch) == LogExportResult.SUCCESS
    assert [log.log_record.body for log in inner_exporter.get_finished_logs()] == snapshot(['info1', 'no_severity'])
