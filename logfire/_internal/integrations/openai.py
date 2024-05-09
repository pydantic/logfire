from __future__ import annotations

from contextlib import contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Callable,
    ContextManager,
    Generic,
    Iterator,
    NamedTuple,
    TypeVar,
    cast,
)

import openai
from openai._legacy_response import LegacyAPIResponse
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.completion import Completion
from openai.types.create_embedding_response import CreateEmbeddingResponse
from openai.types.images_response import ImagesResponse
from opentelemetry import context

from ..constants import ONE_SECOND_IN_NANOSECONDS
from ..stack_info import get_user_stack_offset

if TYPE_CHECKING:
    from openai._models import FinalRequestOptions
    from openai._streaming import AsyncStream, Stream
    from openai._types import ResponseT
    from typing_extensions import LiteralString, TypedDict, Unpack

    from ..main import Logfire, LogfireSpan

    # The following typevars are used to use a generic type in the `OpenAIRequest` TypedDict for the sync and async flavors
    _AsyncStreamT = TypeVar('_AsyncStreamT', bound=AsyncStream[Any])
    _StreamT = TypeVar('_StreamT', bound=Stream[Any])

    _ResponseType = TypeVar('_ResponseType')
    _StreamType = TypeVar('_StreamType')

    class OpenAIRequest(TypedDict, Generic[_ResponseType, _StreamType]):
        cast_to: type[_ResponseType]
        options: FinalRequestOptions
        remaining_retries: int | None
        stream: bool
        stream_cls: type[_StreamType] | None


__all__ = ('instrument_openai',)


def instrument_openai(
    logfire: Logfire, client: openai.OpenAI | openai.AsyncOpenAI, suppress_otel: bool
) -> ContextManager[None]:
    logfire_openai = logfire.with_settings(custom_scope_suffix='openai')

    client._is_instrumented_by_logfire = True  # type: ignore

    if isinstance(client, openai.OpenAI):
        instrument_openai_sync(logfire_openai, client, suppress_otel)
    else:
        assert isinstance(client, openai.AsyncOpenAI), f'Unexpected OpenAI or AsyncOpenAI type, got: {client}'
        instrument_openai_async(logfire_openai, client, suppress_otel)

    @contextmanager
    def uninstrument_context():
        """Context manager to remove instrumentation from the OpenAI client.

        The user isn't required (or even expected) to use this context manager,
        which is why the instrumenting has already happened before.
        It exists mostly for tests, and just in case users want it.
        """
        try:
            yield
        finally:
            client._request = client._original_request_method  # type: ignore
            del client._original_request_method  # type: ignore
            client._is_instrumented_by_logfire = False  # type: ignore

    return uninstrument_context()


STEAMING_MSG_TEMPLATE: LiteralString = 'streaming response from {request_data[model]!r} took {duration:.2f}s'


