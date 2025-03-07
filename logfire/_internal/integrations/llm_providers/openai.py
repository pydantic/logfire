from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import openai
from openai._legacy_response import LegacyAPIResponse
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion import Completion
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.images_response import ImagesResponse

from ...utils import handle_internal_errors
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
        return EndpointConfig(
            message_template='Chat Completion with {request_data[model]!r}',
            span_data={'request_data': json_data},
            stream_state_cls=OpenaiChatCompletionStreamState,
        )
    elif url == '/completions':
        return EndpointConfig(
            message_template='Completion with {request_data[model]!r}',
            span_data={'request_data': json_data},
            stream_state_cls=OpenaiCompletionStreamState,
        )
    elif url == '/embeddings':
        return EndpointConfig(
            message_template='Embedding Creation with {request_data[model]!r}',
            span_data={'request_data': json_data},
        )
    elif url == '/images/generations':
        return EndpointConfig(
            message_template='Image Generation with {request_data[model]!r}',
            span_data={'request_data': json_data},
        )
    else:
        return EndpointConfig(
            message_template='OpenAI API call to {url!r}',
            span_data={'request_data': json_data, 'url': url},
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

    if isinstance(response, ChatCompletion) and response.choices:
        span.set_attribute(
            'response_data',
            {'message': response.choices[0].message, 'usage': response.usage},
        )
    elif isinstance(response, Completion) and response.choices:
        first_choice = response.choices[0]
        span.set_attribute(
            'response_data',
            {'finish_reason': first_choice.finish_reason, 'text': first_choice.text, 'usage': response.usage},
        )
    elif isinstance(response, CreateEmbeddingResponse):
        span.set_attribute('response_data', {'usage': response.usage})
    elif isinstance(response, ImagesResponse):  # pragma: no branch
        span.set_attribute('response_data', {'images': response.data})
    return response


def is_async_client(client: type[openai.OpenAI] | type[openai.AsyncOpenAI]):
    """Returns whether or not the `client` class is async."""
    if issubclass(client, openai.OpenAI):
        return False
    assert issubclass(client, openai.AsyncOpenAI), f'Expected OpenAI or AsyncOpenAI type, got: {client}'
    return True
