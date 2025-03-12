from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

import pytest
from dirty_equals import IsInt, IsStr
from inline_snapshot import snapshot
from openai import AsyncOpenAI

import logfire
from logfire._internal.exporters.test import TestExporter

try:
    from agents import (
        Agent,
        FileSearchTool,
        GuardrailFunctionOutput,
        InputGuardrailTripwireTriggered,
        OpenAIChatCompletionsModel,
        Runner,
        SpanData,
        agent_span,
        custom_span,
        function_tool,
        get_current_span,
        get_current_trace,
        input_guardrail,
        trace,
    )
    from agents.tracing.spans import NoOpSpan
    from agents.tracing.traces import NoOpTrace

    from logfire._internal.integrations.openai_agents import LogfireSpanWrapper, LogfireTraceWrapper


except ImportError:
    pytestmark = pytest.mark.skipif(sys.version_info < (3, 9), reason='Requires Python 3.9 or higher')
    if TYPE_CHECKING:
        assert False

os.environ.setdefault('OPENAI_API_KEY', 'foo')


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
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': "Agent run: 'agent_name'",
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing',
                    'code.lineno': 123,
                    'name': 'trace_name',
                    'agent_trace_id': IsStr(),
                    'metadata': 'null',
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{},"group_id":{"type":"null"},"metadata":{"type":"null"}}}',
                    'logfire.msg': 'OpenAI Agents trace: trace_name',
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
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name2',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': "Agent run: 'agent_name2'",
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'name': 'agent_name',
                    'handoffs': 'null',
                    'tools': 'null',
                    'output_type': 'null',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"handoffs":{"type":"null"},"tools":{"type":"null"},"output_type":{"type":"null"}}}',
                    'logfire.msg': "Agent run: 'agent_name'",
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_openai_agent_tracing_manual_start_end',
                    'code.lineno': 123,
                    'name': 'trace_name',
                    'agent_trace_id': IsStr(),
                    'metadata': 'null',
                    'group_id': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': '{"type":"object","properties":{"name":{},"agent_trace_id":{},"group_id":{"type":"null"},"metadata":{"type":"null"}}}',
                    'logfire.msg': 'OpenAI Agents trace: trace_name',
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


