import pytest
from dirty_equals import IsStr
from inline_snapshot import snapshot
from langgraph.prebuilt import create_react_agent  # pyright: ignore [reportUnknownVariableType]
from openinference.instrumentation.langchain import LangChainInstrumentor

from logfire._internal.exporters.test import TestExporter


@pytest.mark.vcr()
def test_instrument_langchain(exporter: TestExporter):
    LangChainInstrumentor().instrument()

    def add(a: float, b: float) -> float:
        """Add two numbers."""
        return a + b

    math_agent = create_react_agent(model='gpt-4o', tools=[add])

    result = math_agent.invoke({'messages': [{'role': 'user', 'content': "what's 123 + 456?"}]})

    assert result['messages'][-1].content == snapshot('123 + 456 equals 579.')

    spans = [s for s in exporter.exported_spans_as_dict(parse_json_attributes=True) if s['name'] == 'ChatOpenAI']
    assert spans[-1]['attributes'] == snapshot(
        {
            'logfire.span_type': 'span',
            'logfire.msg': 'ChatOpenAI',
            'input.value': {
                'messages': [
                    [
                        {
                            'lc': 1,
                            'type': 'constructor',
                            'id': ['langchain', 'schema', 'messages', 'HumanMessage'],
                            'kwargs': {
                                'content': "what's 123 + 456?",
                                'type': 'human',
                                'id': IsStr(),
                            },
                        },
                        {
                            'lc': 1,
                            'type': 'constructor',
                            'id': ['langchain', 'schema', 'messages', 'AIMessage'],
                            'kwargs': {
                                'content': '',
                                'additional_kwargs': {
                                    'tool_calls': [
                                        {
                                            'id': IsStr(),
                                            'function': {'arguments': '{"a":123,"b":456}', 'name': 'add'},
                                            'type': 'function',
                                        }
                                    ],
                                    'refusal': None,
                                },
                                'response_metadata': {
                                    'token_usage': {
                                        'completion_tokens': 17,
                                        'prompt_tokens': 52,
                                        'total_tokens': 69,
                                        'completion_tokens_details': {
                                            'accepted_prediction_tokens': 0,
                                            'audio_tokens': 0,
                                            'reasoning_tokens': 0,
                                            'rejected_prediction_tokens': 0,
                                        },
                                        'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 0},
                                    },
                                    'model_name': 'gpt-4o-2024-08-06',
                                    'system_fingerprint': 'fp_76544d79cb',
                                    'id': IsStr(),
                                    'service_tier': 'default',
                                    'finish_reason': 'tool_calls',
                                    'logprobs': None,
                                },
                                'type': 'ai',
                                'id': IsStr(),
                                'tool_calls': [
                                    {
                                        'name': 'add',
                                        'args': {'a': 123, 'b': 456},
                                        'id': IsStr(),
                                        'type': 'tool_call',
                                    }
                                ],
                                'usage_metadata': {
                                    'input_tokens': 52,
                                    'output_tokens': 17,
                                    'total_tokens': 69,
                                    'input_token_details': {'audio': 0, 'cache_read': 0},
                                    'output_token_details': {'audio': 0, 'reasoning': 0},
                                },
                                'invalid_tool_calls': [],
                            },
                        },
                        {
                            'lc': 1,
                            'type': 'constructor',
                            'id': ['langchain', 'schema', 'messages', 'ToolMessage'],
                            'kwargs': {
                                'content': '579.0',
                                'type': 'tool',
                                'name': 'add',
                                'id': IsStr(),
                                'tool_call_id': IsStr(),
                                'status': 'success',
                            },
                        },
                    ]
                ]
            },
            'input.mime_type': 'application/json',
            'output.value': {
                'generations': [
                    [
                        {
                            'generation_info': {'finish_reason': 'stop', 'logprobs': None},
                            'type': 'ChatGeneration',
                            'message': {
                                'lc': 1,
                                'type': 'constructor',
                                'id': ['langchain', 'schema', 'messages', 'AIMessage'],
                                'kwargs': {
                                    'content': '123 + 456 equals 579.',
                                    'additional_kwargs': {'refusal': None},
                                    'response_metadata': {
                                        'token_usage': {
                                            'completion_tokens': 9,
                                            'prompt_tokens': 79,
                                            'total_tokens': 88,
                                            'completion_tokens_details': {
                                                'accepted_prediction_tokens': 0,
                                                'audio_tokens': 0,
                                                'reasoning_tokens': 0,
                                                'rejected_prediction_tokens': 0,
                                            },
                                            'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 0},
                                        },
                                        'model_name': 'gpt-4o-2024-08-06',
                                        'system_fingerprint': 'fp_9bddfca6e2',
                                        'id': IsStr(),
                                        'service_tier': 'default',
                                        'finish_reason': 'stop',
                                        'logprobs': None,
                                    },
                                    'type': 'ai',
                                    'id': IsStr(),
                                    'usage_metadata': {
                                        'input_tokens': 79,
                                        'output_tokens': 9,
                                        'total_tokens': 88,
                                        'input_token_details': {'audio': 0, 'cache_read': 0},
                                        'output_token_details': {'audio': 0, 'reasoning': 0},
                                    },
                                    'tool_calls': [],
                                    'invalid_tool_calls': [],
                                },
                            },
                            'text': '123 + 456 equals 579.',
                        }
                    ]
                ],
                'llm_output': {
                    'token_usage': {
                        'completion_tokens': 9,
                        'prompt_tokens': 79,
                        'total_tokens': 88,
                        'completion_tokens_details': {
                            'accepted_prediction_tokens': 0,
                            'audio_tokens': 0,
                            'reasoning_tokens': 0,
                            'rejected_prediction_tokens': 0,
                        },
                        'prompt_tokens_details': {'audio_tokens': 0, 'cached_tokens': 0},
                    },
                    'model_name': 'gpt-4o-2024-08-06',
                    'system_fingerprint': 'fp_9bddfca6e2',
                    'id': IsStr(),
                    'service_tier': 'default',
                },
                'run': None,
                'type': 'LLMResult',
            },
            'output.mime_type': 'application/json',
            'llm.input_messages.0.message.role': 'user',
            'llm.input_messages.0.message.content': "what's 123 + 456?",
            'llm.input_messages.1.message.role': 'assistant',
            'llm.input_messages.1.message.tool_calls.0.tool_call.function.name': 'add',
            'llm.input_messages.1.message.tool_calls.0.tool_call.function.arguments': {'a': 123, 'b': 456},
            'llm.input_messages.2.message.role': 'tool',
            'llm.input_messages.2.message.content': '579.0',
            'llm.input_messages.2.message.tool_call_id': IsStr(),
            'llm.input_messages.2.message.name': 'add',
            'llm.output_messages.0.message.role': 'assistant',
            'llm.output_messages.0.message.content': '123 + 456 equals 579.',
            'llm.invocation_parameters': {
                'model': 'gpt-4o',
                'model_name': 'gpt-4o',
                'stream': False,
                '_type': 'openai-chat',
                'stop': None,
                'tools': [
                    {
                        'type': 'function',
                        'function': {
                            'name': 'add',
                            'description': 'Add two numbers.',
                            'parameters': {
                                'properties': {'a': {'type': 'number'}, 'b': {'type': 'number'}},
                                'required': ['a', 'b'],
                                'type': 'object',
                            },
                        },
                    }
                ],
            },
            'llm.tools.0.tool.json_schema': {
                'type': 'function',
                'function': {
                    'name': 'add',
                    'description': 'Add two numbers.',
                    'parameters': {
                        'properties': {'a': {'type': 'number'}, 'b': {'type': 'number'}},
                        'required': ['a', 'b'],
                        'type': 'object',
                    },
                },
            },
            'llm.model_name': 'gpt-4o',
            'llm.token_count.prompt': 79,
            'llm.token_count.completion': 9,
            'llm.token_count.total': 88,
            'llm.token_count.completion_details.audio': 0,
            'llm.token_count.completion_details.reasoning': 0,
            'llm.token_count.prompt_details.audio': 0,
            'llm.token_count.prompt_details.cache_read': 0,
            'metadata': {
                'langgraph_step': 3,
                'langgraph_node': 'agent',
                'langgraph_triggers': ['branch:to:agent'],
                'langgraph_path': ['__pregel_pull', 'agent'],
                'langgraph_checkpoint_ns': IsStr(),
                'checkpoint_ns': IsStr(),
                'ls_provider': 'openai',
                'ls_model_name': 'gpt-4o',
                'ls_model_type': 'chat',
                'ls_temperature': None,
            },
            'openinference.span.kind': 'LLM',
            'logfire.json_schema': {
                'type': 'object',
                'properties': {
                    'input.value': {'type': 'object'},
                    'output.value': {'type': 'object'},
                    'llm.input_messages.1.message.tool_calls.0.tool_call.function.arguments': {'type': 'object'},
                    'llm.invocation_parameters': {'type': 'object'},
                    'llm.tools.0.tool.json_schema': {'type': 'object'},
                    'metadata': {'type': 'object'},
                },
            },
        }
    )
