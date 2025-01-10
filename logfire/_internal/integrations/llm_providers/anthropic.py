from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
from anthropic.types import Message, TextBlock, TextDelta

from .types import EndpointConfig, StreamState

if TYPE_CHECKING:
    from anthropic._models import FinalRequestOptions
    from anthropic._types import ResponseT

    from ...main import LogfireSpan

__all__ = (
    'get_endpoint_config',
    'on_response',
    'is_async_client',
)


def get_endpoint_config(options: FinalRequestOptions) -> EndpointConfig:
    """Returns the endpoint config for Anthropic or Bedrock depending on the url."""
    url = options.url
    json_data = options.json_data
    if not isinstance(json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        json_data = {}

    if url == '/v1/messages':
        return EndpointConfig(
            message_template='Message with {request_data[model]!r}',
            span_data={'request_data': json_data},
            stream_state_cls=AnthropicMessageStreamState,
        )
    else:
        return EndpointConfig(
            message_template='Anthropic API call to {url!r}',
            span_data={'request_data': json_data, 'url': url},
        )


def content_from_messages(chunk: anthropic.types.MessageStreamEvent) -> str | None:
    if hasattr(chunk, 'content_block'):
        return chunk.content_block.text if isinstance(chunk.content_block, TextBlock) else None  # type: ignore
    if hasattr(chunk, 'delta'):
        return chunk.delta.text if isinstance(chunk.delta, TextDelta) else None  # type: ignore
    return None


class AnthropicMessageStreamState(StreamState):
    def __init__(self):
        self._content: list[str] = []

    def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
        content = content_from_messages(chunk)
        if content:
            self._content.append(content)

    def get_response_data(self) -> Any:
        return {'combined_chunk_content': ''.join(self._content), 'chunk_count': len(self._content)}


def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, Message):  # pragma: no branch
        block = response.content[0]
        message: dict[str, Any] = {'role': 'assistant'}
        if block.type == 'text':
            message['content'] = block.text
        else:
            message['tool_calls'] = [
                {
                    'function': {
                        'arguments': block.model_dump_json(include={'input'}),
                        'name': block.name,  # type: ignore
                    }
                }
                for block in response.content
            ]
        span.set_attribute('response_data', {'message': message, 'usage': response.usage})
    return response


def is_async_client(
    client: type[anthropic.Anthropic]
    | type[anthropic.AsyncAnthropic]
    | type[anthropic.AnthropicBedrock]
    | type[anthropic.AsyncAnthropicBedrock],
):
    """Returns whether or not the `client` class is async."""
    if issubclass(client, (anthropic.Anthropic, anthropic.AnthropicBedrock)):
        return False
    assert issubclass(client, (anthropic.AsyncAnthropic, anthropic.AsyncAnthropicBedrock)), (
        f'Expected Anthropic, AsyncAnthropic, AnthropicBedrock or AsyncAnthropicBedrock type, got: {client}'
    )
    return True
