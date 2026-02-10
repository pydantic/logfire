from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

import openai
from openai._legacy_response import LegacyAPIResponse
from openai.lib.streaming.responses import ResponseStreamState
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion import Completion
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.images_response import ImagesResponse
from openai.types.responses import Response
from opentelemetry.trace import get_current_span

from logfire import LogfireSpan

from ...utils import handle_internal_errors, log_internal_error
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
    from openai._models import FinalRequestOptions
    from openai._types import ResponseT

    from ...main import LogfireSpan

__all__ = (
    'get_endpoint_config',
    'on_response',
    'is_async_client',
)


def get_endpoint_config(options: FinalRequestOptions, *, version: int | str = 1) -> EndpointConfig:
    """Returns the endpoint config for OpenAI depending on the url."""
    url = options.url

    json_data = options.json_data
    if not isinstance(json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        json_data = {}
    json_data = cast('dict[str, Any]', json_data)

    model = json_data.get('model')

    if url == '/chat/completions':
        if is_current_agent_span('Chat completion with {gen_ai.request.model!r}'):
            return EndpointConfig(message_template='', span_data={})

        if version == 'latest':
            span_data: dict[str, Any] = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'chat',
                REQUEST_MODEL: model,
            }
            messages: list[dict[str, Any]] = json_data.get('messages', [])
            if messages:
                input_messages, system_instructions = convert_openai_messages_to_semconv(messages)
                span_data[INPUT_MESSAGES] = input_messages
                if system_instructions:
                    span_data[SYSTEM_INSTRUCTIONS] = system_instructions
            # Minimal request_data for streaming template compatibility
            span_data['request_data'] = {'model': model}
            return EndpointConfig(
                message_template='Chat Completion with {gen_ai.request.model!r}',
                span_data=span_data,
                stream_state_cls=OpenaiChatCompletionStreamStateLatest,
            )
        else:
            span_data = {
                'request_data': json_data,
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'chat',
                REQUEST_MODEL: model,
            }
            messages = json_data.get('messages', [])
            if messages:
                input_messages, system_instructions = convert_openai_messages_to_semconv(messages)
                span_data[INPUT_MESSAGES] = input_messages
                if system_instructions:
                    span_data[SYSTEM_INSTRUCTIONS] = system_instructions
            return EndpointConfig(
                message_template='Chat Completion with {request_data[model]!r}',
                span_data=span_data,
                stream_state_cls=OpenaiChatCompletionStreamState,
            )
    elif url == '/responses':
        if is_current_agent_span('Responses API', 'Responses API with {gen_ai.request.model!r}'):
            return EndpointConfig(message_template='', span_data={})

        stream = json_data.get('stream', False)

        if version == 'latest':
            span_data = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'chat',
                REQUEST_MODEL: model,
            }
            input_msgs, sys_instructions = convert_responses_input_to_semconv(
                json_data.get('input'),
                json_data.get('instructions'),
            )
            if input_msgs:
                span_data[INPUT_MESSAGES] = input_msgs
            if sys_instructions:
                span_data[SYSTEM_INSTRUCTIONS] = sys_instructions
            # Minimal request_data for streaming template compatibility
            span_data['request_data'] = {'model': model, 'stream': stream}
            return EndpointConfig(
                message_template='Responses API with {gen_ai.request.model!r}',
                span_data=span_data,
                stream_state_cls=OpenaiResponsesStreamStateLatest,
            )
        else:
            span_data = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'chat',
                REQUEST_MODEL: model,
                'request_data': {'model': model, 'stream': stream},
                'events': inputs_to_events(
                    json_data.get('input'),
                    json_data.get('instructions'),
                ),
            }
            return EndpointConfig(
                message_template='Responses API with {request_data[model]!r}',
                span_data=span_data,
                stream_state_cls=OpenaiResponsesStreamState,
            )
    elif url == '/completions':
        if version == 'latest':
            span_data = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'text_completion',
                REQUEST_MODEL: model,
                'request_data': {'model': model},
            }
            return EndpointConfig(
                message_template='Completion with {gen_ai.request.model!r}',
                span_data=span_data,
                stream_state_cls=OpenaiCompletionStreamStateLatest,
            )
        else:
            span_data = {
                'request_data': json_data,
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'text_completion',
                REQUEST_MODEL: model,
            }
            return EndpointConfig(
                message_template='Completion with {request_data[model]!r}',
                span_data=span_data,
                stream_state_cls=OpenaiCompletionStreamState,
            )
    elif url == '/embeddings':
        if version == 'latest':
            span_data = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'embeddings',
                REQUEST_MODEL: model,
                'request_data': {'model': model},
            }
            return EndpointConfig(
                message_template='Embedding Creation with {gen_ai.request.model!r}',
                span_data=span_data,
            )
        else:
            span_data = {
                'request_data': json_data,
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'embeddings',
                REQUEST_MODEL: model,
            }
            return EndpointConfig(
                message_template='Embedding Creation with {request_data[model]!r}',
                span_data=span_data,
            )
    elif url == '/images/generations':
        if version == 'latest':
            span_data = {
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'generate_content',
                REQUEST_MODEL: model,
                'request_data': {'model': model},
            }
            return EndpointConfig(
                message_template='Image Generation with {gen_ai.request.model!r}',
                span_data=span_data,
            )
        else:
            span_data = {
                'request_data': json_data,
                PROVIDER_NAME: 'openai',
                OPERATION_NAME: 'generate_content',
                REQUEST_MODEL: model,
            }
            return EndpointConfig(
                message_template='Image Generation with {request_data[model]!r}',
                span_data=span_data,
            )
    else:
        if version == 'latest':
            span_data = {'url': url, PROVIDER_NAME: 'openai'}
            if 'model' in json_data:
                span_data[REQUEST_MODEL] = json_data['model']
                span_data['request_data'] = {'model': json_data['model']}
            else:
                span_data['request_data'] = {}
        else:
            span_data = {'request_data': json_data, 'url': url, PROVIDER_NAME: 'openai'}
            if 'model' in json_data:
                span_data[REQUEST_MODEL] = json_data['model']
        return EndpointConfig(
            message_template='OpenAI API call to {url!r}',
            span_data=span_data,
        )


