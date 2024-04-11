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

    assert [span.name for span in batch1] == ['span1 (pending)', 'log1', 'span1', 'span2 (pending)', 'log2']
    assert [span.name for span in batch2] == ['log3', 'span2', 'span3 (pending)', 'log4', 'span3']

    inner_exporter = TestExporter()
    remove_exporter = RemovePendingSpansExporter(inner_exporter)
    remove_exporter.export(batch1)
    assert [span.name for span in inner_exporter.exported_spans] == ['log1', 'log2', 'span1', 'span2 (pending)']
    inner_exporter.clear()
    remove_exporter.export(batch2)
    assert [span.name for span in inner_exporter.exported_spans] == ['log3', 'log4', 'span2', 'span3']
