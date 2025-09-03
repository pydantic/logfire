from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter


def test_instrument_print(exporter: TestExporter) -> None:
    with logfire.instrument_print():
        name = 'world'
        print('hello', name)

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'print',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'print',
                    'logfire.msg': 'hello world',
                    'code.filepath': 'test_print.py',
                    'code.function': 'test_instrument_print',
                    'code.lineno': 123,
                    'name': 'world',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{}}}',
                },
            }
        ]
    )