def convert_openai_messages_to_semconv(
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert OpenAI messages format to OTel Gen AI Semantic Convention format.

    Returns a tuple of (input_messages, system_instructions).
    """
    input_messages: list[dict[str, Any]] = []
    system_instructions: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get('role', 'unknown')
        content = msg.get('content')

        if role == 'system':
            # System messages go to system_instructions
            if isinstance(content, str):
                system_instructions.append({'type': 'text', 'content': content})
            elif isinstance(content, list):  # pragma: no branch
                for part in cast('list[dict[str, Any] | str]', content):
                    system_instructions.append(_convert_content_part(part))
            continue

        # Build the message with parts
        parts: list[dict[str, Any]] = []

        if content is not None:
            if isinstance(content, str):
                parts.append({'type': 'text', 'content': content})
            elif isinstance(content, list):  # pragma: no branch
                for part in cast('list[dict[str, Any] | str]', content):
                    parts.append(_convert_content_part(part))

        # Handle tool calls from assistant messages
        tool_calls = msg.get('tool_calls')
        if tool_calls:
            for tc in tool_calls:
                function = tc.get('function', {})
                arguments = function.get('arguments')
                if isinstance(arguments, str):  # pragma: no branch
                    with contextlib.suppress(json.JSONDecodeError):
                        arguments = json.loads(arguments)
                parts.append(
                    {
                        'type': 'tool_call',
                        'id': tc.get('id'),
                        'name': function.get('name'),
                        'arguments': arguments,
                    }
                )

        # Handle tool message (tool response)
        tool_call_id = msg.get('tool_call_id')
        if role == 'tool' and tool_call_id:
            # For tool messages, the content is the response, not text content
            # Clear text parts and add tool_call_response instead
            parts = [p for p in parts if p.get('type') != 'text']
            parts.append(
                {
                    'type': 'tool_call_response',
                    'id': tool_call_id,
                    'response': content,
                }
            )

        input_messages.append(
            {
                'role': role,
                'parts': parts,
                **({'name': msg.get('name')} if msg.get('name') else {}),
            }
        )

    return input_messages, system_instructions


def _convert_content_part(part: dict[str, Any] | str) -> dict[str, Any]:
    """Convert a single content part to semconv format."""
    if isinstance(part, str):
        return {'type': 'text', 'content': part}

    part_type = part.get('type', 'text')
    if part_type == 'text':
        return {'type': 'text', 'content': part.get('text', '')}
    elif part_type == 'image_url':
        url = part.get('image_url', {}).get('url', '')
        return {'type': 'uri', 'modality': 'image', 'uri': url}
    elif part_type in ('input_audio', 'audio'):
        return {'type': 'blob', 'modality': 'audio', 'content': part.get('data', '')}
    else:
        # Return as generic part
        return {'type': part_type, **{k: v for k, v in part.items() if k != 'type'}}


def convert_openai_response_to_semconv(
    message: Any,
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """Convert an OpenAI response message to OTel Gen AI Semantic Convention format."""
    parts: list[dict[str, Any]] = []

    if hasattr(message, 'content') and message.content:  # pragma: no branch
        parts.append({'type': 'text', 'content': message.content})

    if hasattr(message, 'tool_calls') and message.tool_calls:
        for tc in message.tool_calls:
            function = tc.function if hasattr(tc, 'function') else tc.get('function', {})
            func_name = function.name if hasattr(function, 'name') else function.get('name')
            func_args = function.arguments if hasattr(function, 'arguments') else function.get('arguments')
            if isinstance(func_args, str):  # pragma: no branch
                with contextlib.suppress(json.JSONDecodeError):
                    func_args = json.loads(func_args)
            parts.append(
                {
                    'type': 'tool_call',
                    'id': tc.id if hasattr(tc, 'id') else tc.get('id'),
                    'name': func_name,
                    'arguments': func_args,
                }
            )

    result: dict[str, Any] = {
        'role': message.role if hasattr(message, 'role') else message.get('role', 'assistant'),
        'parts': parts,
    }
    if finish_reason:
        result['finish_reason'] = finish_reason

    return result


def convert_responses_input_to_semconv(
    inputs: str | list[dict[str, Any]] | None,
    instructions: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert Responses API inputs to semconv format.

    Returns a tuple of (input_messages, system_instructions).
    """
    input_messages: list[dict[str, Any]] = []
    system_instructions: list[dict[str, Any]] = []

    if instructions:
        system_instructions.append({'type': 'text', 'content': instructions})

    if inputs:
        if isinstance(inputs, str):
            input_messages.append(
                {
                    'role': 'user',
                    'parts': [{'type': 'text', 'content': inputs}],
                }
            )
        else:
            for inp in inputs:
                _convert_responses_input_item(inp, input_messages, system_instructions)

    return input_messages, system_instructions


def _convert_responses_input_item(
    inp: dict[str, Any],
    input_messages: list[dict[str, Any]],
    system_instructions: list[dict[str, Any]],
) -> None:
    """Convert a single Responses API input item to semconv format."""
    role = inp.get('role', 'user')
    typ = inp.get('type')
    content = inp.get('content')

    if typ == 'function_call':
        input_messages.append(
            {
                'role': 'assistant',
                'parts': [
                    {
                        'type': 'tool_call',
                        'id': inp.get('call_id'),
                        'name': inp.get('name'),
                        'arguments': inp.get('arguments'),
                    }
                ],
            }
        )
    elif typ == 'function_call_output':
        input_messages.append(
            {
                'role': 'tool',
                'parts': [
                    {
                        'type': 'tool_call_response',
                        'id': inp.get('call_id'),
                        'response': inp.get('output'),
                    }
                ],
            }
        )
    elif role and content:  # pragma: no branch
        parts: list[dict[str, Any]] = []
        if isinstance(content, str):
            parts.append({'type': 'text', 'content': content})
        elif isinstance(content, list):  # pragma: no branch
            for item in cast('list[dict[str, Any]]', content):
                if item.get('type') == 'output_text':
                    parts.append({'type': 'text', 'content': item.get('text', '')})
                elif item.get('type') == 'text':
                    parts.append({'type': 'text', 'content': item.get('text', '')})
                else:
                    parts.append(item)
        if parts:  # pragma: no branch
            input_messages.append({'role': role, 'parts': parts})


def convert_responses_outputs_to_semconv(response: Response) -> list[dict[str, Any]]:
    """Convert Responses API output to semconv format."""
    output_messages: list[dict[str, Any]] = []
    for out in response.output:
        out_dict = out.model_dump()
        typ = out_dict.get('type')
        if typ == 'message':
            content: list[dict[str, Any]] = out_dict.get('content', [])
            parts: list[dict[str, Any]] = []
            for item in content:
                if item.get('type') == 'output_text':
                    parts.append({'type': 'text', 'content': item.get('text', '')})
                else:
                    parts.append(item)
            output_messages.append(
                {
                    'role': out_dict.get('role', 'assistant'),
                    'parts': parts,
                }
            )
        elif typ == 'function_call':
            output_messages.append(
                {
                    'role': 'assistant',
                    'parts': [
                        {
                            'type': 'tool_call',
                            'id': out_dict.get('call_id'),
                            'name': out_dict.get('name'),
                            'arguments': out_dict.get('arguments'),
                        }
                    ],
                }
            )
        else:
            # Generic fallback
            output_messages.append(
                {
                    'role': 'assistant',
                    'parts': [{'type': str(typ), **{k: v for k, v in out_dict.items() if k != 'type'}}],
                }
            )
    return output_messages


def is_current_agent_span(*span_names: str):
    current_span = get_current_span()
    return (
        current_span.is_recording()
        and (instrumentation_scope := getattr(current_span, 'instrumentation_scope', None))
        and instrumentation_scope.name == 'logfire.openai_agents'
        and getattr(current_span, 'name', None) in span_names
    )


def content_from_completions(chunk: Completion | None) -> str | None:
    if chunk and chunk.choices:
        return chunk.choices[0].text
    return None  # pragma: no cover


class OpenaiCompletionStreamState(StreamState):
    def __init__(self):
        self._content: list[str] = []

    def record_chunk(self, chunk: Completion) -> None:
        content = content_from_completions(chunk)
        if content:
            self._content.append(content)

    def get_response_data(self) -> Any:
        return {'combined_chunk_content': ''.join(self._content), 'chunk_count': len(self._content)}


class OpenaiCompletionStreamStateLatest(OpenaiCompletionStreamState):
    def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
        text = ''.join(self._content)
        return {
            **span_data,
            OUTPUT_MESSAGES: [{'role': 'assistant', 'parts': [{'type': 'text', 'content': text}]}],
        }


class OpenaiResponsesStreamState(StreamState):
    def __init__(self):
        self._state = ResponseStreamState(input_tools=openai.omit, text_format=openai.omit)

    def record_chunk(self, chunk: Any) -> None:
        self._state.handle_event(chunk)

    def get_response_data(self) -> Any:
        response = self._state._completed_response  # pyright: ignore[reportPrivateUsage]
        if not response:  # pragma: no cover
            raise RuntimeError("Didn't receive a `response.completed` event.")

        return response

    def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
        response = self.get_response_data()
        span_data['events'] = span_data['events'] + responses_output_events(response)
        return span_data


class OpenaiResponsesStreamStateLatest(OpenaiResponsesStreamState):
    def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
        response = self.get_response_data()
        return {**span_data, OUTPUT_MESSAGES: convert_responses_outputs_to_semconv(response)}


try:
    # ChatCompletionStreamState only exists in openai>=1.40.0
    from openai.lib.streaming.chat._completions import ChatCompletionStreamState

    class OpenaiChatCompletionStreamState(StreamState):
        def __init__(self):
            self._stream_state = ChatCompletionStreamState()

        def record_chunk(self, chunk: ChatCompletionChunk) -> None:
            try:
                self._stream_state.handle_chunk(chunk)
            except Exception:
                pass

        def get_response_data(self) -> Any:
            try:
                final_completion = self._stream_state.current_completion_snapshot
            except AssertionError:
                # AssertionError is raised when there is no completion snapshot
                # Return empty content to show an empty Assistant response in the UI
                return {'combined_chunk_content': '', 'chunk_count': 0}
            if final_completion.choices:
                message = final_completion.choices[0].message
                message.role = 'assistant'
            else:
                message = None
            return {'message': message, 'usage': final_completion.usage}

    class OpenaiChatCompletionStreamStateLatest(OpenaiChatCompletionStreamState):
        def get_attributes(self, span_data: dict[str, Any]) -> dict[str, Any]:
            try:
                final_completion = self._stream_state.current_completion_snapshot
            except AssertionError:
                return {**span_data, OUTPUT_MESSAGES: []}
            output_messages: list[dict[str, Any]] = []
            for choice in final_completion.choices:
                output_messages.append(convert_openai_response_to_semconv(choice.message, choice.finish_reason))
            return {**span_data, OUTPUT_MESSAGES: output_messages}

except ImportError:  # pragma: no cover
    OpenaiChatCompletionStreamState = OpenaiCompletionStreamState  # type: ignore
    OpenaiChatCompletionStreamStateLatest = OpenaiCompletionStreamStateLatest  # type: ignore


@handle_internal_errors
def on_response(response: ResponseT, span: LogfireSpan, *, version: int | str = 1) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, LegacyAPIResponse):  # pragma: no cover
        on_response(response.parse(), span, version=version)  # type: ignore
        return cast('ResponseT', response)

    # Keep gen_ai.system for backward compatibility
    span.set_attribute('gen_ai.system', 'openai')

    if isinstance(response_model := getattr(response, 'model', None), str):
        span.set_attribute(RESPONSE_MODEL, response_model)

        try:
            from genai_prices import calc_price, extract_usage

            response_data = response.model_dump()  # type: ignore
            usage_data = extract_usage(
                response_data,
                provider_id='openai',
                api_flavor='responses' if isinstance(response, Response) else 'chat',
            )
            span.set_attribute(
                'operation.cost',
                float(calc_price(usage_data.usage, model_ref=response_model, provider_id='openai').total_price),
            )
        except Exception:
            pass

    # Set response ID
    response_id = getattr(response, 'id', None)
    if isinstance(response_id, str):
        span.set_attribute(RESPONSE_ID, response_id)

    usage = getattr(response, 'usage', None)
    input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', None))
    output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', None))
    if isinstance(input_tokens, int):
        span.set_attribute(INPUT_TOKENS, input_tokens)
    if isinstance(output_tokens, int):
        span.set_attribute(OUTPUT_TOKENS, output_tokens)

    if isinstance(response, ChatCompletion) and response.choices:
        output_messages: list[dict[str, Any]] = []
        finish_reasons: list[str] = []
        for choice in response.choices:
            finish_reason = choice.finish_reason
            if finish_reason:  # pragma: no branch
                finish_reasons.append(finish_reason)
            output_messages.append(convert_openai_response_to_semconv(choice.message, finish_reason))
        if finish_reasons:  # pragma: no branch
            span.set_attribute(RESPONSE_FINISH_REASONS, finish_reasons)

        if version == 'latest':
            span.set_attribute(OUTPUT_MESSAGES, output_messages)
        else:
            span.set_attribute(
                'response_data',
                {'message': response.choices[0].message, 'usage': usage},
            )
            span.set_attribute(OUTPUT_MESSAGES, output_messages)
    elif isinstance(response, Completion) and response.choices:
        finish_reasons_completion: list[str] = []
        output_messages_completion: list[dict[str, Any]] = []
        for choice in response.choices:
            finish_reason = choice.finish_reason
            if finish_reason:  # pragma: no branch
                finish_reasons_completion.append(finish_reason)
            output_messages_completion.append(
                {
                    'role': 'assistant',
                    'parts': [{'type': 'text', 'content': choice.text}],
                    'finish_reason': finish_reason,
                }
            )
        if finish_reasons_completion:  # pragma: no branch
            span.set_attribute(RESPONSE_FINISH_REASONS, finish_reasons_completion)

        if version == 'latest':
            span.set_attribute(OUTPUT_MESSAGES, output_messages_completion)
        else:
            first_choice = response.choices[0]
            span.set_attribute(
                'response_data',
                {'finish_reason': first_choice.finish_reason, 'text': first_choice.text, 'usage': usage},
            )
            span.set_attribute(OUTPUT_MESSAGES, output_messages_completion)
    elif isinstance(response, CreateEmbeddingResponse):
        if version != 'latest':
            span.set_attribute('response_data', {'usage': usage})
    elif isinstance(response, ImagesResponse):
        if version != 'latest':
            span.set_attribute('response_data', {'images': response.data})
    elif isinstance(response, Response):  # pragma: no branch
        if version == 'latest':
            span.set_attribute(OUTPUT_MESSAGES, convert_responses_outputs_to_semconv(response))
        else:
            try:
                events = json.loads(span.attributes['events'])  # type: ignore
            except Exception:
                pass
            else:
                events += responses_output_events(response)
                span.set_attribute('events', events)

    return response


