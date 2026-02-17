import logging
import os
import sys
from unittest import mock

import pydantic
import pytest
from dirty_equals import IsStr

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter
from tests._inline_snapshot import snapshot

# Skip entire module if requirements not met
if sys.version_info < (3, 10):
    pytest.skip('DSPy instrumentation requires Python 3.10+', allow_module_level=True)

if get_version(pydantic.__version__) < get_version('2.5.0'):
    pytest.skip('DSPy/LiteLLM requires Pydantic >= 2.5 for Discriminator import', allow_module_level=True)


def test_missing_openinference_dependency() -> None:
    with mock.patch.dict('sys.modules', {'openinference.instrumentation.dspy': None}):
        with pytest.raises(RuntimeError) as exc_info:
            logfire.instrument_dspy()
        assert str(exc_info.value) == snapshot("""\
The `logfire.instrument_dspy()` method requires the `openinference-instrumentation-dspy` package.
You can install this with:
    pip install 'logfire[dspy]'\
""")


@pytest.mark.vcr()
def test_dspy_instrumentation(exporter: TestExporter) -> None:
    # Skip test if dspy can't be imported due to compatibility issues
    dspy = pytest.importorskip('dspy', reason='DSPy import failed due to environment incompatibility')

    # Disable LiteLLM logger to prevent Pydantic serialization warnings
    logging.getLogger('LiteLLM').disabled = True

    # Instrument DSPy
    logfire.instrument_dspy()

    # Configure DSPy with OpenAI - disable caching
    # Use real API key if present (for recording), otherwise fake key (for VCR replay)
    api_key = os.getenv('OPENAI_API_KEY', 'fake-api-key-for-testing')
    lm = dspy.LM('openai/gpt-5-mini', cache=False, api_key=api_key)
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
    assert spans == snapshot(
        [
            {
                'name': 'LM.__call__',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'LM.__call__',
                    'input.mime_type': 'application/json',
                    'input.value': {
                        'prompt': None,
                        'messages': [
                            {
                                'role': 'system',
                                'content': """\
Your input fields are:
1. `question` (str):
Your output fields are:
1. `answer` (str): often between 1 and 5 words
All interactions will be structured in the following way, with the appropriate values filled in.

[[ ## question ## ]]
{question}

[[ ## answer ## ]]
{answer}

[[ ## completed ## ]]
In adhering to this structure, your objective is: \n\
        Answer questions with short factoid answers.\
""",
                            },
                            {
                                'role': 'user',
                                'content': """\
[[ ## question ## ]]
What is the capital of France?

Respond with the corresponding output fields, starting with the field `[[ ## answer ## ]]`, and then ending with the marker for `[[ ## completed ## ]]`.\
""",
                            },
                        ],
                        'kwargs': {},
                    },
                    'llm.model_name': 'gpt-5-mini',
                    'llm.provider': 'openai',
                    'llm.invocation_parameters': {'temperature': None, 'max_completion_tokens': None},
                    'llm.input_messages.0.message.role': 'system',
                    'llm.input_messages.0.message.content': """\
Your input fields are:
1. `question` (str):
Your output fields are:
1. `answer` (str): often between 1 and 5 words
All interactions will be structured in the following way, with the appropriate values filled in.

[[ ## question ## ]]
{question}

[[ ## answer ## ]]
{answer}

[[ ## completed ## ]]
In adhering to this structure, your objective is: \n\
        Answer questions with short factoid answers.\
""",
                    'llm.input_messages.1.message.role': 'user',
                    'llm.input_messages.1.message.content': """\
[[ ## question ## ]]
What is the capital of France?

Respond with the corresponding output fields, starting with the field `[[ ## answer ## ]]`, and then ending with the marker for `[[ ## completed ## ]]`.\
""",
                    'output.value': [
                        """\
[[ ## answer ## ]]
Paris

[[ ## completed ## ]]\
"""
                    ],
                    'output.mime_type': 'application/json',
                    'llm.output_messages.0.message.role': 'assistant',
                    'llm.output_messages.0.message.content': """\
[[ ## answer ## ]]
Paris

[[ ## completed ## ]]\
""",
                    'openinference.span.kind': 'LLM',
                },
            },
            {
                'name': 'ChatAdapter.__call__',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 6000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'ChatAdapter.__call__',
                    'input.mime_type': 'application/json',
                    'input.value': {
                        'lm': IsStr(),
                        'lm_kwargs': {},
                        'signature': """\
BasicQA(question -> answer
    instructions='Answer questions with short factoid answers.'
    question = Field(annotation=str required=True json_schema_extra={'__dspy_field_type': 'input', 'prefix': 'Question:', 'desc': '${question}'})
    answer = Field(annotation=str required=True json_schema_extra={'desc': 'often between 1 and 5 words', '__dspy_field_type': 'output', 'prefix': 'Answer:'})
)\
""",
                        'demos': [],
                        'inputs': {'question': 'What is the capital of France?'},
                    },
                    'output.value': [{'answer': 'Paris'}],
                    'output.mime_type': 'application/json',
                    'openinference.span.kind': 'CHAIN',
                },
            },
            {
                'name': 'Predict(BasicQA).forward',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 7000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Predict(BasicQA).forward',
                    'input.value': {'question': 'What is the capital of France?'},
                    'input.mime_type': 'application/json',
                    'output.value': {'answer': 'Paris'},
                    'output.mime_type': 'application/json',
                    'openinference.span.kind': 'CHAIN',
                },
            },
            {
                'name': 'Predict.forward',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'logfire.span_type': 'span',
                    'logfire.msg': 'Predict.forward',
                    'input.value': {'question': 'What is the capital of France?'},
                    'input.mime_type': 'application/json',
                    'output.mime_type': 'application/json',
                    'output.value': {'answer': 'Paris'},
                    'openinference.span.kind': 'CHAIN',
                },
            },
        ]
    )
