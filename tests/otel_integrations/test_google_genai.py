import os
import warnings
from unittest import mock
from unittest.mock import patch

import pydantic
import pytest
from dirty_equals import IsInt, IsPartialDict, IsStr
from inline_snapshot import snapshot
from opentelemetry._logs import LogRecord, SeverityNumber

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter

os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
os.environ.setdefault('GOOGLE_API_KEY', 'foo')

pytestmark = [
    # google-genai >= 2.9.0 requires pydantic >= 2.12.5. On older pydantic its generated
    # `_gaos` models (which declare `__pydantic_extra__` as a field) fail to import.
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.12.5'), reason='google-genai requires pydantic >= 2.12.5'
    ),
]


def test_missing_opentelemetry_dependency() -> None:
    with mock.patch.dict('sys.modules', {'opentelemetry.instrumentation.google_genai': None}):
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_google_genai()
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_google_genai()` method requires the `opentelemetry-instrumentation-google-genai` package.
You can install this with:
    pip install 'logfire[google-genai]'\
""")


@pytest.mark.vcr()
def test_instrument_google_genai(exporter: TestExporter) -> None:
    from google.genai import Client, types

    logfire.instrument_google_genai()

    client = Client()

    def get_current_weather(location: str) -> str:
        """Returns the current weather.

        Args:
          location: The city and state, e.g. San Francisco, CA
        """
        return 'rainy'

    with warnings.catch_warnings():
        # generate_content itself produces this warning, but only with pydantic 2.9.2 and python 3.13.
        warnings.filterwarnings('ignore', category=UserWarning)

        response = client.models.generate_content(  # type: ignore
            model='gemini-2.0-flash-001',
            contents=[
                'What is the weather like in Boston?',
                types.Part.from_bytes(data=b'123', mime_type='text/plain'),
            ],
            config=types.GenerateContentConfig(
                tools=[get_current_weather],
                system_instruction=[types.Part.from_text(text='help')],
            ),
        )

    assert response.text == snapshot('It is rainy in Boston, MA.\n')
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'execute_tool get_current_weather',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
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
                'end_time': 7000000000,
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
                        {'content': 'help', 'role': 'system'},
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


@pytest.mark.vcr()
def test_instrument_google_genai_no_content(exporter: TestExporter) -> None:
    from google.genai import Client, types

    with patch.dict(os.environ, {'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT': 'false'}):
        logfire.instrument_google_genai()

        client = Client()

        def get_current_weather(location: str) -> str:
            """Returns the current weather."""
            return 'rainy'

        with warnings.catch_warnings():
            # generate_content itself produces this warning, but only with pydantic 2.9.2 and python 3.13.
            warnings.filterwarnings('ignore', category=UserWarning)

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

    assert response.text == snapshot('It is rainy in Boston.\n')
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
                    'gen_ai.tool.description': 'Returns the current weather.',
                    'code.function.name': 'get_current_weather',
                    'code.module': 'tests.otel_integrations.test_google_genai',
                    'code.args.positional.count': 0,
                    'code.args.keyword.count': 1,
                    'logfire.span_type': 'span',
                    'logfire.msg': 'execute_tool get_current_weather',
                    'code.function.parameters.location.type': 'str',
                    'code.function.return.type': 'str',
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
                    'gen_ai.usage.input_tokens': 39,
                    'gen_ai.usage.output_tokens': 7,
                    'gen_ai.response.finish_reasons': ('stop',),
                    'logfire.metrics': IsPartialDict(),
                    'events': [
                        {'content': '<elided>', 'role': 'user'},
                        {
                            'content': '<elided>',
                            'role': 'user',
                        },
                        {'index': 0, 'content': '<elided>', 'finish_reason': 'STOP'},
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'events': {'type': 'array'}}},
                    'gen_ai.response.model': 'gemini-2.0-flash-001',
                },
            },
        ]
    )


@pytest.mark.vcr()
def test_instrument_google_genai_response_schema(exporter: TestExporter) -> None:
    from google.genai import Client, types

    logfire.instrument_google_genai()

    client = Client()

    class ResponseData(pydantic.BaseModel):
        answer: str

    with warnings.catch_warnings():
        # generate_content itself produces this warning, but only with pydantic 2.9.2 and python 3.13.
        warnings.filterwarnings('ignore', category=UserWarning)

        response = client.models.generate_content(  # type: ignore
            model='gemini-2.5-flash',
            contents='Hi',
            config=types.GenerateContentConfig(response_schema=ResponseData, response_mime_type='application/json'),
        )
        assert response.text == snapshot('{"answer":"Hello! How can I help you today?"}')

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'generate_content gemini-2.5-flash',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': IsInt(),
                'end_time': 3000000000,
                'attributes': {
                    'code.function.name': 'google.genai.Models.generate_content',
                    'gen_ai.system': 'gemini',
                    'gen_ai.request.model': 'gemini-2.5-flash',
                    'gen_ai.operation.name': 'chat',
                    'logfire.span_type': 'span',
                    'gen_ai.output.type': 'json',
                    'logfire.msg': 'generate_content gemini-2.5-flash',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 13,
                    'gen_ai.response.finish_reasons': ('stop',),
                    'logfire.metrics': IsPartialDict(),
                    'events': [
                        {'content': 'Hi', 'role': 'user'},
                        {
                            'index': 0,
                            'finish_reason': 'STOP',
                            'message': {
                                'role': 'assistant',
                                'content': ['{"answer":"Hello! How can I help you today?"}'],
                            },
                        },
                    ],
                    'logfire.json_schema': {'type': 'object', 'properties': {'events': {'type': 'array'}}},
                    'gen_ai.response.model': 'gemini-2.5-flash',
                },
            }
        ]
    )


def test_span_event_logger_with_none_parts(exporter: TestExporter) -> None:
    """Test that SpanEventLogger handles parts=None gracefully.

    This can happen when Gemini 3 Pro returns a thinking-only response with no text or tool calls.
    See https://github.com/pydantic/logfire/issues/1675
    """
    from logfire._internal.integrations.google_genai import SpanEventLogger

    with logfire.span('test'):
        logger = SpanEventLogger('test_logger')
        record = LogRecord(
            event_name='gen_ai.choice',
            timestamp=2,
            severity_number=SeverityNumber.INFO,
            body={'content': {'parts': None}, 'index': 0, 'finish_reason': 'STOP'},
        )
        logger.emit(record)

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'test',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_google_genai.py',
                    'code.function': 'test_span_event_logger_with_none_parts',
                    'code.lineno': 123,
                    'logfire.msg_template': 'test',
                    'logfire.span_type': 'span',
                    'logfire.msg': 'test',
                },
                'events': [
                    {
                        'name': 'gen_ai.choice',
                        'timestamp': 2000000000,
                        'attributes': {
                            'event_body': {
                                'index': 0,
                                'finish_reason': 'STOP',
                                'message': {'role': 'assistant', 'content': []},
                            }
                        },
                    }
                ],
            }
        ]
    )


def test_span_event_logger_with_circular_reference(exporter: TestExporter) -> None:
    """SpanEventLogger must not drop the event when the body contains a circular reference.

    The upstream google_genai instrumentation can produce dicts whose `_to_dict`
    representation contains self-loops (e.g. an uploaded `google.genai.types.File`).
    Without the fallback in `emit`, `json.dumps` would raise
    `ValueError: Circular reference detected` and the event would be swallowed by
    `handle_internal_errors`. See https://github.com/pydantic/logfire/issues/1881.
    """
    from typing import Any as _Any

    from logfire._internal.integrations.google_genai import SpanEventLogger

    # Dict with a self-loop — mimics a Gemini File-like object whose _to_dict has a cycle.
    file_part: dict[str, _Any] = {'name': 'files/abc123', 'mime_type': 'audio/wav'}
    file_part['self'] = file_part

    # List with a self-loop — exercises the list branch of _strip_cycles.
    circular_list: list[_Any] = [1, 2, 3]
    circular_list.append(circular_list)

    with logfire.span('test'):
        logger = SpanEventLogger('test_logger')
        # Emit a record with a circular dict in the body.
        record = LogRecord(
            event_name='gen_ai.user.message',
            timestamp=2,
            severity_number=SeverityNumber.INFO,
            body={'content': file_part, 'role': 'user'},
        )
        logger.emit(record)

        # Emit a record with a circular list nested inside a non-circular dict.
        record2 = LogRecord(
            event_name='gen_ai.user.message',
            timestamp=3,
            severity_number=SeverityNumber.INFO,
            body={'content': {'data': circular_list, 'text': 'hello'}, 'role': 'user'},
        )
        logger.emit(record2)

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) == 1
    events = spans[0]['events']
    assert len(events) == 2

    # First event: circular dict.
    # transform_part copies file_part into a new dict (new_part), so file_part is seen at
    # depth 3 (body -> new_part -> file_part). _strip_cycles expands the first occurrence
    # of file_part normally; the back-edge (file_part['self'] == file_part) is replaced
    # with safe_repr once the id is already in the seen-set.
    e1 = events[0]
    assert e1['name'] == 'gen_ai.user.message'
    body1 = e1['attributes']['event_body']
    assert body1['role'] == 'user'
    assert body1['content']['name'] == 'files/abc123'
    assert body1['content']['mime_type'] == 'audio/wav'
    # content['self'] is file_part — it is expanded once, then its own 'self' back-edge
    # becomes a safe_repr string.
    assert body1['content']['self']['name'] == 'files/abc123'
    assert isinstance(body1['content']['self']['self'], str)

    # Second event: circular list — non-cyclic items preserved; back-edge becomes a string.
    e2 = events[1]
    assert e2['name'] == 'gen_ai.user.message'
    body2 = e2['attributes']['event_body']
    assert body2['role'] == 'user'
    assert body2['content']['text'] == 'hello'
    data = body2['content']['data']
    assert data[:3] == [1, 2, 3]
    assert isinstance(data[3], str)  # the self-loop replaced by safe_repr
