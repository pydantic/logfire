from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from unittest import mock

import pydantic
import pytest
from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire
from logfire._internal.utils import get_version
from logfire.testing import TestExporter

if get_version(pydantic.__version__) < get_version('2.10.0'):
    pytest.skip('LiteLLM requires Pydantic >= 2.10', allow_module_level=True)


@contextmanager
def _event_loop_policy(policy: asyncio.AbstractEventLoopPolicy) -> Generator[None, None, None]:
    previous_policy = asyncio.get_event_loop_policy()  # pyright: ignore[reportDeprecated]
    asyncio.set_event_loop_policy(policy)  # pyright: ignore[reportDeprecated]
    try:
        yield
    finally:
        asyncio.set_event_loop_policy(previous_policy)  # pyright: ignore[reportDeprecated]


@contextmanager
def _current_event_loop(loop: asyncio.AbstractEventLoop) -> Generator[None, None, None]:
    """Temporarily set a loop on Python 3.14+, where get_event_loop() never creates one."""
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        asyncio.set_event_loop(previous_loop)


@contextmanager
def _isolated_litellm_event_loop() -> Generator[None, None, None]:
    """Give LiteLLM a loop owned by this test without disturbing an existing loop."""
    if sys.version_info >= (3, 14):
        loop = asyncio.new_event_loop()
        try:
            with _current_event_loop(loop):
                yield
        finally:
            loop.close()
        return

    test_policy = asyncio.DefaultEventLoopPolicy()
    with _event_loop_policy(test_policy):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            yield
        finally:
            loop.close()


@pytest.fixture
def isolated_litellm_event_loop() -> Iterator[None]:
    with _isolated_litellm_event_loop():
        yield


def _assert_litellm_event_loop_is_isolated(existing_loop: asyncio.AbstractEventLoop) -> None:
    with _isolated_litellm_event_loop():
        isolated_loop = asyncio.get_event_loop()
        assert isolated_loop is not existing_loop

    assert isolated_loop.is_closed()
    assert asyncio.get_event_loop() is existing_loop
    assert not existing_loop.is_closed()


def test_isolated_litellm_event_loop_preserves_existing_loop() -> None:
    existing_loop = asyncio.new_event_loop()
    try:
        if sys.version_info >= (3, 14):
            with _current_event_loop(existing_loop):
                _assert_litellm_event_loop_is_isolated(existing_loop)
        else:
            existing_policy = asyncio.DefaultEventLoopPolicy()
            with _event_loop_policy(existing_policy):
                asyncio.set_event_loop(existing_loop)
                _assert_litellm_event_loop_is_isolated(existing_loop)
                assert asyncio.get_event_loop_policy() is existing_policy  # pyright: ignore[reportDeprecated]
    finally:
        existing_loop.close()


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
def test_dspy_instrumentation(exporter: TestExporter, isolated_litellm_event_loop: None) -> None:
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
    question = Field(annotation=str required=True json_schema_extra={'__dspy_field_type': 'input', 'IS_TYPE_UNDEFINED': True, 'prefix': 'Question:', 'desc': '${question}'})
    answer = Field(annotation=str required=True json_schema_extra={'desc': 'often between 1 and 5 words', '__dspy_field_type': 'output', 'IS_TYPE_UNDEFINED': True, 'prefix': 'Answer:'})
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
