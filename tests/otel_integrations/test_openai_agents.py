from agents import agent_span, get_current_span, get_current_trace, trace
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.integrations.openai_agents import LogfireSpanWrapper, LogfireTraceWrapper


def test_openai_agent_tracing(exporter: TestExporter):
    logfire.instrument_openai_agents()

    with logfire.span('logfire span 1'):
        assert get_current_trace() is None
        with trace('trace_name') as t:
            assert isinstance(t, LogfireTraceWrapper)
            assert get_current_trace() is t
            with logfire.span('logfire span 2'):
                assert get_current_span() is None
                with agent_span('agent_name') as s:
                    assert get_current_trace() is t
                    assert get_current_span() is s
                    assert isinstance(s, LogfireSpanWrapper)
                    logfire.info('Hi')
                assert get_current_span() is None
        assert get_current_trace() is None

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
                'name': 'Agent {name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'agent_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent {name}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': 'Agent agent_name',
                },
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
                'name': 'OpenAI Agents trace {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'trace',
                    'code.lineno': 123,
                    'name': 'trace_name',
                    'agent_trace_id': 'null',
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{"type":"null"},"group_id":{"type":"null"}}}',
                    'logfire.msg': 'OpenAI Agents trace trace_name',
                },
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


def test_openai_agent_tracing_manual_start_end(exporter: TestExporter):
    logfire.instrument_openai_agents()

    with logfire.span('logfire span 1'):
        t = trace('trace_name')
        assert isinstance(t, LogfireTraceWrapper)
        assert not t.span_helper.span.is_recording()
        assert get_current_trace() is None
        t.start(mark_as_current=True)
        assert t.span_helper.span.is_recording()
        assert get_current_trace() is t
        with logfire.span('logfire span 2'):
            s = agent_span('agent_name')
            assert isinstance(s, LogfireSpanWrapper)
            assert get_current_span() is None
            s.start(mark_as_current=True)
            assert get_current_span() is s

            s2 = agent_span('agent_name2')
            assert isinstance(s2, LogfireSpanWrapper)
            assert get_current_span() is s
            s2.start()
            assert get_current_span() is s

            logfire.info('Hi')

            s2.finish(reset_current=True)
            assert get_current_span() is s
            s.finish(reset_current=True)
            assert get_current_span() is None

        assert get_current_trace() is t
        t.finish(reset_current=True)
        assert get_current_trace() is None

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'Hi',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'log',
                    'logfire.level_num': 9,
                    'logfire.msg_template': 'Hi',
                    'logfire.msg': 'Hi',
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                },
            },
            {
                'name': 'Agent {name}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'agent_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent {name}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name2',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': 'Agent agent_name2',
                },
            },
            {
                'name': 'Agent {name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'agent_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent {name}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': 'Agent agent_name',
                },
            },
            {
                'name': 'logfire span 2',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                    'logfire.msg_template': 'logfire span 2',
                    'logfire.msg': 'logfire span 2',
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'OpenAI Agents trace {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'trace',
                    'code.lineno': 123,
                    'name': 'trace_name',
                    'agent_trace_id': 'null',
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{"type":"null"},"group_id":{"type":"null"}}}',
                    'logfire.msg': 'OpenAI Agents trace trace_name',
                },
            },
            {
                'name': 'logfire span 1',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 11000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                    'logfire.msg_template': 'logfire span 1',
                    'logfire.msg': 'logfire span 1',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )
