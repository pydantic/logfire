from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import anthropic
from anthropic.types import Message, TextBlock, TextDelta, ToolUseBlock

from logfire._internal.utils import handle_internal_errors

from .semconv import (
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    PROVIDER_NAME,
    REQUEST_MAX_TOKENS,
    REQUEST_STOP_SEQUENCES,
    REQUEST_TEMPERATURE,
    REQUEST_TOP_K,
    REQUEST_TOP_P,
    TOOL_DEFINITIONS,
)
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


def _extract_request_parameters(json_data: dict[str, Any], span_data: dict[str, Any]) -> None:
    """Extract request parameters from json_data and add to span_data."""
    if (max_tokens := json_data.get('max_tokens')) is not None:
        span_data[REQUEST_MAX_TOKENS] = max_tokens

    if (temperature := json_data.get('temperature')) is not None:
        span_data[REQUEST_TEMPERATURE] = temperature

    if (top_p := json_data.get('top_p')) is not None:
        span_data[REQUEST_TOP_P] = top_p

    if (top_k := json_data.get('top_k')) is not None:
        span_data[REQUEST_TOP_K] = top_k

    if (stop_sequences := json_data.get('stop_sequences')) is not None:
        span_data[REQUEST_STOP_SEQUENCES] = json.dumps(stop_sequences)

    if (tools := json_data.get('tools')) is not None:
        span_data[TOOL_DEFINITIONS] = json.dumps(tools)


def get_endpoint_config(options: FinalRequestOptions) -> EndpointConfig:
    """Returns the endpoint config for Anthropic or Bedrock depending on the url."""
    url = options.url
    raw_json_data = options.json_data
    if not isinstance(raw_json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        raw_json_data = {}
    json_data = cast('dict[str, Any]', raw_json_data)

    if url == '/v1/messages':
        span_data: dict[str, Any] = {
            'request_data': json_data,
            PROVIDER_NAME: 'anthropic',
            OPERATION_NAME: 'chat',
        }
        _extract_request_parameters(json_data, span_data)

        return EndpointConfig(
            message_template='Message with {request_data[model]!r}',
            span_data=span_data,
            stream_state_cls=AnthropicMessageStreamState,
        )
    else:
        span_data = {
            'request_data': json_data,
            'url': url,
            PROVIDER_NAME: 'anthropic',
        }
        return EndpointConfig(
            message_template='Anthropic API call to {url!r}',
            span_data=span_data,
        )


def convert_anthropic_response_to_semconv(message: Message) -> dict[str, Any]:
    """Convert an Anthropic response message to OTel Gen AI Semantic Convention format."""
    parts: list[dict[str, Any]] = []

    for block in message.content:
        if isinstance(block, TextBlock):
            parts.append({'type': 'text', 'content': block.text})
        elif isinstance(block, ToolUseBlock):
            parts.append(
                {
                    'type': 'tool_call',
                    'id': block.id,
                    'name': block.name,
                    'arguments': block.input,
                }
            )
        elif hasattr(block, 'type'):  # pragma: no cover
            # Handle other block types generically
            block_dict = block.model_dump() if hasattr(block, 'model_dump') else dict(block)
            parts.append(block_dict)

    result: dict[str, Any] = {
        'role': message.role,
        'parts': parts,
    }
    if message.stop_reason:
        result['finish_reason'] = message.stop_reason

    return result


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


@handle_internal_errors
def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, Message):  # pragma: no branch
        # Keep response_data for backward compatibility
        message: dict[str, Any] = {'role': 'assistant'}
        for block in response.content:
            if block.type == 'text':
                message['content'] = block.text
            elif block.type == 'tool_use':  # pragma: no branch
                message.setdefault('tool_calls', []).append(
                    {
                        'id': block.id,
                        'function': {
                            'arguments': block.model_dump_json(include={'input'}),
                            'name': block.name,
                        },
                    }
                )
        span.set_attribute('response_data', {'message': message, 'usage': response.usage})

        # Add semantic convention output messages
        output_message = convert_anthropic_response_to_semconv(response)
        span.set_attribute(OUTPUT_MESSAGES, [output_message])

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
