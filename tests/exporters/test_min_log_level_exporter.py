from inline_snapshot import snapshot
from opentelemetry.sdk.trace.export import SpanExportResult

import logfire
from logfire._internal.exporters.min_log_level import MinLogLevelFilterSpanExporter
from logfire.testing import TestExporter


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