def is_async_client(client: type[openai.OpenAI] | type[openai.AsyncOpenAI]):
    """Returns whether or not the `client` class is async."""
    if issubclass(client, openai.OpenAI):
        return False
    assert issubclass(client, openai.AsyncOpenAI), f'Expected OpenAI or AsyncOpenAI type, got: {client}'
    return True


@handle_internal_errors
def inputs_to_events(inputs: str | list[dict[str, Any]] | None, instructions: str | None):
    """Generate dictionaries in the style of OTel events from the inputs and instructions to the Responses API."""
    events: list[dict[str, Any]] = []
    tool_call_id_to_name: dict[str, str] = {}
    if instructions:
        events += [
            {
                'event.name': 'gen_ai.system.message',
                'content': instructions,
                'role': 'system',
            }
        ]
    if inputs:
        if isinstance(inputs, str):
            inputs = [{'role': 'user', 'content': inputs}]
        for inp in inputs:
            events += input_to_events(inp, tool_call_id_to_name)
    return events


@handle_internal_errors
def responses_output_events(response: Response):
    """Generate dictionaries in the style of OTel events from the outputs of the Responses API."""
    events: list[dict[str, Any]] = []
    for out in response.output:
        for message in input_to_events(
            out.model_dump(),
            # Outputs don't have tool call responses, so this isn't needed.
            tool_call_id_to_name={},
        ):
            events.append({**message, 'role': 'assistant'})
    return events