def without_code_attrs(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    The Agents SDK runs some things in some weird async context that messes with getting consistent code attributes.

    This function removes the code attributes from the spans to make the tests more stable.
    It only does this if code.function is missing which is a sign of the problem.
    """
    return [
        {
            **span,
            'attributes': {
                k: v
                for k, v in span['attributes'].items()
                if 'code.function' in span['attributes'] or not k.startswith('code')
            },
        }
        for span in spans
    ]


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_responses(exporter: TestExporter):
    logfire.instrument_openai_agents()

    @function_tool
    def random_number() -> int:
        return 4

    agent2 = Agent(name='agent2', instructions='Return double the number')
    agent1 = Agent(name='agent1', tools=[random_number], handoffs=[agent2])

    with logfire.instrument_openai():
        await Runner.run(agent1, input='Generate a random number then, hand off to agent2.')

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
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
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
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
                    'raw_input': [{'content': 'Generate a random number then, hand off to agent2.', 'role': 'user'}],
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                        },
                    },
                },
            },
            {
                'name': 'Function: {name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.msg_template': 'Function: {name}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Function: random_number',
                    'name': 'random_number',
                    'input': {},
                    'output': '4',
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'input': {}, 'output': {}}},
                },
            },
            {
                'name': 'Handoff: {from_agent} -> {to_agent}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.msg_template': 'Handoff: {from_agent} -> {to_agent}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Handoff: agent1 -> agent2',
                    'from_agent': 'agent1',
                    'to_agent': 'agent2',
                    'logfire.json_schema': {'type': 'object', 'properties': {'from_agent': {}, 'to_agent': {}}},
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent1'",
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
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
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
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
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
                    'raw_input': [
                        {'content': 'Generate a random number then, hand off to agent2.', 'role': 'user'},
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
                        {'call_id': 'call_vwqy7HyGGnNht9NNfxMnnouY', 'output': '4', 'type': 'function_call_output'},
                        {
                            'call_id': 'call_oEA0MnUXCwKevx8txteoopNL',
                            'output': "{'assistant': 'agent2'}",
                            'type': 'function_call_output',
                        },
                    ],
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
                    'gen_ai.usage.input_tokens': 89,
                    'gen_ai.usage.output_tokens': 18,
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 13000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent2'",
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
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


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_input_guardrails(exporter: TestExporter):
    logfire.instrument_openai_agents()

    @input_guardrail
    async def zero_guardrail(_context: Any, _agent: Agent[Any], inp: Any) -> GuardrailFunctionOutput:
        return GuardrailFunctionOutput(output_info={'input': inp}, tripwire_triggered='0' in str(inp))

    agent = Agent[str](name='my_agent', input_guardrails=[zero_guardrail])

    await Runner.run(agent, '1+1?')
    with pytest.raises(InputGuardrailTripwireTriggered):
        await Runner.run(agent, '0?')

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Guardrail {name!r} {triggered=}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'Guardrail {name!r} {triggered=}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Guardrail 'zero_guardrail' triggered=False",
                    'name': 'zero_guardrail',
                    'triggered': False,
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'triggered': {}}},
                },
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'response_id': 'resp_67cee263c6e0819184efdc0fe2624cc8',
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
                        'id': 'resp_67cee263c6e0819184efdc0fe2624cc8',
                        'created_at': 1741611619.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67cee2641544819193c128971fa966e3',
                                'content': [{'annotations': [], 'text': '1 + 1 equals 2.', 'type': 'output_text'}],
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
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 29,
                            'output_tokens': 9,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 38,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [{'content': '1+1?', 'role': 'user'}],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': '1+1?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'content': '1 + 1 equals 2.', 'role': 'assistant'},
                        },
                    ],
                    'gen_ai.usage.input_tokens': 29,
                    'gen_ai.usage.output_tokens': 9,
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_input_guardrails',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'my_agent'",
                    'name': 'my_agent',
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_input_guardrails',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
            {
                'name': 'Guardrail {name!r} {triggered=}',
                'context': {'trace_id': 2, 'span_id': 13, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'start_time': 11000000000,
                'end_time': 12000000000,
                'attributes': {
                    'logfire.msg_template': 'Guardrail {name!r} {triggered=}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Guardrail 'zero_guardrail' triggered=True",
                    'name': 'zero_guardrail',
                    'triggered': True,
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'triggered': {}}},
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 2, 'span_id': 11, 'is_remote': False},
                'parent': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'start_time': 10000000000,
                'end_time': 14000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_input_guardrails',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'logfire.msg': "Agent run: 'my_agent' failed: Guardrail tripwire triggered",
                    'name': 'my_agent',
                    'handoffs': [],
                    'tools': [],
                    'output_type': 'str',
                    'error': {'message': 'Guardrail tripwire triggered', 'data': {'guardrail': 'zero_guardrail'}},
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'handoffs': {'type': 'array'},
                            'tools': {'type': 'array'},
                            'output_type': {},
                            'error': {'type': 'object'},
                        },
                    },
                },
            },
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 2, 'span_id': 9, 'is_remote': False},
                'parent': None,
                'start_time': 9000000000,
                'end_time': 15000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_input_guardrails',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_chat_completions(exporter: TestExporter):
    logfire.instrument_openai_agents()

    model = OpenAIChatCompletionsModel('gpt-4o', AsyncOpenAI())
    agent = Agent[str](name='my_agent', model=model)
    with logfire.instrument_openai():
        await Runner.run(agent, '1+1?')
    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Chat completion with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'Chat completion with {gen_ai.request.model!r}',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'logfire.msg': "Chat completion with 'gpt-4o'",
                    'input': [{'role': 'user', 'content': '1+1?'}],
                    'output': [
                        {
                            'content': '1 + 1 = 2',
                            'refusal': None,
                            'role': 'assistant',
                            'audio': None,
                            'function_call': None,
                            'tool_calls': None,
                            'annotations': [],
                        }
                    ],
                    'model_config': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': False,
                        'truncation': None,
                        'base_url': 'https://api.openai.com/v1/',
                    },
                    'usage': {'input_tokens': 11, 'output_tokens': 8},
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'gen_ai.response.model': 'gpt-4o',
                    'gen_ai.usage.input_tokens': 11,
                    'gen_ai.usage.output_tokens': 8,
                    'request_data': {
                        'messages': [
                            {'role': 'user', 'content': '1+1?'},
                            {
                                'content': '1 + 1 = 2',
                                'refusal': None,
                                'role': 'assistant',
                                'annotations': [],
                                'audio': None,
                                'function_call': None,
                                'tool_calls': None,
                            },
                        ],
                        'model': 'gpt-4o',
                    },
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'input': {'type': 'array'},
                            'output': {'type': 'array'},
                            'model_config': {'type': 'object'},
                            'usage': {'type': 'object'},
                            'request_data': {'type': 'object'},
                            'gen_ai.system': {},
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_chat_completions',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'my_agent'",
                    'name': 'my_agent',
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_chat_completions',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )


def test_custom_span(exporter: TestExporter):
    logfire.instrument_openai_agents()

    with trace('my_trace', trace_id='trace_123', group_id='456'):
        with custom_span('my_span') as s:
            s.span_data.name = 'my_span2'
            s.span_data.data = {'foo': 'bar'}

    assert exporter.exported_spans_as_dict(parse_json_attributes=True, _include_pending_spans=True) == snapshot(
        [
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 2, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 1000000000,
                'end_time': 1000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_custom_span',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'agent_trace_id': 'trace_123',
                    'group_id': '456',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'name': {}, 'agent_trace_id': {}, 'group_id': {}, 'metadata': {'type': 'null'}},
                    },
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000000',
                },
            },
            {
                'name': 'Custom span: {name}',
                'context': {'trace_id': 1, 'span_id': 4, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_custom_span',
                    'code.lineno': 123,
                    'name': 'my_span',
                    'data': {},
                    'logfire.msg_template': 'Custom span: {name}',
                    'logfire.msg': 'Custom span: my_span',
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'data': {'type': 'object'}}},
                    'logfire.span_type': 'pending_span',
                    'logfire.pending_parent_id': '0000000000000001',
                },
            },
            {
                'name': 'Custom span: {name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_custom_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Custom span: {name}',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Custom span: my_span2',
                    'name': 'my_span2',
                    'data': {'foo': 'bar'},
                    'logfire.json_schema': {'type': 'object', 'properties': {'name': {}, 'data': {'type': 'object'}}},
                },
            },
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_custom_span',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'metadata': 'null',
                    'group_id': '456',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.span_type': 'span',
                    'agent_trace_id': 'trace_123',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'name': {}, 'agent_trace_id': {}, 'group_id': {}, 'metadata': {'type': 'null'}},
                    },
                },
            },
        ]
    )


def test_unknown_span(exporter: TestExporter):
    logfire.instrument_openai_agents()

    from agents.tracing import GLOBAL_TRACE_PROVIDER

    class MySpanData(SpanData):
        def export(self):
            return {'foo': 'bar', 'type': self.type}

        @property
        def type(self) -> str:
            return 'my_span'

    with trace('my_trace', trace_id='trace_123', group_id='456') as t:
        assert t.name == 'my_trace'
        with GLOBAL_TRACE_PROVIDER.create_span(span_data=MySpanData(), span_id='span_789') as s:
            assert s.trace_id == 'trace_123'
            assert s.span_id == 'span_789'
            assert s.parent_id is None
        s.finish()
    t.finish()

    assert t.export() == snapshot(
        {'object': 'trace', 'id': 'trace_123', 'workflow_name': 'my_trace', 'group_id': '456', 'metadata': None}
    )
    assert s.export() == snapshot(
        {
            'object': 'trace.span',
            'id': 'span_789',
            'trace_id': 'trace_123',
            'parent_id': None,
            'started_at': s.started_at,
            'ended_at': s.ended_at,
            'span_data': {'foo': 'bar', 'type': 'my_span'},
            'error': None,
        }
    )

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'OpenAI agents: {type} span',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_unknown_span',
                    'code.lineno': 123,
                    'logfire.msg_template': 'OpenAI agents: {type} span',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'OpenAI agents: my_span span',
                    'foo': 'bar',
                    'type': 'my_span',
                    'logfire.json_schema': {'type': 'object', 'properties': {'foo': {}, 'type': {}}},
                },
            },
            {
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_unknown_span',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.span_type': 'span',
                    'agent_trace_id': 'trace_123',
                    'group_id': '456',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'name': {}, 'agent_trace_id': {}, 'group_id': {}, 'metadata': {'type': 'null'}},
                    },
                },
            },
        ]
    )


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_responses_simple(exporter: TestExporter):
    logfire.instrument_openai_agents()

    agent1 = Agent(name='agent1')

    with trace('my_trace', trace_id='trace_123'):
        result = await Runner.run(agent1, input='2+2?')
        await Runner.run(agent1, input=result.to_input_list() + [{'role': 'user', 'content': '4?'}])

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'response_id': 'resp_67ceee053cdc81919f39173ee02cb88e',
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
                        'id': 'resp_67ceee053cdc81919f39173ee02cb88e',
                        'created_at': 1741614597.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67ceee05a83c8191a2e1e19ceb63495e',
                                'content': [{'annotations': [], 'text': '2 + 2 equals 4.', 'type': 'output_text'}],
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
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 29,
                            'output_tokens': 9,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 38,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [{'content': '2+2?', 'role': 'user'}],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': '2+2?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'content': '2 + 2 equals 4.', 'role': 'assistant'},
                        },
                    ],
                    'gen_ai.usage.input_tokens': 29,
                    'gen_ai.usage.output_tokens': 9,
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses_simple',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent1'",
                    'name': 'agent1',
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
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'response_id': 'resp_67ceee0623ac819190454bc7af968938',
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
                        'id': 'resp_67ceee0623ac819190454bc7af968938',
                        'created_at': 1741614598.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67ceee06885881918c740a6ca0ce2807',
                                'content': [{'annotations': [], 'text': 'Yes, 2 + 2 equals 4.', 'type': 'output_text'}],
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
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 47,
                            'output_tokens': 12,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 59,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [
                        {'content': '2+2?', 'role': 'user'},
                        {
                            'id': 'msg_67ceee05a83c8191a2e1e19ceb63495e',
                            'content': [{'annotations': [], 'text': '2 + 2 equals 4.', 'type': 'output_text'}],
                            'role': 'assistant',
                            'status': 'completed',
                            'type': 'message',
                        },
                        {'role': 'user', 'content': '4?'},
                    ],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': '2+2?', 'role': 'user'},
                        {'event.name': 'gen_ai.assistant.message', 'content': '2 + 2 equals 4.', 'role': 'assistant'},
                        {'event.name': 'gen_ai.user.message', 'content': '4?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'content': 'Yes, 2 + 2 equals 4.', 'role': 'assistant'},
                        },
                    ],
                    'gen_ai.usage.input_tokens': 47,
                    'gen_ai.usage.output_tokens': 12,
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses_simple',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent1'",
                    'name': 'agent1',
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_responses_simple',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.span_type': 'span',
                    'agent_trace_id': 'trace_123',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_file_search(exporter: TestExporter):
    logfire.instrument_openai_agents()

    agent = Agent(
        name='agent',
        tools=[FileSearchTool(max_num_results=1, vector_store_ids=['vs_67cd9e6afeb4819198cbffafab95d8ba'])],
    )

    with trace('my_trace', trace_id='trace_123'):
        result = await Runner.run(agent, 'Who made Logfire?')
        await Runner.run(agent, input=result.to_input_list() + [{'role': 'user', 'content': '2+2?'}])

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'response_id': 'resp_67ceff39d5e88191885004de76d26e43',
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
                        'id': 'resp_67ceff39d5e88191885004de76d26e43',
                        'created_at': 1741619001.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'fs_67ceff3ab5b081919945a1b5a1185949',
                                'queries': ['Who made Logfire?'],
                                'status': 'completed',
                                'type': 'file_search_call',
                                'results': None,
                            },
                            {
                                'id': 'msg_67ceff3bede881918dd73f17abeefdf4',
                                'content': [
                                    {
                                        'annotations': [
                                            {
                                                'file_id': 'file-CmKZQn5qLRRgcAjS61GSqv',
                                                'index': 27,
                                                'type': 'file_citation',
                                                'filename': 'test.txt',
                                            }
                                        ],
                                        'text': 'Logfire is made by Pydantic.',
                                        'type': 'output_text',
                                    }
                                ],
                                'role': 'assistant',
                                'status': 'completed',
                                'type': 'message',
                            },
                        ],
                        'parallel_tool_calls': True,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'type': 'file_search',
                                'vector_store_ids': ['vs_67cd9e6afeb4819198cbffafab95d8ba'],
                                'max_num_results': 1,
                                'ranking_options': {'ranker': 'auto', 'score_threshold': 0.0},
                                'filters': None,
                            }
                        ],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 1974,
                            'output_tokens': 38,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 2012,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [{'content': 'Who made Logfire?', 'role': 'user'}],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Who made Logfire?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'role': 'assistant',
                                'content': """\
file_search_call

See JSON for details\
""",
                                'data': {
                                    'id': 'fs_67ceff3ab5b081919945a1b5a1185949',
                                    'queries': ['Who made Logfire?'],
                                    'status': 'completed',
                                    'type': 'file_search_call',
                                    'results': None,
                                },
                            },
                        },
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'content': 'Logfire is made by Pydantic.', 'role': 'assistant'},
                        },
                    ],
                    'gen_ai.usage.input_tokens': 1974,
                    'gen_ai.usage.output_tokens': 38,
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
                                        'prefixItems': [
                                            {
                                                'type': 'object',
                                                'title': 'ResponseFileSearchToolCall',
                                                'x-python-datatype': 'PydanticModel',
                                            },
                                            {
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
                                                            'properties': {
                                                                'annotations': {
                                                                    'type': 'array',
                                                                    'items': {
                                                                        'type': 'object',
                                                                        'title': 'AnnotationFileCitation',
                                                                        'x-python-datatype': 'PydanticModel',
                                                                    },
                                                                }
                                                            },
                                                        },
                                                    }
                                                },
                                            },
                                        ],
                                    },
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'FileSearchTool',
                                            'x-python-datatype': 'PydanticModel',
                                            'properties': {
                                                'ranking_options': {
                                                    'type': 'object',
                                                    'title': 'RankingOptions',
                                                    'x-python-datatype': 'PydanticModel',
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_file_search',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent'",
                    'name': 'agent',
                    'handoffs': [],
                    'tools': ['file_search'],
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
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'response_id': 'resp_67ceff3c84548191b620a2cf4c2e37f2',
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
                        'id': 'resp_67ceff3c84548191b620a2cf4c2e37f2',
                        'created_at': 1741619004.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67ceff3d201481918300b33fb2968fb5',
                                'content': [{'annotations': [], 'text': 'The answer is 4.', 'type': 'output_text'}],
                                'role': 'assistant',
                                'status': 'completed',
                                'type': 'message',
                            }
                        ],
                        'parallel_tool_calls': True,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'type': 'file_search',
                                'vector_store_ids': ['vs_67cd9e6afeb4819198cbffafab95d8ba'],
                                'max_num_results': 1,
                                'ranking_options': {'ranker': 'auto', 'score_threshold': 0.0},
                                'filters': None,
                            }
                        ],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None, 'summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 923,
                            'output_tokens': 8,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 931,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [
                        {'content': 'Who made Logfire?', 'role': 'user'},
                        {
                            'id': 'fs_67ceff3ab5b081919945a1b5a1185949',
                            'queries': ['Who made Logfire?'],
                            'status': 'completed',
                            'type': 'file_search_call',
                            'results': None,
                        },
                        {
                            'id': 'msg_67ceff3bede881918dd73f17abeefdf4',
                            'content': [
                                {
                                    'annotations': [
                                        {
                                            'file_id': 'file-CmKZQn5qLRRgcAjS61GSqv',
                                            'index': 27,
                                            'type': 'file_citation',
                                            'filename': 'test.txt',
                                        }
                                    ],
                                    'text': 'Logfire is made by Pydantic.',
                                    'type': 'output_text',
                                }
                            ],
                            'role': 'assistant',
                            'status': 'completed',
                            'type': 'message',
                        },
                        {'role': 'user', 'content': '2+2?'},
                    ],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Who made Logfire?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.unknown',
                            'role': 'unknown',
                            'content': """\
file_search_call

See JSON for details\
""",
                            'data': {
                                'id': 'fs_67ceff3ab5b081919945a1b5a1185949',
                                'queries': ['Who made Logfire?'],
                                'status': 'completed',
                                'type': 'file_search_call',
                                'results': None,
                            },
                        },
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'content': 'Logfire is made by Pydantic.',
                            'role': 'assistant',
                        },
                        {'event.name': 'gen_ai.user.message', 'content': '2+2?', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {'content': 'The answer is 4.', 'role': 'assistant'},
                        },
                    ],
                    'gen_ai.usage.input_tokens': 923,
                    'gen_ai.usage.output_tokens': 8,
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
                                    'tools': {
                                        'type': 'array',
                                        'items': {
                                            'type': 'object',
                                            'title': 'FileSearchTool',
                                            'x-python-datatype': 'PydanticModel',
                                            'properties': {
                                                'ranking_options': {
                                                    'type': 'object',
                                                    'title': 'RankingOptions',
                                                    'x-python-datatype': 'PydanticModel',
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
                                        'title': 'ResponseTextConfig',
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
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_file_search',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'logfire.msg': "Agent run: 'agent'",
                    'name': 'agent',
                    'handoffs': [],
                    'tools': ['file_search'],
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_file_search',
                    'code.lineno': 123,
                    'name': 'my_trace',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: my_trace',
                    'logfire.span_type': 'span',
                    'agent_trace_id': 'trace_123',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_function_tool_exception(exporter: TestExporter):
    logfire.instrument_openai_agents()

    @function_tool
    def tool():
        raise RuntimeError("Ouch, don't do that again!")

    agent = Agent(name='Start Agent', tools=[tool])
    await Runner.run(agent, input='Call the tool.')

    assert without_code_attrs(exporter.exported_spans_as_dict(parse_json_attributes=True)) == snapshot(
        [
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': False,
                        'truncation': None,
                    },
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67d17435ebcc8191b68300d26c22b0f90273f8a636c82b58',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'response': {
                        'id': 'resp_67d17435ebcc8191b68300d26c22b0f90273f8a636c82b58',
                        'created_at': 1741780021.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'fc_67d1743683b4819192c2f0487f38fa280273f8a636c82b58',
                                'arguments': '{}',
                                'call_id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                                'name': 'tool',
                                'type': 'function_call',
                                'status': 'completed',
                            }
                        ],
                        'parallel_tool_calls': True,
                        'temperature': 1.0,
                        'tool_choice': 'auto',
                        'tools': [
                            {
                                'name': 'tool',
                                'parameters': {
                                    'properties': {},
                                    'title': 'tool_args',
                                    'type': 'object',
                                    'additionalProperties': False,
                                    'required': [],
                                },
                                'strict': True,
                                'type': 'function',
                                'description': None,
                            }
                        ],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 244,
                            'output_tokens': 10,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 254,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [{'content': 'Call the tool.', 'role': 'user'}],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Call the tool.', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                                        'type': 'function',
                                        'function': {'name': 'tool', 'arguments': '{}'},
                                    }
                                ],
                            },
                        },
                    ],
                    'gen_ai.usage.input_tokens': 244,
                    'gen_ai.usage.output_tokens': 10,
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
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
                                        'title': 'ResponseTextConfig',
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
                            'gen_ai.system': {},
                            'gen_ai.operation.name': {},
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Function: {name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.msg_template': 'Function: {name}',
                    'logfire.span_type': 'span',
                    'logfire.level_num': 17,
                    'name': 'tool',
                    'input': {},
                    'output': "An error occurred while running the tool. Please try again. Error: Ouch, don't do that again!",
                    'error': {
                        'message': 'Error running tool (non-fatal)',
                        'data': {'tool_name': 'tool', 'error': "Ouch, don't do that again!"},
                    },
                    'logfire.msg': 'Function: tool failed: Error running tool (non-fatal)',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'name': {}, 'input': {}, 'output': {}, 'error': {'type': 'object'}},
                    },
                },
                'events': [
                    {
                        'name': 'exception',
                        'timestamp': IsInt(),
                        'attributes': {
                            'exception.type': 'RuntimeError',
                            'exception.message': "Ouch, don't do that again!",
                            'exception.stacktrace': "RuntimeError: Ouch, don't do that again!",
                            'exception.escaped': 'False',
                        },
                    }
                ],
            },
            {
                'name': 'Responses API with {gen_ai.request.model!r}',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 7000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_function_tool_exception',
                    'code.lineno': 123,
                    'model_settings': {
                        'temperature': None,
                        'top_p': None,
                        'frequency_penalty': None,
                        'presence_penalty': None,
                        'tool_choice': None,
                        'parallel_tool_calls': False,
                        'truncation': None,
                    },
                    'gen_ai.request.model': 'gpt-4o',
                    'logfire.msg_template': 'Responses API with {gen_ai.request.model!r}',
                    'logfire.span_type': 'span',
                    'response_id': 'resp_67d17436e29481919a2bd269518a8a3e0273f8a636c82b58',
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'response': {
                        'id': 'resp_67d17436e29481919a2bd269518a8a3e0273f8a636c82b58',
                        'created_at': 1741780022.0,
                        'error': None,
                        'incomplete_details': None,
                        'instructions': None,
                        'metadata': {},
                        'model': 'gpt-4o-2024-08-06',
                        'object': 'response',
                        'output': [
                            {
                                'id': 'msg_67d174373e2c81918c8b92e4a39381c70273f8a636c82b58',
                                'content': [
                                    {
                                        'annotations': [],
                                        'text': 'It seems there was an error when trying to call the tool. If you need help with something specific, feel free to let me know!',
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
                        'tools': [
                            {
                                'name': 'tool',
                                'parameters': {
                                    'properties': {},
                                    'title': 'tool_args',
                                    'type': 'object',
                                    'additionalProperties': False,
                                    'required': [],
                                },
                                'strict': True,
                                'type': 'function',
                                'description': None,
                            }
                        ],
                        'top_p': 1.0,
                        'max_output_tokens': None,
                        'previous_response_id': None,
                        'reasoning': {'effort': None, 'generate_summary': None},
                        'status': 'completed',
                        'text': {'format': {'type': 'text'}},
                        'truncation': 'disabled',
                        'usage': {
                            'input_tokens': 283,
                            'output_tokens': 30,
                            'output_tokens_details': {'reasoning_tokens': 0},
                            'total_tokens': 313,
                            'input_tokens_details': {'cached_tokens': 0},
                        },
                        'user': None,
                        'store': True,
                    },
                    'gen_ai.system': 'openai',
                    'gen_ai.operation.name': 'chat',
                    'raw_input': [
                        {'content': 'Call the tool.', 'role': 'user'},
                        {
                            'id': 'fc_67d1743683b4819192c2f0487f38fa280273f8a636c82b58',
                            'arguments': '{}',
                            'call_id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                            'name': 'tool',
                            'type': 'function_call',
                            'status': 'completed',
                        },
                        {
                            'call_id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                            'output': "An error occurred while running the tool. Please try again. Error: Ouch, don't do that again!",
                            'type': 'function_call_output',
                        },
                    ],
                    'events': [
                        {'event.name': 'gen_ai.user.message', 'content': 'Call the tool.', 'role': 'user'},
                        {
                            'event.name': 'gen_ai.assistant.message',
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                                    'type': 'function',
                                    'function': {'name': 'tool', 'arguments': '{}'},
                                }
                            ],
                        },
                        {
                            'event.name': 'gen_ai.tool.message',
                            'role': 'tool',
                            'id': 'call_OpJ32C09GImFzxYLe01MiOOd',
                            'content': "An error occurred while running the tool. Please try again. Error: Ouch, don't do that again!",
                        },
                        {
                            'event.name': 'gen_ai.choice',
                            'index': 0,
                            'message': {
                                'content': 'It seems there was an error when trying to call the tool. If you need help with something specific, feel free to let me know!',
                                'role': 'assistant',
                            },
                        },
                    ],
                    'gen_ai.usage.input_tokens': 283,
                    'gen_ai.usage.output_tokens': 30,
                    'logfire.msg': "Responses API with 'gpt-4o'",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'response_id': {},
                            'model_settings': {
                                'type': 'object',
                                'title': 'ModelSettings',
                                'x-python-datatype': 'dataclass',
                            },
                            'gen_ai.request.model': {},
                            'gen_ai.response.model': {},
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
                                        'title': 'ResponseTextConfig',
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
                            'gen_ai.system': {},
                            'gen_ai.operation.name': {},
                            'raw_input': {'type': 'array'},
                            'events': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                        },
                    },
                },
            },
            {
                'name': 'Agent run: {name!r}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_function_tool_exception',
                    'code.lineno': 123,
                    'logfire.msg_template': 'Agent run: {name!r}',
                    'logfire.span_type': 'span',
                    'name': 'Start Agent',
                    'handoffs': [],
                    'tools': ['tool'],
                    'output_type': 'str',
                    'logfire.msg': "Agent run: 'Start Agent'",
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
                'name': 'OpenAI Agents trace: {name}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_openai_agents.py',
                    'code.function': 'test_function_tool_exception',
                    'code.lineno': 123,
                    'name': 'Agent workflow',
                    'group_id': 'null',
                    'metadata': 'null',
                    'logfire.msg_template': 'OpenAI Agents trace: {name}',
                    'logfire.msg': 'OpenAI Agents trace: Agent workflow',
                    'logfire.span_type': 'span',
                    'agent_trace_id': IsStr(),
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'name': {},
                            'agent_trace_id': {},
                            'group_id': {'type': 'null'},
                            'metadata': {'type': 'null'},
                        },
                    },
                },
            },
        ]
    )
