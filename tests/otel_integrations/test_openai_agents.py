from agents import agent_span, trace
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter


def test_openai_agent_tracing(exporter: TestExporter):
    logfire.instrument_openai_agents()
    logfire.instrument_openai_agents()

    with logfire.span('logfire span 1'):
        with trace('trace_name'):
            with logfire.span('logfire span 2'):
                with agent_span('agent_name'):
                    logfire.info('Hi')

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Hi',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Hi',
                    'logfire.msg': 'Hi',
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'agent',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'attributes': {'logfire.span_type': 'span', 'logfire.msg': 'agent'},
            },
            {
                'name': 'logfire span 2',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing',
                    'code.lineno': 123,
                    'logfire.msg_template': 'logfire span 2',
                    'logfire.msg': 'logfire span 2',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'trace_name',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 8000000000,
                'attributes': {'logfire.span_type': 'span', 'logfire.msg': 'trace_name'},
            },
            {
                'name': 'logfire span 1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing',
                    'code.lineno': 123,
                    'logfire.msg_template': 'logfire span 1',
                    'logfire.msg': 'logfire span 1',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
