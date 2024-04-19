from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, ContextManager, Iterator, NamedTuple

import openai
from opentelemetry import context

if TYPE_CHECKING:
    from openai._models import FinalRequestOptions
    from openai._streaming import AsyncStream, Stream
    from openai.types.chat.chat_completion import ChatCompletion
    from openai.types.completion import Completion
    from openai.types.create_embedding_response import CreateEmbeddingResponse
    from openai.types.images_response import ImagesResponse
    from typing_extensions import LiteralString

    from ..main import Logfire, LogfireSpan


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


STEAMING_MSG_TEMPLATE: LiteralString = 'streaming response from {request_data[model]!r}'


def instrument_openai_sync(logfire_openai: Logfire, openai_client: openai.OpenAI, suppress_otel: bool) -> None:
    # WARNING: this method is vey similar to `instrument_openai_async` below, any changes here should be reflected there
    openai_client._original_request_method = original_request_method = openai_client._request  # type: ignore

    def instrumented_openai_request(**kwargs: Any) -> Any:
        if context.get_value('suppress_instrumentation'):
            return original_request_method(**kwargs)

        options: FinalRequestOptions | None = kwargs.get('options')
        try:
            message_template, span_data, on_response, content_from_stream = get_endpoint_config(options)
        except ValueError as exc:
            logfire_openai.warn('Unable to instrument OpenAI API call: {error}', error=str(exc), kwargs=kwargs)
            return original_request_method(**kwargs)

        span_data['async'] = False
        stream = bool(kwargs.get('stream'))

        if stream and content_from_stream:
            stream_cls: type[Stream] | None = kwargs.get('stream_cls')  # type: ignore[reportMissingTypeArgument]
            assert stream_cls is not None, 'Expected `stream_cls` when streaming'

            class LogfireInstrumentedStream(stream_cls):
                def __stream__(self) -> Iterator[Any]:
                    content: list[str] = []
                    with logfire_openai.span(STEAMING_MSG_TEMPLATE, **span_data) as stream_span:
                        with maybe_suppress_instrumentation(suppress_otel):
                            for chunk in super().__stream__():  # type: ignore
                                chunk_content = content_from_stream(chunk)
                                if chunk_content is not None:
                                    content.append(chunk_content)
                                yield chunk
                            stream_span.set_attribute(
                                'response_data',
                                {'combined_chunk_content': ''.join(content), 'chunk_count': len(content)},
                            )

            kwargs['stream_cls'] = LogfireInstrumentedStream

        with logfire_openai.span(message_template, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return original_request_method(**kwargs)
                else:
                    response = original_request_method(**kwargs)
                    on_response(response, span)
                    return response

    openai_client._request = instrumented_openai_request  # type: ignore


def instrument_openai_async(logfire_openai: Logfire, openai_client: openai.AsyncOpenAI, suppress_otel: bool) -> None:
    # WARNING: this method is vey similar to `instrument_openai_sync` above, any changes here should be reflected there
    openai_client._original_request_method = original_request_method = openai_client._request  # type: ignore

    async def instrumented_openai_request(**kwargs: Any) -> Any:
        if context.get_value('suppress_instrumentation'):
            return await original_request_method(**kwargs)

        options: FinalRequestOptions | None = kwargs.get('options')
        try:
            message_template, span_data, on_response, content_from_stream = get_endpoint_config(options)
        except ValueError as exc:
            logfire_openai.warn('Unable to instrument OpenAI API call: {error}', error=str(exc), kwargs=kwargs)
            return await original_request_method(**kwargs)

        span_data['async'] = True
        stream = bool(kwargs.get('stream'))

        if stream and content_from_stream:
            stream_cls: type[AsyncStream] | None = kwargs.get('stream_cls')  # type: ignore[reportMissingTypeArgument]
            assert stream_cls is not None, 'Expected `stream_cls` when streaming'

            class LogfireInstrumentedStream(stream_cls):
                async def __stream__(self) -> AsyncIterator[Any]:
                    content: list[str] = []
                    with logfire_openai.span(STEAMING_MSG_TEMPLATE, **span_data) as stream_span:
                        with maybe_suppress_instrumentation(suppress_otel):
                            async for chunk in super().__stream__():  # type: ignore
                                chunk_content = content_from_stream(chunk)
                                if chunk_content is not None:
                                    content.append(chunk_content)
                                yield chunk
                            stream_span.set_attribute(
                                'response_data',
                                {'combined_chunk_content': ''.join(content), 'chunk_count': len(content)},
                            )

            kwargs['stream_cls'] = LogfireInstrumentedStream

        with logfire_openai.span(message_template, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return await original_request_method(**kwargs)
                else:
                    response = await original_request_method(**kwargs)
                    on_response(response, span)
                    return response

    openai_client._request = instrumented_openai_request  # type: ignore


class EndpointConfig(NamedTuple):
    message_template: LiteralString
    span_data: dict[str, Any]
    on_response: Callable[[Any, LogfireSpan], None]
    content_from_stream: Callable[[Any], str | None] | None


def get_endpoint_config(options: FinalRequestOptions | None) -> EndpointConfig:
    if options is None:
        raise ValueError('`options` is required')
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
            on_response=on_chat_response,
            content_from_stream=lambda chunk: chunk.choices[0].delta.content,
        )
    elif url == '/completions':
        return EndpointConfig(
            message_template='Completion with {request_data[model]!r}',
            span_data={'request_data': json_data},
            on_response=on_completion_response,
            content_from_stream=lambda chunk: chunk.choices[0].text,
        )
    elif url == '/embeddings':
        return EndpointConfig(
            message_template='Embedding Creation with {request_data[model]!r}',
            span_data={'request_data': json_data},
            on_response=on_embedding_response,
            content_from_stream=None,
        )
    elif url == '/images/generations':
        return EndpointConfig(
            message_template='Image Generation with {request_data[model]!r}',
            span_data={'request_data': json_data},
            on_response=on_image_response,
            content_from_stream=None,
        )
    else:
        raise ValueError(f'Unknown OpenAI API endpoint: `{url}`')


def on_chat_response(response: ChatCompletion, span: LogfireSpan) -> None:
    span.set_attribute(
        'response_data',
        {
            'message': response.choices[0].message,
            'usage': response.usage,
        },
    )


def on_completion_response(response: Completion, span: LogfireSpan) -> None:
    first_choice = response.choices[0]
    span.set_attribute(
        'response_data',
        {
            'finish_reason': first_choice.finish_reason,
            'text': first_choice.text,
            'usage': response.usage,
        },
    )


def on_embedding_response(response: CreateEmbeddingResponse, span: LogfireSpan) -> None:
    span.set_attribute('response_data', {'usage': response.usage})


def on_image_response(response: ImagesResponse, span: LogfireSpan) -> None:
    span.set_attribute('response_data', {'images': response.data})


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
