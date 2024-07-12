from __future__ import annotations

from typing import TYPE_CHECKING, cast

import openai
from openai._legacy_response import LegacyAPIResponse
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion import Completion
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.images_response import ImagesResponse

from .types import EndpointConfig

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
            content_from_stream=content_from_chat_completions,
        )
    elif url == '/completions':
        return EndpointConfig(
            message_template='Completion with {request_data[model]!r}',
            span_data={'request_data': json_data},
            content_from_stream=content_from_completions,
        )
    elif url == '/embeddings':
        return EndpointConfig(
            message_template='Embedding Creation with {request_data[model]!r}',
            span_data={'request_data': json_data},
            content_from_stream=None,
        )
    elif url == '/images/generations':
        return EndpointConfig(
            message_template='Image Generation with {request_data[model]!r}',
            span_data={'request_data': json_data},
            content_from_stream=None,
        )
    else:
        return EndpointConfig(
            message_template='OpenAI API call to {url!r}',
            span_data={'request_data': json_data, 'url': url},
            content_from_stream=None,
        )


def content_from_completions(chunk: Completion | None) -> str | None:
    if chunk and chunk.choices:
        return chunk.choices[0].text
    return None  # pragma: no cover


def content_from_chat_completions(chunk: ChatCompletionChunk | None) -> str | None:
    if chunk and chunk.choices:
        return chunk.choices[0].delta.content
    return None


def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
    """Updates the span based on the type of response."""
    if isinstance(response, LegacyAPIResponse):  # pragma: no cover
        on_response(response.parse(), span)  # type: ignore
        return cast('ResponseT', response)

    if isinstance(response, ChatCompletion):
        span.set_attribute(
            'response_data',
            {'message': response.choices[0].message, 'usage': response.usage},
        )
    elif isinstance(response, Completion):
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
