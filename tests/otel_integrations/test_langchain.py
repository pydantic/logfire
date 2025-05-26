import contextlib
import importlib
import os
import sys
from typing import TYPE_CHECKING

import pytest
from dirty_equals import IsPartialDict
from inline_snapshot import snapshot

from logfire._internal.exporters.test import TestExporter

os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
os.environ['LANGSMITH_TRACING'] = 'true'

for mod_name, mod in list(sys.modules.items()):
    if mod_name.startswith('langsmith'):
        with contextlib.suppress(Exception):
            importlib.reload(mod)

try:
    from langgraph.prebuilt import create_react_agent  # pyright: ignore [reportUnknownVariableType]
except ImportError:
    pytestmark = pytest.mark.skipif(sys.version_info < (3, 9), reason='Langgraph does not support 3.8')
    if TYPE_CHECKING:
        assert False


@pytest.mark.vcr()
def test_instrument_langchain(exporter: TestExporter):
    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    math_agent = create_react_agent(model='gpt-4o', tools=[add])

    result = math_agent.invoke({'messages': [{'role': 'user', 'content': "what's 123 + 456?"}]})

    assert result['messages'][-1].content == snapshot('123 + 456 equals 579.')

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
                    'function': {'arguments': '{"a":123,"b":456}', 'name': 'add'},
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

    assert [
        (
            span['name'],
            len(span['attributes'].get('all_messages_events', [])),
            'gen_ai.usage.input_tokens' in span['attributes'],
        )
        for span in sorted(spans, key=lambda s: s['start_time'])
    ] == snapshot(
        [
            ('LangGraph', 4, False),
            ('agent', 2, False),
            ('call_model', 2, False),
            ('RunnableSequence', 2, False),
            ('Prompt', 1, False),
            ('ChatOpenAI', 2, True),
            ('should_continue', 2, False),
            ('tools', 0, False),
            ('add', 0, False),
            ('agent', 4, False),
            ('call_model', 4, False),
            ('RunnableSequence', 4, False),
            ('Prompt', 3, False),
            ('ChatOpenAI', 4, True),
            ('should_continue', 4, False),
        ]
    )

    spans = [s for s in spans if s['name'] == 'ChatOpenAI']
    attributes = spans[-1]['attributes']
    assert attributes['gen_ai.request.model'] == snapshot('gpt-4o')
    assert attributes['gen_ai.response.model'] == snapshot('gpt-4o-2024-08-06')
    assert attributes['gen_ai.usage.input_tokens'] == snapshot(79)
    assert attributes['all_messages_events'] == snapshot(
        [
            {'content': "what's 123 + 456?", 'role': 'user'},
            {
                'role': 'assistant',
                'content': '',
                'tool_calls': [
                    {
                        'id': 'call_My0goQVU64UVqhJrtCnLPmnQ',
                        'function': {'arguments': '{"a":123,"b":456}', 'name': 'add'},
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
