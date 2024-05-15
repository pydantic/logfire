from __future__ import annotations

from typing import TYPE_CHECKING, Any

import anthropic
from anthropic.types import ContentBlockDeltaEvent, ContentBlockStartEvent, Message
from anthropic.types.beta.tools import ToolsBetaMessage

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

    if url == '/v1/messages' or url == '/v1/messages?beta=tools':
        # Note: this enables the UI to display the system message; however, it also shows
        # the system message in the messages array, which isn't actually what's being sent.
        # Likely better to enable the UI separately so the request data actually matches
        # what is sent but the system message still shows up pretty in the UI.
        request_data = json_data.copy()  # type: ignore
        system_message = {'role': 'system', 'content': request_data['system']}  # type: ignore
        request_data['messages'] = [system_message] + request_data['messages']
        return EndpointConfig(
            message_template='Message with {request_data[model]!r}',
            span_data={'request_data': request_data},
            content_from_stream=content_from_messages,
        )
    else:
        raise ValueError(f'Unknown Anthropic API endpoint: `{url}`')


def content_from_messages(chunk: anthropic.types.MessageStreamEvent) -> str | None:
    if isinstance(chunk, ContentBlockStartEvent):
        return chunk.content_block.text
    if isinstance(chunk, ContentBlockDeltaEvent):
        return chunk.delta.text
    return None


def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, (Message, ToolsBetaMessage)):
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


def is_async_client(client: anthropic.Anthropic | anthropic.AsyncAnthropic):
    """Returns whether or not `client` is async."""
    if isinstance(client, anthropic.Anthropic):
        return False
    assert isinstance(client, anthropic.AsyncAnthropic), f'Unexpected Anthropic or AsyncAnthropic type, got: {client}'
    return True
