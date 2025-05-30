from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

import openai
from openai._legacy_response import LegacyAPIResponse
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion import Completion
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.images_response import ImagesResponse
from openai.types.responses import Response
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import get_current_span

from logfire import LogfireSpan

from ...utils import handle_internal_errors, log_internal_error
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


def get_endpoint_config(options: FinalRequestOptions) -> EndpointConfig:
    """Returns the endpoint config for OpenAI depending on the url."""
    url = options.url

    json_data = options.json_data
    if not isinstance(json_data, dict):  # pragma: no cover
        # Ensure that `{request_data[model]!r}` doesn't raise an error, just a warning about `model` missing.
        json_data = {}

    if url == '/chat/completions':
        if is_current_agent_span('Chat completion with {gen_ai.request.model!r}'):
            return EndpointConfig(message_template='', span_data={})

        return EndpointConfig(
            message_template='Chat Completion with {request_data[model]!r}',
            span_data={'request_data': json_data, 'gen_ai.request.model': json_data['model']},
            stream_state_cls=OpenaiChatCompletionStreamState,
        )
    elif url == '/responses':
        if is_current_agent_span('Responses API', 'Responses API with {gen_ai.request.model!r}'):
            return EndpointConfig(message_template='', span_data={})

        return EndpointConfig(
            message_template='Responses API with {gen_ai.request.model!r}',
            span_data={
                'gen_ai.request.model': json_data['model'],
                'events': inputs_to_events(
                    json_data['input'],  # type: ignore
                    json_data.get('instructions'),  # type: ignore
                ),
            },
        )
    elif url == '/completions':
        return EndpointConfig(
            message_template='Completion with {request_data[model]!r}',
            span_data={'request_data': json_data, 'gen_ai.request.model': json_data['model']},
            stream_state_cls=OpenaiCompletionStreamState,
        )
    elif url == '/embeddings':
        return EndpointConfig(
            message_template='Embedding Creation with {request_data[model]!r}',
            span_data={'request_data': json_data, 'gen_ai.request.model': json_data['model']},
        )
    elif url == '/images/generations':
        return EndpointConfig(
            message_template='Image Generation with {request_data[model]!r}',
            span_data={'request_data': json_data, 'gen_ai.request.model': json_data['model']},
        )
    else:
        span_data: dict[str, Any] = {'request_data': json_data, 'url': url}
        if 'model' in json_data:
            span_data['gen_ai.request.model'] = json_data['model']
        return EndpointConfig(
            message_template='OpenAI API call to {url!r}',
            span_data=span_data,
        )


def is_current_agent_span(*span_names: str):
    current_span = get_current_span()
    return (
        isinstance(current_span, ReadableSpan)
        and current_span.instrumentation_scope
        and current_span.instrumentation_scope.name == 'logfire.openai_agents'
        and current_span.name in span_names
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


try:
    # ChatCompletionStreamState only exists in openai>=1.40.0
    from openai.lib.streaming.chat._completions import ChatCompletionStreamState

    class OpenaiChatCompletionStreamState(StreamState):
        def __init__(self):
            self._stream_state = ChatCompletionStreamState(
                # We do not need the response to be parsed into Python objects so can skip
                # providing the `response_format` and `input_tools` arguments.
                input_tools=openai.NOT_GIVEN,
                response_format=openai.NOT_GIVEN,
            )

        def record_chunk(self, chunk: ChatCompletionChunk) -> None:
            self._stream_state.handle_chunk(chunk)

        def get_response_data(self) -> Any:
            try:
                final_completion = self._stream_state.current_completion_snapshot
            except AssertionError:
                # AssertionError is raised when there is no completion snapshot
                # Return empty content to show an empty Assistant response in the UI
                return {'combined_chunk_content': '', 'chunk_count': 0}
            return {
                'message': final_completion.choices[0].message if final_completion.choices else None,
                'usage': final_completion.usage,
            }
except ImportError:  # pragma: no cover
    OpenaiChatCompletionStreamState = OpenaiCompletionStreamState  # type: ignore


@handle_internal_errors
def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, LegacyAPIResponse):  # pragma: no cover
        on_response(response.parse(), span)  # type: ignore
        return cast('ResponseT', response)

    span.set_attribute('gen_ai.system', 'openai')

    if isinstance(response_model := getattr(response, 'model', None), str):
        span.set_attribute('gen_ai.response.model', response_model)

    usage = getattr(response, 'usage', None)
    input_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', None))
    output_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', None))
    if isinstance(input_tokens, int):
        span.set_attribute('gen_ai.usage.input_tokens', input_tokens)
    if isinstance(output_tokens, int):
        span.set_attribute('gen_ai.usage.output_tokens', output_tokens)

    if isinstance(response, ChatCompletion) and response.choices:
        span.set_attribute(
            'response_data',
            {'message': response.choices[0].message, 'usage': usage},
        )
    elif isinstance(response, Completion) and response.choices:
        first_choice = response.choices[0]
        span.set_attribute(
            'response_data',
            {'finish_reason': first_choice.finish_reason, 'text': first_choice.text, 'usage': usage},
        )
    elif isinstance(response, CreateEmbeddingResponse):
        span.set_attribute('response_data', {'usage': usage})
    elif isinstance(response, ImagesResponse):
        span.set_attribute('response_data', {'images': response.data})
    elif isinstance(response, Response):  # pragma: no branch
        events = json.loads(span.attributes['events'])  # type: ignore
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