def input_to_events(inp: dict[str, Any], tool_call_id_to_name: dict[str, str]):
    """Generate dictionaries in the style of OTel events from one input to the Responses API.

    `tool_call_id_to_name` is a mapping from tool call IDs to function names.
    It's populated when the input is a tool call and used later to
    provide the function name in the event for tool call responses.
    """
    try:
        events: list[dict[str, Any]] = []
        role: str | None = inp.get('role')
        typ = inp.get('type')
        content = inp.get('content')
        if role and typ in (None, 'message') and content:
            event_name = f'gen_ai.{role}.message'
            if isinstance(content, str):
                events.append({'event.name': event_name, 'content': content, 'role': role})
            else:
                for content_item in content:
                    with contextlib.suppress(KeyError):
                        if content_item['type'] == 'output_text':  # pragma: no branch
                            events.append({'event.name': event_name, 'content': content_item['text'], 'role': role})
                            continue
                    events.append(unknown_event(content_item))  # pragma: no cover
        elif typ == 'function_call':
            tool_call_id_to_name[inp['call_id']] = inp['name']
            events.append(
                {
                    'event.name': 'gen_ai.assistant.message',
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': inp['call_id'],
                            'type': 'function',
                            'function': {'name': inp['name'], 'arguments': inp['arguments']},
                        },
                    ],
                }
            )
        elif typ == 'function_call_output':
            events.append(
                {
                    'event.name': 'gen_ai.tool.message',
                    'role': 'tool',
                    'id': inp['call_id'],
                    'content': inp['output'],
                    'name': tool_call_id_to_name.get(inp['call_id'], inp.get('name', 'unknown')),
                }
            )
        else:
            events.append(unknown_event(inp))
        return events
    except Exception:  # pragma: no cover
        log_internal_error()
        return [unknown_event(inp)]


def unknown_event(inp: dict[str, Any]):
    return {
        'event.name': 'gen_ai.unknown',
        'role': inp.get('role') or 'unknown',
        'content': f'{inp.get("type")}\n\nSee JSON for details',
        'data': inp,
    }