def instrument_openai_sync(logfire_openai: Logfire, openai_client: openai.OpenAI, suppress_otel: bool) -> None:
    # WARNING: this method is vey similar to `instrument_openai_async` below, any changes here should be reflected there
    openai_client._original_request_method = original_request_method = openai_client._request  # type: ignore

    def instrumented_openai_request(**kwargs: Unpack[OpenAIRequest[ResponseT, _StreamT]]) -> ResponseT | _StreamT:
        if context.get_value('suppress_instrumentation'):
            return original_request_method(**kwargs)

        options = kwargs['options']
        try:
            message_template, span_data, content_from_stream = get_endpoint_config(options)
        except ValueError as exc:
            logfire_openai.warn('Unable to instrument OpenAI API call: {error}', error=str(exc), kwargs=kwargs)
            return original_request_method(**kwargs)

        span_data['async'] = False
        stream = kwargs['stream']

        if stream and content_from_stream:
            stream_cls = kwargs['stream_cls']
            assert stream_cls is not None, 'Expected `stream_cls` when streaming'

            class LogfireInstrumentedStream(stream_cls):
                def __stream__(self) -> Iterator[Any]:
                    with record_streaming(logfire_openai, span_data, content_from_stream) as record_chunk:
                        for chunk in super().__stream__():
                            record_chunk(chunk)
                            yield chunk

            kwargs['stream_cls'] = LogfireInstrumentedStream  # type: ignore

        # The stack offset is increased by 1 because of this function call.
        user_stack_offset = get_user_stack_offset() + 1
        with logfire_openai.span(message_template, _stack_offset=user_stack_offset, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return original_request_method(**kwargs)
                else:
                    response = on_response(original_request_method(**kwargs), span)
                    return response

    openai_client._request = instrumented_openai_request  # type: ignore


def instrument_openai_async(logfire_openai: Logfire, openai_client: openai.AsyncOpenAI, suppress_otel: bool) -> None:
    # WARNING: this method is vey similar to `instrument_openai_sync` above, any changes here should be reflected there
    openai_client._original_request_method = original_request_method = openai_client._request  # type: ignore

    async def instrumented_openai_request(
        **kwargs: Unpack[OpenAIRequest[ResponseT, _AsyncStreamT]],
    ) -> ResponseT | _AsyncStreamT:
        if context.get_value('suppress_instrumentation'):
            return await original_request_method(**kwargs)

        options = kwargs['options']
        try:
            message_template, span_data, content_from_stream = get_endpoint_config(options)
        except ValueError as exc:
            logfire_openai.warn('Unable to instrument OpenAI API call: {error}', error=str(exc), kwargs=kwargs)
            return await original_request_method(**kwargs)

        span_data['async'] = True
        stream = kwargs['stream']

        if stream and content_from_stream:
            stream_cls = kwargs['stream_cls']
            assert stream_cls is not None, 'Expected `stream_cls` when streaming'

            class LogfireInstrumentedStream(stream_cls):
                async def __stream__(self) -> AsyncIterator[Any]:
                    with record_streaming(logfire_openai, span_data, content_from_stream) as record_chunk:
                        async for chunk in super().__stream__():
                            record_chunk(chunk)
                            yield chunk

            kwargs['stream_cls'] = LogfireInstrumentedStream  # type: ignore

        # The stack offset is increased by 1 because of this function call.
        user_stack_offset = get_user_stack_offset() + 1
        with logfire_openai.span(message_template, _stack_offset=user_stack_offset, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return await original_request_method(**kwargs)
                else:
                    response = on_response(await original_request_method(**kwargs), span)
                    return response

    openai_client._request = instrumented_openai_request  # type: ignore


class EndpointConfig(NamedTuple):
    message_template: LiteralString
    span_data: dict[str, Any]
    content_from_stream: Callable[[Any], str | None] | None


def get_endpoint_config(options: FinalRequestOptions) -> EndpointConfig:
    url = options.url
    json_data = options.json_data
    if not isinstance(json_data, dict):
        raise ValueError('Expected `options.json_data` to be a dictionary')
    if 'model' not in json_data:
        # all OpenAI API calls have a model AFAIK
        raise ValueError('`model` not found in request data')

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
        raise ValueError(f'Unknown OpenAI API endpoint: `{url}`')


def content_from_completions(chunk: Completion | None) -> str | None:
    if chunk and chunk.choices:
        return chunk.choices[0].text
    return None  # pragma: no cover


def content_from_chat_completions(chunk: ChatCompletionChunk | None) -> str | None:
    if chunk and chunk.choices:
        return chunk.choices[0].delta.content
    return None


def on_response(response: ResponseT, span: LogfireSpan) -> ResponseT:
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


@contextmanager
def maybe_suppress_instrumentation(suppress: bool) -> Iterator[None]:
    if suppress:
        new_context = context.set_value('suppress_instrumentation', True)
        token = context.attach(new_context)
        try:
            yield
        finally:
            context.detach(token)
    else:
        yield


@contextmanager
def record_streaming(
    logfire_openai: Logfire,
    span_data: dict[str, Any],
    content_from_stream: Callable[[Any], str | None],
):
    content: list[str] = []

    def record_chunk(chunk: Any) -> Any:
        chunk_content = content_from_stream(chunk)
        if chunk_content is not None:
            content.append(chunk_content)

    timer = logfire_openai._config.ns_timestamp_generator  # type: ignore
    start = timer()
    try:
        yield record_chunk
    finally:
        duration = (timer() - start) / ONE_SECOND_IN_NANOSECONDS
        # We need to subtract 2 from the stack offset, because the `logfire_openai.log` adds 2 to the stack offset.
        user_stack_offset = get_user_stack_offset() - 2
        logfire_openai.log(
            'info',
            STEAMING_MSG_TEMPLATE,
            stack_offset=user_stack_offset,
            attributes=dict(
                **span_data,
                duration=duration,
                response_data={'combined_chunk_content': ''.join(content), 'chunk_count': len(content)},
            ),
        )
