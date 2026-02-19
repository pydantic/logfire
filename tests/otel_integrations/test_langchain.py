import os
import sys
from typing import Any

import pydantic
import pytest
from dirty_equals import IsPartialDict
from inline_snapshot import snapshot

from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import get_version

os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
os.environ['LANGSMITH_TRACING'] = 'true'
os.environ['LANGSMITH_OTEL_ONLY'] = 'true'

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
def test_instrument_langchain(exporter: TestExporter) -> None:
    from langchain.agents import create_agent  # pyright: ignore[reportUnknownVariableType]
    from langchain_core.tracers.langchain import wait_for_all_tracers
    from langchain_openai import ChatOpenAI

    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    model = ChatOpenAI(
        model='gpt-5',
        reasoning={'effort': 'medium', 'summary': 'concise'},
        base_url='https://gateway.pydantic.dev/proxy/openai/',
    )
    math_agent = create_agent(model, tools=[add])  # pyright: ignore [reportUnknownVariableType]

    result = math_agent.invoke(  # pyright: ignore
        {'messages': [{'role': 'user', 'content': "what's 123 + 456? think carefully and use the tool"}]}
    )

    assert result['messages'][-1].content == snapshot(
        [
            {
                'type': 'text',
                'text': '579',
                'annotations': [],
                'id': 'msg_033ba4b7d827c976006978a474036481a2bddedf312304869f',
            }
        ]
    )

    # Wait for langsmith OTel thread
    wait_for_all_tracers()

    # All spans that have messages should have some 'prefix' of this list, maybe with extra keys in each dict.
    message_events_minimum: list[dict[str, Any]] = [
        {
            'role': 'user',
            'content': "what's 123 + 456? think carefully and use the tool",
        },
        {
            'role': 'assistant',
            'content': [
                {'type': 'reasoning', 'content': '**Using tool to add numbers**'},
                {'type': 'reasoning', 'content': '**Executing addition and finalizing result**'},
            ],
            'tool_calls': [
                {
                    'id': 'call_XlgatTV1bBqLX1fOZTbu7cxO',
                    'function': {'arguments': {'a': 123, 'b': 456}, 'name': 'add'},
                    'type': 'function',
                }
            ],
        },
        {
            'role': 'tool',
            'content': '579.0',
            'name': 'add',
            'id': 'call_XlgatTV1bBqLX1fOZTbu7cxO',
        },
        {
            'role': 'assistant',
            'content': [
                {
                    'type': 'text',
                    'text': '579',
                    'annotations': [],
                    'id': 'msg_033ba4b7d827c976006978a474036481a2bddedf312304869f',
                }
            ],
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
            assert span['attributes']['gen_ai.request.model'] == snapshot('gpt-5')
            assert span['attributes']['gen_ai.response.model'] == snapshot('gpt-5')
            assert span['attributes']['gen_ai.system'] == 'openai'
            assert span['attributes']['gen_ai.provider.name'] == 'openai'
        else:
            assert 'gen_ai.usage.input_tokens' not in span['attributes']
            assert 'gen_ai.request.model' not in span['attributes']
            assert 'gen_ai.response.model' not in span['attributes']
            assert 'gen_ai.system' not in span['attributes']
            assert 'gen_ai.provider.name' not in span['attributes']

    assert [
        (span['name'], len(span['attributes'].get('all_messages_events', [])))
        for span in sorted(spans, key=lambda s: s['start_time'])
    ] == snapshot(
        [
            ('LangGraph', 4),  # Full conversation in outermost span
            # First request and response
            ('model', 2),
            ('ChatOpenAI', 2),
            ('tools', 0),
            ('add', 0),
            # Second request and response included, thus the whole conversation
            ('model', 4),
            ('ChatOpenAI', 4),
        ]
    )

    [span] = [s for s in spans if s['name'] == 'ChatOpenAI' and len(s['attributes']['all_messages_events']) == 4]
    assert span['attributes']['all_messages_events'] == snapshot(
        [
            {'content': "what's 123 + 456? think carefully and use the tool", 'role': 'user'},
            {
                'role': 'assistant',
                'content': [
                    {'type': 'reasoning', 'content': '**Using tool to add numbers**'},
                    {'type': 'reasoning', 'content': '**Executing addition and finalizing result**'},
                ],
                'tool_calls': [
                    {
                        'id': 'call_XlgatTV1bBqLX1fOZTbu7cxO',
                        'function': {'arguments': {'a': 123, 'b': 456}, 'name': 'add'},
                        'type': 'function',
                    }
                ],
                'invalid_tool_calls': [],
            },
            {
                'role': 'tool',
                'content': '579.0',
                'name': 'add',
                'id': 'call_XlgatTV1bBqLX1fOZTbu7cxO',
                'status': 'success',
            },
            {
                'role': 'assistant',
                'content': [
                    {
                        'type': 'text',
                        'text': '579',
                        'annotations': [],
                        'id': 'msg_033ba4b7d827c976006978a474036481a2bddedf312304869f',
                    }
                ],
                'invalid_tool_calls': [],
            },
        ]
    )
