import sys
from types import ModuleType
from unittest import mock

import pytest
from inline_snapshot import snapshot
from opentelemetry.trace import Tracer, TracerProvider

import logfire
from logfire.testing import TestExporter

pytestmark = [
    pytest.mark.skipif(
        sys.version_info < (3, 10),
        reason='DSPy instrumentation requires Python 3.10+',
    ),
]


def test_missing_openinference_dependency() -> None:
    with mock.patch.dict('sys.modules', {'openinference.instrumentation.dspy': None}):
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_dspy()
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_dspy()` method requires the `openinference-instrumentation-dspy` package.
You can install this with:
    pip install 'logfire[dspy]'\
""")


def test_instrument_dspy_calls_instrumentor() -> None:
    instrumentor = mock.Mock()
    module = ModuleType('openinference.instrumentation.dspy')
    module.DSPyInstrumentor = mock.Mock(return_value=instrumentor)  # type: ignore[attr-defined]

    with (
        mock.patch.dict('sys.modules', {'openinference.instrumentation.dspy': module}),
        mock.patch('logfire._internal.integrations.dspy.util.find_spec', return_value=object()),
    ):
        logfire.instrument_dspy()

    instrumentor.instrument.assert_called_once()


def test_instrument_dspy_exports_span(exporter: TestExporter) -> None:
    class FakeInstrumentor:
        def instrument(self, tracer_provider: TracerProvider, **kwargs: object) -> None:
            tracer: Tracer = tracer_provider.get_tracer('openinference.instrumentation.dspy')
            with tracer.start_as_current_span('dspy.predict') as span:
                span.set_attribute('dspy.test', True)

    module = ModuleType('openinference.instrumentation.dspy')
    module.DSPyInstrumentor = FakeInstrumentor  # type: ignore[attr-defined]

    with (
        mock.patch.dict('sys.modules', {'openinference.instrumentation.dspy': module}),
        mock.patch('logfire._internal.integrations.dspy.util.find_spec', return_value=object()),
    ):
        logfire.instrument_dspy()

    assert exporter.exported_spans_as_dict() == snapshot(
        [
            {
                'name': 'dspy.predict',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {'logfire.span_type': 'span', 'logfire.msg': 'dspy.predict', 'dspy.test': True},
            }
        ]
    )


@pytest.mark.vcr()
def test_dspy_instrumentation(exporter: TestExporter) -> None:
    import os

    import dspy

    # Temporarily set API key for test
    original_key = os.environ.get('OPENAI_API_KEY')
    if not original_key:
        os.environ['OPENAI_API_KEY'] = 'test-api-key'

    try:
        logfire.instrument_dspy()

        # Configure DSPy with OpenAI
        lm = dspy.LM('openai/gpt-4o-mini')
        dspy.configure(lm=lm)  # type: ignore[reportUnknownMemberType]

        # Define a simple signature
        class BasicQA(dspy.Signature):
            """Answer questions with short factoid answers."""

            question = dspy.InputField()  # type: ignore[reportUnknownMemberType]
            answer = dspy.OutputField(desc='often between 1 and 5 words')  # type: ignore[reportUnknownMemberType]

        # Create a predictor
        generate_answer = dspy.Predict(BasicQA)

        # Execute the prediction
        prediction = generate_answer(question='What is the capital of France?')

        assert prediction.answer == snapshot('Paris')  # type: ignore[reportUnknownMemberType]

        # Verify spans were exported
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        assert len(spans) > 0

        # Check for DSPy or LLM-related spans (DSPy uses OpenAI/LiteLLM underneath)
        span_names = [span['name'] for span in spans]
        assert any(
            'dspy' in name.lower() or 'completion' in name.lower() or 'predict' in name.lower() for name in span_names
        ), f'No DSPy-related spans found. Got: {span_names}'
    finally:
        if not original_key:
            os.environ.pop('OPENAI_API_KEY', None)
        else:
            os.environ['OPENAI_API_KEY'] = original_key
