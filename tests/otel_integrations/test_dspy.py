import sys
from types import ModuleType
from unittest import mock

import pydantic
import pytest
from inline_snapshot import snapshot

import logfire
from logfire._internal.utils import get_version
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


@pytest.mark.vcr()
@pytest.mark.skipif(
    sys.version_info >= (3, 14),
    reason='DSPy has compatibility issues with Python 3.14 asyncio deprecation warnings',
)
@pytest.mark.skipif(
    get_version(pydantic.__version__) < get_version('2.5.0'),
    reason='DSPy/LiteLLM requires Pydantic >= 2.5 for Discriminator import',
)
def test_dspy_instrumentation(exporter: TestExporter) -> None:
    # Skip test if dspy can't be imported due to compatibility issues
    dspy = pytest.importorskip('dspy', reason='DSPy import failed due to environment incompatibility')

    logfire.instrument_dspy()

    # Configure DSPy with OpenAI
    lm = dspy.LM('openai/gpt-4o-mini')
    dspy.configure(lm=lm)

    # Define a simple signature
    class BasicQA(dspy.Signature):
        """Answer questions with short factoid answers."""

        question = dspy.InputField()
        answer = dspy.OutputField(desc='often between 1 and 5 words')

    # Create a predictor
    generate_answer = dspy.Predict(BasicQA)

    # Execute the prediction
    prediction = generate_answer(question='What is the capital of France?')

    assert prediction.answer == snapshot('Paris')

    # Verify spans were exported
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert len(spans) > 0

    # Check for DSPy or LLM-related spans (DSPy uses OpenAI/LiteLLM underneath)
    span_names = [span['name'] for span in spans]
    assert any(
        'dspy' in name.lower() or 'completion' in name.lower() or 'predict' in name.lower() for name in span_names
    ), f'No DSPy-related spans found. Got: {span_names}'
