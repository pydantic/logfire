from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.remove_pending import RemovePendingSpansExporter
from logfire.testing import TestExporter


def test_remove_pending_spans(exporter: TestExporter):
    with logfire.span('span1'):
        logfire.info('log1')

    with logfire.span('span2'):
        logfire.info('log2')

        # Simulate the batch span processor exporting at this point.
        batch1 = exporter.exported_spans
        exporter.clear()

        logfire.info('log3')

    with logfire.span('span3'):
        logfire.info('log4')

    batch2 = exporter.exported_spans

    assert [
        [(span.name, (span.attributes or {}).get('logfire.span_type')) for span in batch] for batch in [batch1, batch2]
    ] == snapshot(
        [
            [('span1', 'pending_span'), ('log1', 'log'), ('span1', 'span'), ('span2', 'pending_span'), ('log2', 'log')],
            [('log3', 'log'), ('span2', 'span'), ('span3', 'pending_span'), ('log4', 'log'), ('span3', 'span')],
        ]
    )

    inner_exporter = TestExporter()
    remove_exporter = RemovePendingSpansExporter(inner_exporter)
    remove_exporter.export(batch1)
    assert [
        (span.name, (span.attributes or {}).get('logfire.span_type')) for span in inner_exporter.exported_spans
    ] == snapshot([('log1', 'log'), ('log2', 'log'), ('span1', 'span'), ('span2', 'pending_span')])
    inner_exporter.clear()
    remove_exporter.export(batch2)
    assert [
        (span.name, (span.attributes or {}).get('logfire.span_type')) for span in inner_exporter.exported_spans
    ] == snapshot([('log3', 'log'), ('log4', 'log'), ('span2', 'span'), ('span3', 'span')])
