import os
import sys

import pydantic
import pytest
from dirty_equals import IsInt, IsPartialDict, IsStr
from inline_snapshot import snapshot

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter

os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
os.environ.setdefault('GOOGLE_API_KEY', 'foo')


@pytest.mark.skipif(get_version(pydantic.__version__) < get_version('2.6.0'), reason='Requires newer pydantic version')
@pytest.mark.skipif(
    sys.version_info < (3, 10), reason='Python 3.9 produces ResourceWarnings unrelated to the instrumentation'
)
@pytest.mark.vcr()
def test_instrument_google_genai(exporter: TestExporter) -> None:
    try:
        from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
            GEN_AI_REQUEST_CHOICE_COUNT,  # type: ignore  # noqa
        )
    except ImportError:
        pytest.skip('Requires newer opentelemetry semconv package')

    from google.genai import Client, types

    logfire.instrument_google_genai()

    client = Client()

    def get_current_weather(location: str) -> str:
        """Returns the current weather.

        Args:
          location: The city and state, e.g. San Francisco, CA
        """
        return 'rainy'

    response = client.models.generate_content(  # type: ignore
        model='gemini-2.0-flash-001',
        contents=[
            'What is the weather like in Boston?',
            types.Part.from_bytes(data=b'123', mime_type='text/plain'),
        ],
        config=types.GenerateContentConfig(
            tools=[get_current_weather],
        ),
    )

    assert response.text == snapshot('It is rainy in Boston, MA.\n')
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'execute_tool get_current_weather',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'gen_ai.system': 'gemini',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'get_current_weather',
                    'gen_ai.tool.description': IsStr(),
                    'code.function.name': 'get_current_weather',
                    'code.module': 'tests.otel_integrations.test_google_genai',
                    'code.args.positional.count': 0,
                    'code.args.keyword.count': 1,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'execute_tool get_current_weather',
                    'code.function.parameters.location.type': 'str',
                    'code.function.parameters.location.value': 'Boston, MA',
                    'code.function.return.type': 'str',
                    'code.function.return.value': 'rainy',
                },
            },
            {
                'name': 'generate_content gemini-2.0-flash-001',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': IsInt(),
                'end_time': 6000000000,
                'attributes': {
                    'code.function.name': 'google.genai.Models.generate_content',
                    'gen_ai.system': 'gemini',
                    'gen_ai.request.model': 'gemini-2.0-flash-001',
                    'gen_ai.operation.name': 'chat',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'generate_content gemini-2.0-flash-001',
                    'gen_ai.usage.input_tokens': 58,
                    'gen_ai.usage.output_tokens': 9,
                    'gen_ai.response.finish_reasons': ('stop',),
                    'logfire.metrics': IsPartialDict(),
                    'events': [
                        {'content': 'What is the weather like in Boston?', 'role': 'user'},
                        {
                            'content': {
                                'inline_data': {'display_name': None, 'data': 'MTIz', 'mime_type': 'text/plain'}
                            },
                            'role': 'user',
                        },
                        {
                            'index': 0,
                            'finish_reason': 'STOP',
                            'message': {'role': 'assistant', 'content': ['It is rainy in Boston, MA.\n']},
                        },
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'events': {'type': 'array'}}},
                    'gen_ai.response.model': 'gemini-2.0-flash-001',
                },
            },
        ]
    )
