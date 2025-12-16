from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import anthropic
from anthropic.types import Message, TextBlock, TextDelta, ToolUseBlock

from logfire._internal.utils import handle_internal_errors

from .semconv import (
    INPUT_MESSAGES,
    INPUT_TOKENS,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    OUTPUT_TOKENS,
    PROVIDER_NAME,
    REQUEST_MODEL,
    RESPONSE_FINISH_REASONS,
    RESPONSE_ID,
    RESPONSE_MODEL,
    SYSTEM_INSTRUCTIONS,
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


def get_endpoint_config(options: FinalRequestOptions) -> EndpointConfig:
    """Returns the endpoint config for Anthropic or Bedrock depending on the url."""
    url = options.url
    json_data = options.json_data
    if not isinstance(json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        json_data = {}
    json_data = cast('dict[str, Any]', json_data)

    if url == '/v1/messages':
        span_data: dict[str, Any] = {
            'request_data': json_data,
            PROVIDER_NAME: 'anthropic',
            OPERATION_NAME: 'chat',
            REQUEST_MODEL: json_data.get('model'),
        }

        # Convert messages to semantic convention format
        messages: list[dict[str, Any]] = json_data.get('messages', [])
        system: str | list[dict[str, Any]] | None = json_data.get('system')
        if messages or system:
            input_messages, system_instructions = convert_anthropic_messages_to_semconv(messages, system)
            span_data[INPUT_MESSAGES] = input_messages
            if system_instructions:
                span_data[SYSTEM_INSTRUCTIONS] = system_instructions

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
        if 'model' in json_data:
            span_data[REQUEST_MODEL] = json_data['model']
        return EndpointConfig(
            message_template='Anthropic API call to {url!r}',
            span_data=span_data,
        )


def convert_anthropic_messages_to_semconv(
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert Anthropic messages format to OTel Gen AI Semantic Convention format.

    Returns a tuple of (input_messages, system_instructions).
    """
    input_messages: list[dict[str, Any]] = []
    system_instructions: list[dict[str, Any]] = []

    # Handle system parameter (Anthropic uses a separate 'system' parameter)
    if system:
        if isinstance(system, str):
            system_instructions.append({'type': 'text', 'content': system})
        else:
            for part in system:
                if part.get('type') == 'text':
                    system_instructions.append({'type': 'text', 'content': part.get('text', '')})
                else:
                    system_instructions.append(part)

    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content')

        parts: list[dict[str, Any]] = []

        if content is not None:
            if isinstance(content, str):
                parts.append({'type': 'text', 'content': content})
            elif isinstance(content, list):
                for part in cast('list[dict[str, Any] | str]', content):
                    parts.append(_convert_anthropic_content_part(part))

        input_messages.append(
            {
                'role': role,
                'parts': parts,
            }
        )

    return input_messages, system_instructions


def _convert_anthropic_content_part(part: dict[str, Any] | str) -> dict[str, Any]:
    """Convert a single Anthropic content part to semconv format."""
    if isinstance(part, str):
        return {'type': 'text', 'content': part}

    part_type = part.get('type', 'text')
    if part_type == 'text':
        return {'type': 'text', 'content': part.get('text', '')}
    elif part_type == 'image':
        source = part.get('source', {})
        if source.get('type') == 'base64':
            return {
                'type': 'blob',
                'modality': 'image',
                'content': source.get('data', ''),
                'media_type': source.get('media_type'),
            }
        elif source.get('type') == 'url':
            return {'type': 'uri', 'modality': 'image', 'uri': source.get('url', '')}
        else:
            return {'type': 'image', **part}
    elif part_type == 'tool_use':
        return {
            'type': 'tool_call',
            'id': part.get('id'),
            'name': part.get('name'),
            'arguments': part.get('input'),
        }
    elif part_type == 'tool_result':
        result_content = part.get('content')
        if isinstance(result_content, list):
            # Extract text from tool result content
            text_parts: list[str] = []
            for p in cast('list[dict[str, Any] | str]', result_content):
                if isinstance(p, dict) and p.get('type') == 'text':
                    text_parts.append(str(p.get('text', '')))
                elif isinstance(p, str):
                    text_parts.append(p)
            result_text = ' '.join(text_parts)
        else:
            result_text = str(result_content) if result_content else ''
        return {
            'type': 'tool_call_response',
            'id': part.get('tool_use_id'),
            'response': result_text,
        }
    else:
        # Return as generic part
        return {'type': part_type, **{k: v for k, v in part.items() if k != 'type'}}


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
        elif hasattr(block, 'type'):
            # Handle other block types generically
            block_dict = block.model_dump() if hasattr(block, 'model_dump') else dict(block)
            parts.append(_convert_anthropic_content_part(block_dict))

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
                        'function': {
                            'arguments': block.model_dump_json(include={'input'}),
                            'name': block.name,
                        }
                    }
                )
        span.set_attribute('response_data', {'message': message, 'usage': response.usage})

        # Add semantic convention attributes
        span.set_attribute(RESPONSE_MODEL, response.model)
        span.set_attribute(RESPONSE_ID, response.id)

        # Add token usage
        if response.usage:
            span.set_attribute(INPUT_TOKENS, response.usage.input_tokens)
            span.set_attribute(OUTPUT_TOKENS, response.usage.output_tokens)

        # Add finish reason
        if response.stop_reason:
            span.set_attribute(RESPONSE_FINISH_REASONS, [response.stop_reason])

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
