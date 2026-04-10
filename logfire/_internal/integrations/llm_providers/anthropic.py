from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

import anthropic
import httpx
from anthropic.types import Message, TextBlock, TextDelta, ToolUseBlock
from anthropic.types.beta import BetaMessage, BetaTextBlock, BetaTextDelta, BetaToolUseBlock

from logfire._internal.utils import handle_internal_errors

from .semconv import (
    INPUT_MESSAGES,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    REQUEST_MAX_TOKENS,
    REQUEST_MODEL,
    REQUEST_STOP_SEQUENCES,
    REQUEST_TEMPERATURE,
    REQUEST_TOP_K,
    REQUEST_TOP_P,
    RESPONSE_FINISH_REASONS,
    RESPONSE_ID,
    RESPONSE_MODEL,
    SYSTEM_INSTRUCTIONS,
    TOOL_DEFINITIONS,
    BlobPart,
    ChatMessage,
    InputMessages,
    MessagePart,
    OutputMessage,
    SemconvVersion,
    SystemInstructions,
    TextPart,
    ToolCallPart,
    ToolCallResponsePart,
    UriPart,
    provider_attrs,
)
from .types import EndpointConfig, StreamState
from .usage import get_usage_attributes

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


def _versioned_stream_cls(base_cls: type[StreamState], versions: frozenset[SemconvVersion]) -> type[StreamState]:
    """Create a version-aware stream state subclass."""

    class VersionedStreamState(base_cls):
        _versions = versions

    return VersionedStreamState


def get_endpoint_config(
    options: FinalRequestOptions, *, version: SemconvVersion | frozenset[SemconvVersion] = 1
) -> EndpointConfig:
    """Returns the endpoint config for Anthropic or Bedrock depending on the url."""
    versions: frozenset[SemconvVersion] = version if isinstance(version, frozenset) else frozenset({version})
    url = options.url
    raw_json_data = options.json_data
    if not isinstance(raw_json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        raw_json_data = {}
    json_data = cast('dict[str, Any]', raw_json_data)
    model = json_data.get('model')
    request_data = json_data if 1 in versions else {'model': model}

    common_attrs = {'request_data': request_data, **provider_attrs('anthropic')}
    if model:  # pragma: no branch
        common_attrs[REQUEST_MODEL] = model

    if url in ('/v1/messages', '/v1/messages?beta=true'):
        span_data: dict[str, Any] = {**common_attrs, OPERATION_NAME: 'chat'}
        _extract_request_parameters(json_data, span_data)

        if 'latest' in versions:
            # Convert messages to semantic convention format
            messages: list[dict[str, Any]] = json_data.get('messages', [])
            system: str | list[dict[str, Any]] | None = json_data.get('system')
            if messages or system:
                input_messages, system_instructions = convert_messages_to_semconv(messages, system)
                span_data[INPUT_MESSAGES] = input_messages
                if system_instructions:
                    span_data[SYSTEM_INSTRUCTIONS] = system_instructions

        return EndpointConfig(
            message_template='Message with {request_data[model]!r}',
            span_data=span_data,
            stream_state_cls=_versioned_stream_cls(AnthropicMessageStreamState, versions),
        )
    else:
        return EndpointConfig(
            message_template='Anthropic API call to {url!r}',
            span_data={'url': url, **common_attrs},
        )


def _convert_content_part_or_parts(content: object) -> list[MessagePart]:
    if not content:
        return []

    if isinstance(content, list):
        return [_convert_content_part(part) for part in cast(list[Any], content)]
    else:
        return [_convert_content_part(content)]


def _convert_content_part(part: object) -> MessagePart:  # pragma: no cover
    """Convert a single Anthropic content part to semconv format."""
    if not isinstance(part, dict):
        return TextPart(type='text', content=str(part))

    part = cast('dict[str, Any]', part)
    part_type = part.get('type', 'text')
    if part_type == 'text':
        return TextPart(type='text', content=part.get('text', ''))
    elif part_type == 'image':  # pragma: no cover
        source = part.get('source', {})
        if source.get('type') == 'base64':
            blob_part = BlobPart(
                type='blob',
                modality='image',
                content=source.get('data', ''),
            )
            if (media_type := source.get('media_type')) is not None:
                blob_part['media_type'] = media_type
            return blob_part
        elif source.get('type') == 'url':
            return UriPart(type='uri', uri=source.get('url', ''), modality='image')
        else:
            return {'type': 'image', **part}
    elif part_type == 'tool_use':
        return make_tool_call_part(
            tool_call_id=part.get('id', ''),
            name=part.get('name', ''),
            arguments=part.get('input'),
        )
    elif part_type == 'tool_result':  # pragma: no cover
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
        return ToolCallResponsePart(
            type='tool_call_response',
            id=part.get('tool_use_id', ''),
            response=result_text,
        )
    else:  # pragma: no cover
        # Return as generic dict for unknown types
        return {**part, 'type': part_type}


def make_tool_call_part(
    tool_call_id: str,
    name: str,
    arguments: Any,
) -> ToolCallPart:
    """Helper function to create a ToolCallPart."""
    if isinstance(arguments, str):  # pragma: no cover
        with contextlib.suppress(json.JSONDecodeError):
            arguments = json.loads(arguments)
    return ToolCallPart(
        type='tool_call',
        id=tool_call_id,
        name=name,
        arguments=arguments,
    )


def convert_messages_to_semconv(
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]] | None = None,
) -> tuple[InputMessages, SystemInstructions]:
    """Convert Anthropic messages format to OTel Gen AI Semantic Convention format.

    Returns a tuple of (input_messages, system_instructions).
    """
    system_instructions: SystemInstructions = _convert_content_part_or_parts(system)

    input_messages: InputMessages = [
        ChatMessage(
            role=msg.get('role') or 'user',
            parts=_convert_content_part_or_parts(msg.get('content')),
        )
        for msg in messages
    ]

    return input_messages, system_instructions


