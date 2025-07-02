import os

import pydantic
import pytest
from inline_snapshot import snapshot

from logfire._internal.utils import get_version
from logfire.testing import TestExporter

os.environ['OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'] = 'true'
os.environ.setdefault('GOOGLE_API_KEY', 'foo')


@pytest.mark.skipif(get_version(pydantic.__version__) < get_version('2.6.0'), reason='Requires newer pydantic version')
@pytest.mark.vcr()
def test_instrument_google_genai(exporter: TestExporter) -> None:
    try:
        from opentelemetry.semconv._incubating.attributes.gen_ai_attributes import (
            GEN_AI_REQUEST_CHOICE_COUNT,  # type: ignore  # noqa
        )
    except ImportError:
        pytest.skip('Requires newer opentelemetry semconv package')

    from google.genai import Client, types

    client = Client()

    def get_current_weather(location: str) -> str:
        """Returns the current weather.

        Args:
          location: The city and state, e.g. San Francisco, CA
        """
        return 'rainy'

    response = client.models.generate_content(  # type: ignore
        model='gemini-2.0-flash-001',
        contents='What is the weather like in Boston?',
        config=types.GenerateContentConfig(
            tools=[get_current_weather],
        ),
    )

    assert response.text == snapshot('It is rainy in Boston, MA.\n')
