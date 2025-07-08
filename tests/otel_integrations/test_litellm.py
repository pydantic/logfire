import json
import logging
import warnings
from typing import Any

import pytest
from inline_snapshot import snapshot

from logfire.testing import TestExporter

with warnings.catch_warnings():
    warnings.filterwarnings('ignore', category=DeprecationWarning)
    import litellm
    from openinference.instrumentation.litellm import LiteLLMInstrumentor


logging.getLogger('LiteLLM').disabled = True


@pytest.mark.vcr()
def test_litellm_instrumentation(exporter: TestExporter) -> None:
    LiteLLMInstrumentor().instrument()

    def get_current_weather(location: str):
        """Get the current weather in a given location"""
        return json.dumps({'location': 'San Francisco', 'temperature': '72', 'unit': 'fahrenheit'})

    messages = [{'role': 'user', 'content': "What's the weather like in San Francisco?"}]
    tools = [
        {
            'type': 'function',
            'function': {
                'name': 'get_current_weather',
                'description': 'Get the current weather in a given location',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'location': {
                            'type': 'string',
                            'description': 'The city and state, e.g. San Francisco, CA',
                        },
                        'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                    },
                    'required': ['location'],
                },
            },
        }
    ]
    model = 'gpt-4o-mini'
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning)
        response: Any = litellm.completion(model=model, messages=messages, tools=tools)  # type: ignore
    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    messages.append(response_message)

    for tool_call in tool_calls:
        function_name = tool_call.function.name
        assert function_name == get_current_weather.__name__
        function_args = json.loads(tool_call.function.arguments)
        function_response = get_current_weather(
            location=function_args.get('location'),
        )
        messages.append(
            {
                'tool_call_id': tool_call.id,
                'role': 'tool',
                'name': function_name,
                'content': function_response,
            }
        )
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=UserWarning)
        second_response = litellm.completion(model=model, messages=messages)  # type: ignore
    assert second_response.choices[0].message.content == snapshot(  # type: ignore
        'The current temperature in San Francisco is 72°F. If you need more specific weather details or a forecast, let me know!'
    )

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'completion',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'completion',
                    'llm.model_name': 'gpt-4o-mini',
                    'llm.input_messages.0.message.role': 'user',
                    'llm.input_messages.0.message.content': "What's the weather like in San Francisco?",
                    'input.value': {
                        'messages': [{'role': 'user', 'content': "What's the weather like in San Francisco?"}]
                    },
                    'input.mime_type': 'application/json',
                    'llm.invocation_parameters': {
                        'model': 'gpt-4o-mini',
                        'messages': [{'role': 'user', 'content': "What's the weather like in San Francisco?"}],
                        'tools': [
                            {
                                'type': 'function',
                                'function': {
                                    'name': 'get_current_weather',
                                    'description': 'Get the current weather in a given location',
                                    'parameters': {
                                        'type': 'object',
                                        'properties': {
                                            'location': {
                                                'type': 'string',
                                                'description': 'The city and state, e.g. San Francisco, CA',
                                            },
                                            'unit': {'type': 'string', 'enum': ['celsius', 'fahrenheit']},
                                        },
                                        'required': ['location'],
                                    },
                                },
                            }
                        ],
                    },
                    'output.value': {
                        'id': 'chatcmpl-Br2eczuAVPiovQVLOcoEi7qbHonyZ',
                        'created': 1751981286,
                        'model': 'gpt-4o-mini-2024-07-18',
                        'object': 'chat.completion',
                        'system_fingerprint': 'fp_34a54ae93c',
                        'choices': [
                            {
                                'finish_reason': 'tool_calls',
                                'index': 0,
                                'message': {
                                    'content': None,
                                    'role': 'assistant',
                                    'tool_calls': [
                                        {
                                            'function': {
                                                'arguments': '{"location":"San Francisco, CA"}',
                                                'name': 'get_current_weather',
                                            },
                                            'id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                            'type': 'function',
                                        }
                                    ],
                                    'function_call': None,
                                    'annotations': [],
                                },
                                'provider_specific_fields': {},
                            }
                        ],
                        'usage': {
                            'completion_tokens': 18,
                            'prompt_tokens': 80,
                            'total_tokens': 98,
                            'completion_tokens_details': {
                                'accepted_prediction_tokens': 0,
                                'audio_tokens': 0,
                                'reasoning_tokens': 0,
                                'rejected_prediction_tokens': 0,
                            },
                            'prompt_tokens_details': {
                                'audio_tokens': 0,
                                'cached_tokens': 0,
                                'text_tokens': None,
                                'image_tokens': None,
                            },
                        },
                        'service_tier': 'default',
                    },
                    'output.mime_type': 'application/json',
                    'llm.output_messages.0.message.role': 'assistant',
                    'llm.output_messages.0.message.tool_calls.0.tool_call.function.name': 'get_current_weather',
                    'llm.output_messages.0.message.tool_calls.0.tool_call.function.arguments': {
                        'location': 'San Francisco, CA'
                    },
                    'llm.token_count.prompt': 80,
                    'llm.token_count.prompt_details.cache_read': 0,
                    'llm.token_count.prompt_details.audio': 0,
                    'llm.token_count.completion': 18,
                    'llm.token_count.completion_details.reasoning': 0,
                    'llm.token_count.completion_details.audio': 0,
                    'llm.token_count.total': 98,
                    'openinference.span.kind': 'LLM',
                    'request_data': {
                        'messages': [{'role': 'user', 'content': "What's the weather like in San Francisco?"}]
                    },
                    'response_data': {
                        'message': {
                            'content': None,
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'function': {
                                        'arguments': '{"location":"San Francisco, CA"}',
                                        'name': 'get_current_weather',
                                    },
                                    'id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                    'type': 'function',
                                }
                            ],
                            'function_call': None,
                            'annotations': [],
                        },
                        'usage': {
                            'completion_tokens': 18,
                            'prompt_tokens': 80,
                            'total_tokens': 98,
                            'completion_tokens_details': {
                                'accepted_prediction_tokens': 0,
                                'audio_tokens': 0,
                                'reasoning_tokens': 0,
                                'rejected_prediction_tokens': 0,
                            },
                            'prompt_tokens_details': {
                                'audio_tokens': 0,
                                'cached_tokens': 0,
                                'text_tokens': None,
                                'image_tokens': None,
                            },
                        },
                    },
                    'logfire.tags': ['LLM'],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'response_data': {'type': 'object'}},
                    },
                },
            },
            {
                'name': 'completion',
                'context': {'trace_id': 2, 'span_id': 3, 'is_remote': False},
                'parent': None,
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'completion',
                    'llm.model_name': 'gpt-4o-mini',
                    'llm.input_messages.0.message.role': 'user',
                    'llm.input_messages.0.message.content': "What's the weather like in San Francisco?",
                    'llm.input_messages.1.message.role': 'assistant',
                    'llm.input_messages.1.message.tool_calls.0.tool_call.function.name': 'get_current_weather',
                    'llm.input_messages.1.message.tool_calls.0.tool_call.function.arguments': {
                        'location': 'San Francisco, CA'
                    },
                    'llm.input_messages.2.message.role': 'tool',
                    'llm.input_messages.2.message.content': {
                        'location': 'San Francisco',
                        'temperature': '72',
                        'unit': 'fahrenheit',
                    },
                    'input.value': {
                        'messages': [
                            {'role': 'user', 'content': "What's the weather like in San Francisco?"},
                            {
                                'content': None,
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'function': {
                                            'arguments': '{"location":"San Francisco, CA"}',
                                            'name': 'get_current_weather',
                                        },
                                        'id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                        'type': 'function',
                                    }
                                ],
                                'function_call': None,
                                'annotations': [],
                            },
                            {
                                'tool_call_id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                'role': 'tool',
                                'name': 'get_current_weather',
                                'content': '{"location": "San Francisco", "temperature": "72", "unit": "fahrenheit"}',
                            },
                        ]
                    },
                    'input.mime_type': 'application/json',
                    'llm.invocation_parameters': {
                        'model': 'gpt-4o-mini',
                        'messages': [
                            {'role': 'user', 'content': "What's the weather like in San Francisco?"},
                            "Message(content=None, role='assistant', tool_calls=[ChatCompletionMessageToolCall(function=Function(arguments='{\"location\":\"San Francisco, CA\"}', name='get_current_weather'), id='call_SWFIWhfCI6AeHuaV6EM1MRsJ', type='function')], function_call=None, provider_specific_fields={'refusal': None}, annotations=[])",
                            {
                                'tool_call_id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                'role': 'tool',
                                'name': 'get_current_weather',
                                'content': '{"location": "San Francisco", "temperature": "72", "unit": "fahrenheit"}',
                            },
                        ],
                    },
                    'output.value': {
                        'id': 'chatcmpl-Br2eeGlmRiX5iMjOF97Wrkv3Mtvbl',
                        'created': 1751981288,
                        'model': 'gpt-4o-mini-2024-07-18',
                        'object': 'chat.completion',
                        'system_fingerprint': 'fp_34a54ae93c',
                        'choices': [
                            {
                                'finish_reason': 'stop',
                                'index': 0,
                                'message': {
                                    'content': 'The current temperature in San Francisco is 72°F. If you need more specific weather details or a forecast, let me know!',
                                    'role': 'assistant',
                                    'tool_calls': None,
                                    'function_call': None,
                                    'annotations': [],
                                },
                                'provider_specific_fields': {},
                            }
                        ],
                        'usage': {
                            'completion_tokens': 26,
                            'prompt_tokens': 62,
                            'total_tokens': 88,
                            'completion_tokens_details': {
                                'accepted_prediction_tokens': 0,
                                'audio_tokens': 0,
                                'reasoning_tokens': 0,
                                'rejected_prediction_tokens': 0,
                            },
                            'prompt_tokens_details': {
                                'audio_tokens': 0,
                                'cached_tokens': 0,
                                'text_tokens': None,
                                'image_tokens': None,
                            },
                        },
                        'service_tier': 'default',
                    },
                    'output.mime_type': 'application/json',
                    'llm.output_messages.0.message.role': 'assistant',
                    'llm.output_messages.0.message.content': 'The current temperature in San Francisco is 72°F. If you need more specific weather details or a forecast, let me know!',
                    'llm.token_count.prompt': 62,
                    'llm.token_count.prompt_details.cache_read': 0,
                    'llm.token_count.prompt_details.audio': 0,
                    'llm.token_count.completion': 26,
                    'llm.token_count.completion_details.reasoning': 0,
                    'llm.token_count.completion_details.audio': 0,
                    'llm.token_count.total': 88,
                    'openinference.span.kind': 'LLM',
                    'request_data': {
                        'messages': [
                            {'role': 'user', 'content': "What's the weather like in San Francisco?"},
                            {
                                'content': None,
                                'role': 'assistant',
                                'tool_calls': [
                                    {
                                        'function': {
                                            'arguments': '{"location":"San Francisco, CA"}',
                                            'name': 'get_current_weather',
                                        },
                                        'id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                        'type': 'function',
                                    }
                                ],
                                'function_call': None,
                                'annotations': [],
                            },
                            {
                                'tool_call_id': 'call_SWFIWhfCI6AeHuaV6EM1MRsJ',
                                'role': 'tool',
                                'name': 'get_current_weather',
                                'content': '{"location": "San Francisco", "temperature": "72", "unit": "fahrenheit"}',
                            },
                        ]
                    },
                    'response_data': {
                        'message': {
                            'content': 'The current temperature in San Francisco is 72°F. If you need more specific weather details or a forecast, let me know!',
                            'role': 'assistant',
                            'tool_calls': None,
                            'function_call': None,
                            'annotations': [],
                        },
                        'usage': {
                            'completion_tokens': 26,
                            'prompt_tokens': 62,
                            'total_tokens': 88,
                            'completion_tokens_details': {
                                'accepted_prediction_tokens': 0,
                                'audio_tokens': 0,
                                'reasoning_tokens': 0,
                                'rejected_prediction_tokens': 0,
                            },
                            'prompt_tokens_details': {
                                'audio_tokens': 0,
                                'cached_tokens': 0,
                                'text_tokens': None,
                                'image_tokens': None,
                            },
                        },
                    },
                    'logfire.tags': ['LLM'],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'request_data': {'type': 'object'}, 'response_data': {'type': 'object'}},
                    },
                },
            },
        ]
    )
