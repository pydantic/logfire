import json
import os
from typing import Any

import pydantic
import pytest
from dirty_equals import IsPartialDict
from inline_snapshot import snapshot

from logfire._internal.exporters.processor_wrapper import _transform_langsmith_span_attributes  # type: ignore
from logfire._internal.exporters.test import TestExporter
from logfire._internal.utils import get_version

os.environ['LANGSMITH_OTEL_ENABLED'] = 'true'
os.environ['LANGSMITH_TRACING'] = 'true'
os.environ['LANGSMITH_OTEL_ONLY'] = 'true'

# Only the test below needs Langgraph. The rest of this module exercises the span
# transform directly, which has to keep working on every supported Pydantic version.
requires_langgraph = pytest.mark.skipif(
    get_version(pydantic.__version__) < get_version('2.11.0'),
    reason='Langgraph does not support older Pydantic versions',
)


@requires_langgraph
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


def _langsmith_assistant_message(content: list[dict[str, Any]]) -> dict[str, Any]:
    """The parsed `gen_ai.completion` of a LangSmith span whose model made one tool call."""
    return {
        'generations': [
            [
                {
                    'message': {
                        'type': 'constructor',
                        'kwargs': {
                            'type': 'ai',
                            'content': content,
                            'tool_calls': [
                                {'id': 'call_1', 'name': 'add', 'args': {'a': 123, 'b': 456}, 'type': 'tool_call'}
                            ],
                        },
                    }
                }
            ]
        ],
        'llm_output': {'model_name': 'gpt-5'},
    }


FUNCTION_CALL_BLOCK = {
    'arguments': '{"a":123,"b":456}',
    'call_id': 'call_1',
    'name': 'add',
    'type': 'function_call',
    'id': 'fc_1',
    'status': 'completed',
}
REASONING_BLOCK = {
    'type': 'reasoning',
    'id': 'rs_1',
    'summary': [{'text': '**Using the tool**', 'type': 'summary_text'}],
}


@pytest.mark.parametrize(
    'content,expected_content',
    [
        # A model that returns only a tool call, i.e. any model not asked for a reasoning summary.
        ([FUNCTION_CALL_BLOCK], []),
        # The shape recorded in this module's cassette, which kept the dedup working by accident.
        ([REASONING_BLOCK, FUNCTION_CALL_BLOCK], [{'type': 'reasoning', 'content': '**Using the tool**'}]),
    ],
    ids=['tool-call-only', 'reasoning-and-tool-call'],
)
def test_tool_call_is_not_duplicated_in_content(
    content: list[dict[str, Any]], expected_content: list[dict[str, Any]]
) -> None:
    """A function call already listed in `tool_calls` is dropped from `content`.

    The removal used to be skipped when it emptied `content`, so a message whose
    only content was the tool call kept it and the call was rendered twice.
    """
    _, new_attributes = _transform_langsmith_span_attributes(
        {'logfire.span_type': 'span', 'langsmith.metadata.ls_provider': 'openai'},
        {
            'gen_ai.prompt': {
                'messages': [[{'type': 'constructor', 'kwargs': {'type': 'human', 'content': "what's 123 + 456?"}}]]
            },
            'gen_ai.completion': _langsmith_assistant_message(content),
        },
    )

    assistant_message = json.loads(new_attributes['all_messages_events'])[-1]
    assert assistant_message['content'] == expected_content
    assert assistant_message['tool_calls'] == [
        {'id': 'call_1', 'type': 'function', 'function': {'name': 'add', 'arguments': {'a': 123, 'b': 456}}}
    ]