def convert_response_to_semconv(message: Message | BetaMessage) -> OutputMessage:
    """Convert an Anthropic response message to OTel Gen AI Semantic Convention format."""
    parts: list[MessagePart] = []

    for block in message.content:
        if isinstance(block, (TextBlock, BetaTextBlock)):
            parts.append(TextPart(type='text', content=block.text))
        elif isinstance(block, (ToolUseBlock, BetaToolUseBlock)):
            parts.append(
                make_tool_call_part(
                    tool_call_id=block.id,
                    name=block.name,
                    arguments=block.input,
                )
            )
        elif hasattr(block, 'type'):  # pragma: no cover
            # Handle other block types generically
            block_dict = block.model_dump() if hasattr(block, 'model_dump') else dict(block)
            parts.append(block_dict)

    result = OutputMessage(
        role=message.role,
        parts=parts,
    )
    if message.stop_reason:
        result['finish_reason'] = message.stop_reason

    return result


class AnthropicMessageStreamState(StreamState):
    _versions: frozenset[SemconvVersion] = frozenset({1})

    def __init__(self):
        self._message: Any = None
        self._chunk_count: int = 0

    def record_chunk(self, chunk: anthropic.types.MessageStreamEvent) -> None:
        from anthropic.lib.streaming._beta_messages import accumulate_event as beta_accumulate_event
        from anthropic.lib.streaming._messages import accumulate_event

        if type(chunk).__module__.startswith('anthropic.types.beta'):
            self._message = beta_accumulate_event(
                event=cast(Any, chunk), current_snapshot=self._message, request_headers=httpx.Headers()
            )
        else:
            self._message = accumulate_event(event=chunk, current_snapshot=self._message)
        if isinstance(getattr(chunk, 'delta', None), (TextDelta, BetaTextDelta)):
            self._chunk_count += 1

    def get_response_data(self) -> Any:
        if self._message is None:
            return {'combined_chunk_content': '', 'chunk_count': 0}
        texts = [block.text for block in self._message.content if isinstance(block, (TextBlock, BetaTextBlock))]
        return {'combined_chunk_content': ''.join(texts), 'chunk_count': self._chunk_count}

    def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
        versions = self._versions
        result = dict(**span_data)
        if 1 in versions:
            result['response_data'] = self.get_response_data()
        if 'latest' in versions and self._message and self._message.content:
            result[OUTPUT_MESSAGES] = [convert_response_to_semconv(self._message)]
        if self._message is not None:
            result.update(get_anthropic_usage_attributes(self._message))
        return result


def get_anthropic_usage_attributes(response: Any) -> dict[str, Any]:
    """Extract usage attributes from an Anthropic response object.

    Works for Message and BetaMessage from non-streaming on_response().
    Returns an empty dict when usage is None.
    """
    usage = getattr(response, 'usage', None)
    if usage is None:
        return {}
    input_tokens = usage.input_tokens + (usage.cache_read_input_tokens or 0) + (usage.cache_creation_input_tokens or 0)
    output_tokens = usage.output_tokens
    return get_usage_attributes(response, usage, input_tokens, output_tokens, provider_id='anthropic')


@handle_internal_errors
def on_response(
    response: ResponseT, span: LogfireSpan, *, version: SemconvVersion | frozenset[SemconvVersion] = 1
) -> ResponseT:
    """Updates the span based on the type of response."""
    versions: frozenset[SemconvVersion] = version if isinstance(version, frozenset) else frozenset({version})

    if isinstance(response, (Message, BetaMessage)):
        if 1 in versions:
            message: dict[str, Any] = {'role': 'assistant'}
            for block in response.content:
                if block.type == 'text':
                    message['content'] = block.text
                elif block.type == 'tool_use':
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

        if 'latest' in versions:
            output_message = convert_response_to_semconv(response)
            span.set_attribute(OUTPUT_MESSAGES, [output_message])

        # Always set scalar semconv attributes
        span.set_attribute(RESPONSE_MODEL, response.model)
        span.set_attribute(RESPONSE_ID, response.id)

        span.set_attributes(get_anthropic_usage_attributes(response))

        if response.stop_reason:
            span.set_attribute(RESPONSE_FINISH_REASONS, [response.stop_reason])

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
