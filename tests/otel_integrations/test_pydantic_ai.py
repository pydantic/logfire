import sys
import warnings
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import pydantic
import pytest
from dirty_equals import IsPartialDict
from inline_snapshot import snapshot

import logfire
from logfire._internal.exporters.test import TestExporter
from logfire._internal.tracer import _ProxyTracer  # type: ignore
from logfire._internal.utils import get_version

try:
    from pydantic_ai import Agent, BinaryContent
    from pydantic_ai.models.instrumented import InstrumentationSettings, InstrumentedModel
    from pydantic_ai.models.test import TestModel

except Exception:
    assert not TYPE_CHECKING

pytestmark = [
    pytest.mark.skipif(sys.version_info < (3, 10), reason='Pydantic AI requires Python 3.10 or higher'),
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.10'), reason='Pydantic AI requires Pydantic 2.10 or higher'
    ),
]


@pytest.mark.anyio
async def test_instrument_pydantic_ai():
    logfire_inst = logfire.configure(local=True)

    model = TestModel()

    # Instrumenting a model returns a new model and leaves the original as is.
    instrumented = logfire_inst.instrument_pydantic_ai(model)
    assert isinstance(instrumented, InstrumentedModel)
    assert isinstance(model, TestModel)

    agent1 = Agent()
    agent2 = Agent()

    def get_model(a: Agent):
        return a._get_model(model)  # type: ignore

    # This is the default.
    Agent.instrument_all(False)
    assert get_model(agent1) is model

    # Instrument a single agent.
    logfire_inst.instrument_pydantic_ai(agent1)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    assert m.wrapped is model
    assert m.instrumentation_settings.version == InstrumentationSettings().version
    assert isinstance(m.instrumentation_settings.tracer, _ProxyTracer)
    assert m.instrumentation_settings.tracer.provider is logfire_inst.config.get_tracer_provider()

    # Other agents are unaffected.
    m2 = get_model(agent2)
    assert m2 is model

    # Now instrument all agents. Also use the (currently not default) version
    logfire_inst.instrument_pydantic_ai(version=1, include_binary_content=False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    # agent1 still has its own instrumentation settings which override the global ones.
    assert m.instrumentation_settings.version == InstrumentationSettings().version
    assert m.instrumentation_settings.include_binary_content == InstrumentationSettings().include_binary_content
    # agent2 uses the global settings.
    m2 = get_model(agent2)
    assert isinstance(m2, InstrumentedModel)
    assert m2.instrumentation_settings.version == 1
    assert not m2.instrumentation_settings.include_binary_content

    # Remove the global instrumentation. agent1 remains instrumented.
    Agent.instrument_all(False)
    m = get_model(agent1)
    assert isinstance(m, InstrumentedModel)
    m2 = get_model(agent2)
    assert m2 is model

    # Test all known parameters
    logfire_inst.instrument_pydantic_ai(
        include_binary_content=False,
        include_content=False,
        version=1,
        event_mode='logs',
    )
    m = get_model(agent2)
    assert isinstance(m, InstrumentedModel)
    assert m.instrumentation_settings.version == 1
    assert not m.instrumentation_settings.include_binary_content
    assert not m.instrumentation_settings.include_content
    assert m.instrumentation_settings.event_mode == 'logs'
    Agent.instrument_all(False)


def test_invalid_instrument_pydantic_ai():
    with pytest.raises(TypeError):
        logfire.instrument_pydantic_ai(42)  # type: ignore


@pytest.mark.vcr()
@pytest.mark.anyio
async def test_pydantic_ai_gcs_upload(exporter: TestExporter, config_kwargs: dict[str, Any]):
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=ImportWarning)
        warnings.filterwarnings('ignore', category=FutureWarning)

        from logfire.experimental.uploaders.gcs import GcsUploader

    bucket_name = 'test-bucket'
    data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    media_type = 'image/png'
    key = f'1970-01-01/{media_type}/ebf4f635a17d10d6eb46ba680b70142419aa3220f228001a036d311a22ee9d2a'
    image_url = f'https://storage.cloud.google.com/{bucket_name}/{key}'

    mock_client = Mock()
    uploader = GcsUploader(bucket_name, client=mock_client)
    assert uploader.bucket is mock_client.bucket(bucket_name)
    assert isinstance(uploader.bucket, Mock)

    config_kwargs['advanced'].uploader = uploader
    logfire.configure(**config_kwargs)

    agent = Agent('openai:gpt-4o')
    logfire.instrument_pydantic_ai(agent, version=3)

    await agent.run(['What is this?', BinaryContent(data=data, media_type=media_type)])

    blob = uploader.bucket.blob
    blob.assert_called_with(key)
    calls = blob(key).upload_from_file.call_args_list
    assert len(calls) == 2
    for call in calls:
        assert call.args[0].read() == data
        assert call.kwargs['content_type'] == media_type

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat gpt-4o',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.system': 'openai',
                    'gen_ai.request.model': 'gpt-4o',
                    'server.address': 'api.openai.com',
                    'model_request_parameters': {
                        'function_tools': [],
                        'builtin_tools': [],
                        'output_mode': 'text',
                        'output_object': None,
                        'output_tools': [],
                        'allow_text_output': True,
                        'allow_image_output': False,
                    },
                    'logfire.span_type': 'span',
                    'logfire.msg': 'chat gpt-4o',
                    'gen_ai.input.messages': [
                        {
                            'role': 'user',
                            'parts': [
                                {'type': 'text', 'content': 'What is this?'},
                                {
                                    'type': 'image-url',
                                    'url': image_url,
                                },
                            ],
                        }
                    ],
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': 'The image shows the lowercase Greek letter "pi" (π). π is a mathematical constant representing the ratio of a circle\'s circumference to its diameter, approximately equal to 3.14159. It\'s widely used in mathematics and science.',
                                }
                            ],
                            'finish_reason': 'stop',
                        }
                    ],
                    'logfire.json_schema': IsPartialDict(),
                    'gen_ai.usage.input_tokens': 266,
                    'gen_ai.usage.output_tokens': 47,
                    'gen_ai.response.model': 'gpt-4o-2024-08-06',
                    'operation.cost': 0.001135,
                    'gen_ai.response.id': 'chatcmpl-CWmRLk5TMkoir3x9mJHUlwsq7oart',
                    'gen_ai.response.finish_reasons': ('stop',),
                },
            },
            {
                'name': 'invoke_agent agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'model_name': 'gpt-4o',
                    'agent_name': 'agent',
                    'gen_ai.agent.name': 'agent',
                    'logfire.msg': 'agent run',
                    'logfire.span_type': 'span',
                    'final_result': 'The image shows the lowercase Greek letter "pi" (π). π is a mathematical constant representing the ratio of a circle\'s circumference to its diameter, approximately equal to 3.14159. It\'s widely used in mathematics and science.',
                    'gen_ai.usage.input_tokens': 266,
                    'gen_ai.usage.output_tokens': 47,
                    'pydantic_ai.all_messages': [
                        {
                            'role': 'user',
                            'parts': [
                                {'type': 'text', 'content': 'What is this?'},
                                {
                                    'type': 'image-url',
                                    'url': 'https://storage.cloud.google.com/test-bucket/1970-01-01/image/png/ebf4f635a17d10d6eb46ba680b70142419aa3220f228001a036d311a22ee9d2a',
                                },
                            ],
                        },
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': 'The image shows the lowercase Greek letter "pi" (π). π is a mathematical constant representing the ratio of a circle\'s circumference to its diameter, approximately equal to 3.14159. It\'s widely used in mathematics and science.',
                                }
                            ],
                            'finish_reason': 'stop',
                        },
                    ],
                    'logfire.json_schema': IsPartialDict(),
                    'logfire.metrics': IsPartialDict(),
                },
            },
        ]
    )
