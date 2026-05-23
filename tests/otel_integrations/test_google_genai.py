import os
import warnings
from typing import Any
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
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.7.0'), reason='Requires newer pydantic version'
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
                    'operation.cost': 9.4e-06,
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
                    'operation.cost': 6.7e-06,
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
                    'gen_ai.usage.details.thoughts_tokens': 58,
                    'operation.cost': 0.0001781,
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


def _stub_generate_content(response: Any) -> Any:
    def _generate(self: Any, **kwargs: Any) -> Any:
        return response

    return _generate


def _build_fake_genai_response(
    *,
    model_version: str = 'gemini-2.5-flash',
    prompt_token_count: int = 1000,
    candidates_token_count: int = 200,
    cached_content_token_count: int | None = None,
    thoughts_token_count: int | None = None,
    tool_use_prompt_token_count: int | None = None,
):
    from google.genai.types import (
        Candidate,
        Content,
        FinishReason,
        GenerateContentResponse,
        GenerateContentResponseUsageMetadata,
        Part,
    )

    return GenerateContentResponse(
        model_version=model_version,
        usage_metadata=GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt_token_count,
            candidates_token_count=candidates_token_count,
            cached_content_token_count=cached_content_token_count,
            thoughts_token_count=thoughts_token_count,
            tool_use_prompt_token_count=tool_use_prompt_token_count,
            total_token_count=(prompt_token_count or 0) + (candidates_token_count or 0),
        ),
        candidates=[
            Candidate(
                content=Content(parts=[Part.from_text(text='hi back')], role='model'),
                finish_reason=FinishReason.STOP,
            )
        ],
    )


@pytest.fixture
def reset_google_genai_instrumentation():
    """Force re-instrumentation so monkeypatched `Models.generate_content` is captured.

    The upstream `_MethodsSnapshot` captures `Models.generate_content` at instrument
    time. The instrumentor is a process-wide singleton with an
    `is_instrumented_by_opentelemetry` flag that gates re-instrumentation. We clear
    the flag (the proper `uninstrument()` call asserts on a snapshot that the
    upstream `__init__` resets to None on every `GoogleGenAiSdkInstrumentor()` call,
    which makes it unreliable in a test suite) so the next `instrument()` call
    re-creates the snapshot and picks up the mock.
    """
    from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor

    instrumentor = GoogleGenAiSdkInstrumentor()
    instrumentor._is_instrumented_by_opentelemetry = False  # pyright: ignore[reportPrivateUsage]
    yield
    instrumentor._is_instrumented_by_opentelemetry = False  # pyright: ignore[reportPrivateUsage]


def test_instrument_google_genai_cache_and_thinking_tokens(
    exporter: TestExporter, monkeypatch: pytest.MonkeyPatch, reset_google_genai_instrumentation: None
) -> None:
    from google.genai import Client
    from google.genai.models import Models

    fake_response = _build_fake_genai_response(
        prompt_token_count=1000,
        candidates_token_count=200,
        cached_content_token_count=750,
        thoughts_token_count=80,
        tool_use_prompt_token_count=30,
    )
    monkeypatch.setattr(Models, 'generate_content', _stub_generate_content(fake_response))

    logfire.instrument_google_genai()

    client = Client(api_key='fake')
    client.models.generate_content(model='gemini-2.5-flash', contents='hi')  # type: ignore

    [span] = exporter.exported_spans_as_dict(parse_json_attributes=True)
    attrs = span['attributes']
    assert attrs['gen_ai.usage.input_tokens'] == 1000
    assert attrs['gen_ai.usage.output_tokens'] == 200
    assert attrs['gen_ai.usage.cache_read.input_tokens'] == 750
    assert attrs['gen_ai.usage.details.thoughts_tokens'] == 80
    assert attrs['gen_ai.usage.details.tool_use_prompt_tokens'] == 30
    # operation.cost depends on the current Gemini 2.5 Flash pricing table in
    # genai_prices; just confirm it was computed and is a sensible positive value.
    assert isinstance(attrs['operation.cost'], float)
    assert attrs['operation.cost'] > 0


def test_instrument_google_genai_no_cache_metadata(
    exporter: TestExporter, monkeypatch: pytest.MonkeyPatch, reset_google_genai_instrumentation: None
) -> None:
    from google.genai import Client
    from google.genai.models import Models

    fake_response = _build_fake_genai_response(
        prompt_token_count=58,
        candidates_token_count=9,
    )
    monkeypatch.setattr(Models, 'generate_content', _stub_generate_content(fake_response))

    logfire.instrument_google_genai()

    client = Client(api_key='fake')
    client.models.generate_content(model='gemini-2.5-flash', contents='hi')  # type: ignore

    [span] = exporter.exported_spans_as_dict(parse_json_attributes=True)
    attrs = span['attributes']
    assert 'gen_ai.usage.cache_read.input_tokens' not in attrs
    assert 'gen_ai.usage.details.thoughts_tokens' not in attrs
    assert 'gen_ai.usage.details.tool_use_prompt_tokens' not in attrs
    assert attrs['gen_ai.usage.input_tokens'] == 58
    assert attrs['gen_ai.usage.output_tokens'] == 9


def test_instrument_google_genai_cost_silent_failure(
    exporter: TestExporter, monkeypatch: pytest.MonkeyPatch, reset_google_genai_instrumentation: None
) -> None:
    from google.genai import Client
    from google.genai.models import Models

    fake_response = _build_fake_genai_response(
        model_version='gemini-unknown-999',
        prompt_token_count=1000,
        candidates_token_count=200,
        cached_content_token_count=750,
        thoughts_token_count=80,
    )
    monkeypatch.setattr(Models, 'generate_content', _stub_generate_content(fake_response))

    logfire.instrument_google_genai()

    client = Client(api_key='fake')
    client.models.generate_content(model='gemini-unknown-999', contents='hi')  # type: ignore

    [span] = exporter.exported_spans_as_dict(parse_json_attributes=True)
    attrs = span['attributes']
    assert 'operation.cost' not in attrs
    assert attrs['gen_ai.usage.cache_read.input_tokens'] == 750
    assert attrs['gen_ai.usage.details.thoughts_tokens'] == 80


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
