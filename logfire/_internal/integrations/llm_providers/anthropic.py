from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
from anthropic.types import Message, RawContentBlockDeltaEvent, RawContentBlockStartEvent, TextBlock, TextDelta

from .types import EndpointConfig

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
    """Returns the endpoint config for Anthropic depending on the url."""
    url = options.url
    json_data = options.json_data
    if not isinstance(json_data, dict):
        raise ValueError('Expected `options.json_data` to be a dictionary')

    if url == '/v1/messages':
        return EndpointConfig(
            message_template='Message with {request_data[model]!r}',
            span_data={'request_data': json_data},
            content_from_stream=content_from_messages,
        )
    else:
        raise ValueError(f'Unknown Anthropic API endpoint: `{url}`')


def content_from_messages(chunk: anthropic.types.MessageStreamEvent) -> str | None:
    if isinstance(chunk, RawContentBlockStartEvent):
        return chunk.content_block.text if isinstance(chunk.content_block, TextBlock) else ''
    if isinstance(chunk, RawContentBlockDeltaEvent):
        return chunk.delta.text if isinstance(chunk.delta, TextDelta) else ''
    return None


def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, Message):  # pragma: no branch
        block = response.content[0]
        message: dict[str, Any] = {'role': 'assistant'}
        if isinstance(block, TextBlock):
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


def is_async_client(client: type[anthropic.Anthropic] | type[anthropic.AsyncAnthropic]):
    """Returns whether or not the `client` class is async."""
    if issubclass(client, anthropic.Anthropic):
        return False
    assert issubclass(client, anthropic.AsyncAnthropic), f'Expected Anthropic or AsyncAnthropic type, got: {client}'
    return True
