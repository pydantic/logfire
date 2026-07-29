from collections.abc import Iterator
from urllib.parse import quote

import httpx
import pydantic
import pytest
from anthropic import Anthropic, AsyncAnthropic
from anthropic.lib.bedrock import AnthropicBedrock, AsyncAnthropicBedrock
from anthropic.types import Message, TextBlock, Usage
from dirty_equals import IsPartialDict
from httpx._transports.mock import MockTransport
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.llm_providers.anthropic import is_async_client
from logfire._internal.utils import get_version
from logfire.testing import TestExporter

pytestmark = [
    pytest.mark.skipif(
        get_version(pydantic.__version__) < get_version('2.5'),
        reason='Requires Pydantic 2.5 or higher to import genai-prices and set operation.cost attribute.',
    ),
]


def make_request_handler(model_id: str):
    """Build an httpx mock handler for a Bedrock invocation of `model_id`."""

    def request_handler(request: httpx.Request) -> httpx.Response:
        assert request.method == 'POST'
        assert request.url == (
            f'https://bedrock-runtime.us-east-1.amazonaws.com/model/{quote(model_id, safe=":")}/invoke'
        )

        return httpx.Response(
            200,
            json=Message(
                id='test_id',
                content=[
                    TextBlock(
                        text='Nine',
                        type='text',
                    )
                ],
                # Bedrock echoes back the model ID it was invoked with, so this is what
                # the instrumentation has to price.
                model=model_id,
                role='assistant',
                type='message',
                stop_reason='end_turn',
                usage=Usage(input_tokens=2, output_tokens=3),  # Match the snapshot values
            ).model_dump(mode='json'),
        )

    return request_handler


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests"""
    return make_request_handler('anthropic.claude-3-haiku-20240307-v1:0')(request)


def make_client(model_id: str) -> Iterator[AnthropicBedrock]:
    with httpx.Client(transport=MockTransport(make_request_handler(model_id))) as http_client:
        client = AnthropicBedrock(
            aws_region='us-east-1',
            aws_access_key='test-access-key',
            aws_secret_key='test-secret-key',
            aws_session_token='test-session-token',
            http_client=http_client,
        )
        with logfire.instrument_anthropic(version=[1, 'latest']):
            yield client


@pytest.fixture
def mock_client() -> Iterator[AnthropicBedrock]:
    """Fixture that provides a mocked Anthropic client with AWS credentials"""
    yield from make_client('anthropic.claude-3-haiku-20240307-v1:0')


@pytest.mark.filterwarnings('ignore:datetime.datetime.utcnow:DeprecationWarning')
def test_sync_messages(mock_client: AnthropicBedrock, exporter: TestExporter):
    """Test basic synchronous message creation"""
    model_id = 'anthropic.claude-3-haiku-20240307-v1:0'
    response = mock_client.messages.create(
        max_tokens=1000,
        model=model_id,
        system='You are a helpful assistant.',
        messages=[{'role': 'user', 'content': 'What is four plus five?'}],
    )

    # Verify response structure
    assert isinstance(response.content[0], TextBlock)
    assert response.content[0].text == 'Nine'

    # Verify exported spans
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Message with {request_data[model]!r}',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_anthropic_bedrock.py',
                    'code.function': 'test_sync_messages',
                    'code.lineno': 123,
                    'request_data': {
                        'max_tokens': 1000,
                        'system': 'You are a helpful assistant.',
                        'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                        'model': model_id,
                    },
                    'gen_ai.system': 'anthropic',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.request.model': model_id,
                    'gen_ai.request.max_tokens': 1000,
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is four plus five?'}]}
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'You are a helpful assistant.'}],
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': f"Message with '{model_id}'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': {
                        'message': {
                            'content': 'Nine',
                            'role': 'assistant',
                        },
                        'usage': IsPartialDict(
                            {
                                'cache_creation': None,
                                'input_tokens': 2,
                                'output_tokens': 3,
                                'cache_creation_input_tokens': None,
                                'cache_read_input_tokens': None,
                                'server_tool_use': None,
                                'service_tier': None,
                            }
                        ),
                    },
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [{'type': 'text', 'content': 'Nine'}],
                            'finish_reason': 'end_turn',
                        }
                    ],
                    'gen_ai.response.model': model_id,
                    'gen_ai.response.id': 'test_id',
                    'gen_ai.usage.input_tokens': 2,
                    'gen_ai.usage.output_tokens': 3,
                    'gen_ai.usage.raw': {'input_tokens': 2, 'output_tokens': 3},
                    'operation.cost': 4.25e-06,
                    'gen_ai.response.finish_reasons': ['end_turn'],
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'request_data': {'type': 'object'},
                            'gen_ai.system': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.request.model': {},
                            'gen_ai.request.max_tokens': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'async': {},
                            'response_data': {
                                'type': 'object',
                                'properties': {
                                    'usage': {
                                        'type': 'object',
                                        'title': 'Usage',
                                        'x-python-datatype': 'PydanticModel',
                                    },
                                },
                            },
                            'gen_ai.output.messages': {'type': 'array'},
                            'gen_ai.response.model': {},
                            'gen_ai.response.id': {},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.raw': {'type': 'object'},
                            'operation.cost': {},
                            'gen_ai.response.finish_reasons': {'type': 'array'},
                        },
                    },
                },
            }
        ]
    )


@pytest.mark.filterwarnings('ignore:datetime.datetime.utcnow:DeprecationWarning')
@pytest.mark.parametrize(
    'model_id,expected_cost',
    [
        # Plain Bedrock model ID.
        ('anthropic.claude-3-haiku-20240307-v1:0', 4.25e-06),
        # Cross-region inference profiles, which prefix the ID with a scope.
        ('us.anthropic.claude-3-7-sonnet-20250219-v1:0', 5.1e-05),
        ('eu.anthropic.claude-3-7-sonnet-20250219-v1:0', 5.1e-05),
        ('apac.anthropic.claude-3-7-sonnet-20250219-v1:0', 5.1e-05),
        # `global` and `us-gov` are longer than the other scopes, and genai-prices resolves
        # `global` to its own model entry rather than the regional one.
        ('us-gov.anthropic.claude-3-7-sonnet-20250219-v1:0', 5.1e-05),
        ('global.anthropic.claude-sonnet-4-5-20250929-v1:0', 5.1e-05),
        # The full inference profile ARN, which is what `BedrockConverseModel` is often given.
        (
            'arn:aws:bedrock:eu-west-1:123456789012:inference-profile/eu.anthropic.claude-3-7-sonnet-20250219-v1:0',
            5.1e-05,
        ),
    ],
)
def test_bedrock_model_ids_are_priced(model_id: str, expected_cost: float, exporter: TestExporter):
    """Bedrock model IDs are priced under the `aws` provider, in every ID form Bedrock accepts."""
    for client in make_client(model_id):
        client.messages.create(
            max_tokens=1000,
            model=model_id,
            messages=[{'role': 'user', 'content': 'What is four plus five?'}],
        )

    (span,) = exporter.exported_spans_as_dict()
    assert span['attributes']['gen_ai.usage.input_tokens'] == 2
    assert span['attributes']['gen_ai.usage.output_tokens'] == 3
    assert span['attributes']['operation.cost'] == expected_cost


def test_is_async_client() -> None:
    # Test sync clients
    assert not is_async_client(Anthropic)
    assert not is_async_client(AnthropicBedrock)

    # Test async clients
    assert is_async_client(AsyncAnthropic)
    assert is_async_client(AsyncAnthropicBedrock)

    # Test invalid input
    with pytest.raises(AssertionError):
        is_async_client(str)  # type: ignore
