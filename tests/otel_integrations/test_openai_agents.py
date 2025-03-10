import pytest
from agents import Agent, Runner, agent_span, function_tool, get_current_span, get_current_trace, trace
from agents.tracing.spans import NoOpSpan
from agents.tracing.traces import NoOpTrace
from dirty_equals import IsStr
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
                    'agent_trace_id': IsStr(),
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{},"group_id":{"type":"null"}}}',
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
                    'agent_trace_id': IsStr(),
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{},"group_id":{"type":"null"}}}',
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


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_responses(exporter: TestExporter):
    logfire.instrument_openai_agents()

    @function_tool
    def random_number() -> int:
        return 4

    agent2 = Agent(name='agent2', instructions='Return double the number')
    agent1 = Agent(name='agent1', tools=[random_number], handoffs=[agent2])

    await Runner.run(agent1, input='Generate a random number then, hand off to agent2.')

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Response {response_id}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'response_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Response {response_id}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Response resp_67ced68228748191b31ea5d9172a7b4b',
                    'response_id': 'resp_67ced68228748191b31ea5d9172a7b4b',
                    'gen_ai.request.model': 'gpt-4o',
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': False,
                        'truncation': None,
                    },
                    'response': {
                        'id': 'resp_67ced68228748191b31ea5d9172a7b4b',
                        'created_at': 1741608578.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'fc_67ced68352a48191aca3872f9376de86',
                                'arguments': '{}',
                                'call_id': 'call_vwqy7HyGGnNht9NNfxMnnouY',
                                'name': 'random_number',
                                'type': 'function_call',
                                'status': 'completed',
                            },
                            {
                                'id': 'fc_67ced683c8d88191b21be486e163e815',
                                'arguments': '{}',
                                'call_id': 'call_oEA0MnUXCwKevx8txteoopNL',
                                'name': 'transfer_to_agent2',
                                'type': 'function_call',
                                'status': 'completed',
                            },
                        ],
                        'parallel_tool_calls': True,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'name': 'random_number',
                                'parameters': {
                                    'properties': {},
                                    'title': 'random_number_args',
                                    'type': 'object',
                                    'additionalProperties': False,
                                    'required': [],
                                },
                                'strict': True,
                                'type': 'function',
                                'description': None,
                            },
                            {
                                'name': 'transfer_to_agent2',
                                'parameters': {
                                    'additionalProperties': False,
                                    'type': 'object',
                                    'properties': {},
                                    'required': [],
                                },
                                'strict': True,
                                'type': 'function',
                                'description': 'Handoff to the agent2 agent to handle the request. ',
                            },
                        ],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'output_text': '',
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 0,
                            'output_tokens': 0,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 0,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'events': [
                        {
                            'event.name': 'gen_ai.user.message',
                            'content': 'Generate a random number then, hand off to agent2.',
                            'role': 'user',
                        },
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'id': 'call_vwqy7HyGGnNht9NNfxMnnouY',
                                        'type': 'function',
                                        'function': {'name': 'random_number', 'arguments': '{}'},
                                    }
                                ],
                            },
                        },
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'id': 'call_oEA0MnUXCwKevx8txteoopNL',
                                        'type': 'function',
                                        'function': {'name': 'transfer_to_agent2', 'arguments': '{}'},
                                    }
                                ],
                            },
                        },
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'gen_ai.request.model': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'response': {
                                'type': 'object',
                                'title': 'Response',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'output': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'ResponseFunctionToolCall',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'FunctionTool',
                                            'x-python-datatype': 'PydanticModel',
                                        },
                                    },
                                    'reasoning': {
                                        'type': 'object',
                                        'title': 'Reasoning',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'text': {
                                        'type': 'object',
                                        'title': 'ResponseFormatText',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'format': {
                                                'type': 'object',
                                                'title': 'ResponseFormatText',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'ResponseUsage',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'output_tokens_details': {
                                                'type': 'object',
                                                'title': 'OutputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.system': {},
                            'gen_ai.operation.name': {},
                            'events': {'type': 'array'},
                        },
                    },
                },
            },
            {
                'name': 'Function {name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'function_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Function {name}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Function random_number',
                    'name': 'random_number',
                    'input': {},
                    'output': '4',
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'input': {}, 'output': {}}},
                },
            },
            {
                'name': 'Handoff {from_agent} -> {to_agent}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'handoff_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Handoff {from_agent} -> {to_agent}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Handoff agent1 -> agent2',
                    'from_agent': 'agent1',
                    'to_agent': 'agent2',
                    'logfire.json_schema': {'type': 'object', 'properties': {'from_agent': {}, 'to_agent': {}}},
                },
            },
            {
                'name': 'Agent {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'agent_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent {name}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Agent agent1',
                    'name': 'agent1',
                    'handoffs': ['agent2'],
                    'tools': ['random_number'],
                    'output_type': 'str',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'handoffs': {'type': 'array'},
                            'tools': {'type': 'array'},
                            'output_type': {},
                        },
                    },
                },
            },
            {
                'name': 'Response {response_id}',
                'context': {'trace_id': 1, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'response_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Response {response_id}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Response resp_67ced68425f48191a5fb0c2b61cb27dd',
                    'response_id': 'resp_67ced68425f48191a5fb0c2b61cb27dd',
                    'gen_ai.request.model': 'gpt-4o',
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': False,
                        'truncation': None,
                    },
                    'response': {
                        'id': 'resp_67ced68425f48191a5fb0c2b61cb27dd',
                        'created_at': 1741608580.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': 'Return double the number',
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67ced6848e8c81918a946936d3d5bd42',
                                'content': [
                                    {
                                        'annotations': [],
                                        'text': "The random number generated is 4, and it's been handed off to agent2.",
                                        'type': 'output_text',
                                    }
                                ],
                                'role': 'assistant',
                                'status': 'completed',
                                'type': 'message',
                            }
                        ],
                        'parallel_tool_calls': True,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'output_text': "The random number generated is 4, and it's been handed off to agent2.",
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 89,
                            'output_tokens': 18,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 107,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'events': [
                        {
                            'event.name': 'gen_ai.system.message',
                            'content': 'Return double the number',
                            'role': 'system',
                        },
                        {
                            'event.name': 'gen_ai.user.message',
                            'content': 'Generate a random number then, hand off to agent2.',
                            'role': 'user',
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_vwqy7HyGGnNht9NNfxMnnouY',
                                    'type': 'function',
                                    'function': {'name': 'random_number', 'arguments': '{}'},
                                }
                            ],
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_oEA0MnUXCwKevx8txteoopNL',
                                    'type': 'function',
                                    'function': {'name': 'transfer_to_agent2', 'arguments': '{}'},
                                }
                            ],
                        },
                        {
                            'event.name': 'gen_ai.tool.message',
                            'role': 'tool',
                            'id': 'call_vwqy7HyGGnNht9NNfxMnnouY',
                            'content': '4',
                        },
                        {
                            'event.name': 'gen_ai.tool.message',
                            'role': 'tool',
                            'id': 'call_oEA0MnUXCwKevx8txteoopNL',
                            'content': "{'assistant': 'agent2'}",
                        },
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'role': 'assistant',
                                'content': "The random number generated is 4, and it's been handed off to agent2.",
                            },
                        },
                    ],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'gen_ai.request.model': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'response': {
                                'type': 'object',
                                'title': 'Response',
                                'x-python-datatype': 'PydanticModel',
                                'properties': {
                                    'output': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'ResponseOutputMessage',
                                            'x-python-datatype': 'PydanticModel',
                                            'properties': {
                                                'content': {
                                                    'type': 'array',
                                                    'items': {
                                                        'type': 'object',
                                                        'title': 'ResponseOutputText',
                                                        'x-python-datatype': 'PydanticModel',
                                                    },
                                                }
                                            },
                                        },
                                    },
                                    'reasoning': {
                                        'type': 'object',
                                        'title': 'Reasoning',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                    'text': {
                                        'type': 'object',
                                        'title': 'ResponseFormatText',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'format': {
                                                'type': 'object',
                                                'title': 'ResponseFormatText',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                    'usage': {
                                        'type': 'object',
                                        'title': 'ResponseUsage',
                                        'x-python-datatype': 'PydanticModel',
                                        'properties': {
                                            'output_tokens_details': {
                                                'type': 'object',
                                                'title': 'OutputTokensDetails',
                                                'x-python-datatype': 'PydanticModel',
                                            }
                                        },
                                    },
                                },
                            },
                            'gen_ai.response.model': {},
                            'gen_ai.system': {},
                            'gen_ai.operation.name': {},
                            'events': {'type': 'array'},
                        },
                    },
                },
            },
            {
                'name': 'Agent {name}',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'agent_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent {name}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Agent agent2',
                    'name': 'agent2',
                    'handoffs': [],
                    'tools': [],
                    'output_type': 'str',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'handoffs': {'type': 'array'},
                            'tools': {'type': 'array'},
                            'output_type': {},
                        },
                    },
                },
            },
            {
                'name': 'OpenAI Agents trace {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'create.py',
                    'code.function': 'trace',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace {name}',
                    'logfire.msg': 'OpenAI Agents trace Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'name': {}, 'agent_trace_id': {}, 'group_id': {'type': 'null'}},
                    },
                },
            },
        ]
    )


def test_tracing_disabled(exporter: TestExporter):
    with trace('my_trace', disabled=True) as t:
        assert isinstance(t, NoOpTrace)
        with agent_span('my_agent') as s:
            assert isinstance(s, NoOpSpan)

    assert not exporter.exported_spans
