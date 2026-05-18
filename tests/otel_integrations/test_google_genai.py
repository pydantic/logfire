import os
import sys
import warnings
from unittest import mock
from unittest.mock import patch

import pydantic
import pytest
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
    pytest.mark.skipif(
        sys.version_info < (3, 10), reason='Python 3.9 produces ResourceWarnings unrelated to the instrumentation'
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
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot([])


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
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot([])


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

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot([])


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
