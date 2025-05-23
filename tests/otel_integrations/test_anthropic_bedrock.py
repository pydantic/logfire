from typing import Iterator

import httpx
import pytest
from anthropic import Anthropic, AnthropicBedrock, AsyncAnthropic, AsyncAnthropicBedrock
from anthropic.types import Message, TextBlock, Usage
from dirty_equals import IsJson
from httpx._transports.mock import MockTransport
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.llm_providers.anthropic import is_async_client
from logfire.testing import TestExporter


def request_handler(request: httpx.Request) -> httpx.Response:
    """Used to mock httpx requests"""
    model_id = 'anthropic.claude-3-haiku-20240307-v1:0'

    assert request.method == 'POST'
    assert request.url == f'https://bedrock-runtime.us-east-1.amazonaws.com/model/{model_id}/invoke'

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
            model=model_id,
            role='assistant',
            type='message',
            usage=Usage(input_tokens=2, output_tokens=3),  # Match the snapshot values
        ).model_dump(mode='json'),
    )


@pytest.fixture
def mock_client() -> Iterator[AnthropicBedrock]:
    """Fixture that provides a mocked Anthropic client with AWS credentials"""
    with httpx.Client(transport=MockTransport(request_handler)) as http_client:
        client = AnthropicBedrock(
            aws_region='us-east-1',
            aws_access_key='test-access-key',
            aws_secret_key='test-secret-key',
            aws_session_token='test-session-token',
            http_client=http_client,
        )
        with logfire.instrument_anthropic():
            yield client


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
    assert exporter.exported_spans_as_dict() == snapshot(
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
                    'request_data': IsJson(
                        {
                            'max_tokens': 1000,
                            'system': 'You are a helpful assistant.',
                            'messages': [{'role': 'user', 'content': 'What is four plus five?'}],
                            'model': model_id,
                        }
                    ),
                    'async': False,
                    'logfire.msg_template': 'Message with {request_data[model]!r}',
                    'logfire.msg': f"Message with '{model_id}'",
                    'logfire.span_type': 'span',
                    'logfire.tags': ('LLM',),
                    'response_data': IsJson(
                        snapshot(
                            {
                                'message': {
                                    'content': 'Nine',
                                    'role': 'assistant',
                                },
                                'usage': {
                                    'input_tokens': 2,
                                    'output_tokens': 3,
                                    'cache_creation_input_tokens': None,
                                    'cache_read_input_tokens': None,
                                    'server_tool_use': None,
                                    'service_tier': None,
                                },
                            }
                        )
                    ),
                    'logfire.json_schema': IsJson(
                        {
                            'type': 'object',
                            'properties': {
                                'request_data': {'type': 'object'},
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
                            },
                        }
                    ),
                },
            }
        ]
    )


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
