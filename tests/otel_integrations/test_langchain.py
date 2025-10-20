import os
import sys

import pydantic
import pytest
from dirty_equals import IsPartialDict
from inline_snapshot import snapshot

from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import get_version

os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
os.environ['LANGSMITH_TRACING'] = 'true'

pytestmark = [
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.11.0'),
        reason='Langgraph does not support older Pydantic versions',
    ),
    pytest.mark.skipif(
        sys.version_info < (3, 10),
        reason='langchain.agents.create_agent requires Python 3.10+',
    ),
]


@pytest.mark.vcr()
def test_instrument_langchain(exporter: TestExporter):
    from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
    from langchain_core.tracers.langchain import wait_for_all_tracers

    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    math_agent = create_agent(model='gpt-4o', tools=[add])  # pyright: ignore [reportUnknownVariableType]

    result = math_agent.invoke({'messages': [{'role': 'user', 'content': "what's 123 + 456?"}]})  # pyright: ignore

    assert result['messages'][-1].content == snapshot('123 + 456 equals 579.')

    # Wait for langsmith OTel thread
    wait_for_all_tracers()

    # All spans that have messages should have some 'prefix' of this list, maybe with extra keys in each dict.
    message_events_minimum = [
        {
            'role': 'user',
            'content': "what's 123 + 456?",
        },
        {
            'role': 'assistant',
            'tool_calls': [
                {
                    'id': 'call_My0goQVU64UVqhJrtCnLPmnQ',
                    'function': {'arguments': {'a': 123, 'b': 456}, 'name': 'add'},
                    'type': 'function',
                }
            ],
        },
        {
            'role': 'tool',
            'content': '579.0',
            'name': 'add',
            'id': 'call_My0goQVU64UVqhJrtCnLPmnQ',
        },
        {
            'role': 'assistant',
            'content': '123 + 456 equals 579.',
        },
    ]

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    for span in spans:
        for actual_event, expected_event in zip(
            span['attributes'].get('all_messages_events', []), message_events_minimum
        ):
            assert actual_event == IsPartialDict(expected_event)

        if span['name'] == 'ChatOpenAI':
            assert span['attributes']['gen_ai.usage.input_tokens'] > 0
            assert span['attributes']['gen_ai.request.model'] == snapshot('gpt-4o-2024-08-06')
            assert span['attributes']['gen_ai.response.model'] == snapshot('gpt-4o-2024-08-06')
            assert span['attributes']['gen_ai.system'] == 'openai'
        else:
            assert 'gen_ai.usage.input_tokens' not in span['attributes']
            assert 'gen_ai.request.model' not in span['attributes']
            assert 'gen_ai.response.model' not in span['attributes']
            assert 'gen_ai.system' not in span['attributes']

    assert [
        (span['name'], len(span['attributes'].get('all_messages_events', [])))
        for span in sorted(spans, key=lambda s: s['start_time'])
    ] == snapshot(
        [
            ('LangGraph', 4),  # Full conversation in outermost span
            # First request and response
            ('model', 2),
            ('ChatOpenAI', 2),
            ('model_to_tools', 2),
            # These have no message events
            ('tools', 0),
            ('add', 0),
            # Here the tool response only gets added
            ('tools_to_model', 3),
            # Second request and response included, thus the whole conversation
            ('model', 4),
            ('ChatOpenAI', 4),
            ('model_to_tools', 4),
        ]
    )

    [span] = [s for s in spans if s['name'] == 'ChatOpenAI' and len(s['attributes']['all_messages_events']) == 4]
    assert span['attributes']['all_messages_events'] == snapshot(
        [
            {'content': "what's 123 + 456?", 'role': 'user'},
            {
                'role': 'assistant',
                'content': '',
                'tool_calls': [
                    {
                        'id': 'call_My0goQVU64UVqhJrtCnLPmnQ',
                        'function': {'arguments': {'a': 123, 'b': 456}, 'name': 'add'},
                        'type': 'function',
                    }
                ],
                'invalid_tool_calls': [],
                'refusal': None,
            },
            {
                'role': 'tool',
                'content': '579.0',
                'name': 'add',
                'id': 'call_My0goQVU64UVqhJrtCnLPmnQ',
                'status': 'success',
            },
            {
                'role': 'assistant',
                'content': '123 + 456 equals 579.',
                'invalid_tool_calls': [],
                'refusal': None,
            },
        ]
    )
