from __future__ import annotations

from collections.abc import Iterable
from contextlib import ExitStack, contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, ContextManager, Iterator, cast

from ...constants import ONE_SECOND_IN_NANOSECONDS
from ...utils import is_instrumentation_suppressed, suppress_instrumentation

if TYPE_CHECKING:
    from ...main import Logfire, LogfireSpan
    from .types import EndpointConfig


__all__ = ('instrument_llm_provider',)


def instrument_llm_provider(
    logfire: Logfire,
    client: Any,
    suppress_otel: bool,
    scope_suffix: str,
    get_endpoint_config_fn: Callable[[Any], EndpointConfig],
    on_response_fn: Callable[[Any, LogfireSpan], Any],
    is_async_client_fn: Callable[[type[Any]], bool],
) -> ContextManager[None]:
    """Instruments the provided `client` (or clients) with `logfire`.

    The `client` argument can be:
    - a single client instance, e.g. an instance of `openai.OpenAI`,
    - a class of a client, or
    - an iterable of clients/classes.

    Returns:
        A context manager that will revert the instrumentation when exited.
            Use of this context manager is optional.
    """
    if isinstance(client, Iterable):
        # Eagerly instrument each client, but only open the returned context managers
        # in another context manager which the user needs to open if they want.
        # Otherwise the garbage collector will close them and uninstrument.
        context_managers = [
            instrument_llm_provider(
                logfire,
                c,
                suppress_otel,
                scope_suffix,
                get_endpoint_config_fn,
                on_response_fn,
                is_async_client_fn,
            )
            for c in cast('Iterable[Any]', client)
        ]

        @contextmanager
        def uninstrument_context():
            with ExitStack() as exit_stack:
                for context_manager in context_managers:
                    exit_stack.enter_context(context_manager)
                yield

        return uninstrument_context()

    if getattr(client, '_is_instrumented_by_logfire', False):
        # Do nothing if already instrumented.
        return nullcontext()

    logfire_llm = logfire.with_settings(custom_scope_suffix=scope_suffix.lower(), tags=['LLM'])

    client._is_instrumented_by_logfire = True
    client._original_request_method = original_request_method = client._request

    is_async = is_async_client_fn(client if isinstance(client, type) else type(client))

    def _instrumentation_setup(**kwargs: Any) -> Any:
        if is_instrumentation_suppressed():
            return None, None, kwargs

        options = kwargs['options']
        try:
            message_template, span_data, content_from_stream = get_endpoint_config_fn(options)
        except ValueError as exc:
            logfire_llm.warn(
                'Unable to instrument {suffix} API call: {error}', suffix=scope_suffix, error=str(exc), kwargs=kwargs
            )
            return None, None, kwargs

        span_data['async'] = is_async

        stream = kwargs['stream']

        if stream and content_from_stream:
            stream_cls = kwargs['stream_cls']
            assert stream_cls is not None, 'Expected `stream_cls` when streaming'

            if is_async:

                class LogfireInstrumentedAsyncStream(stream_cls):
                    async def __stream__(self) -> AsyncIterator[Any]:
                        with record_streaming(logfire_llm, span_data, content_from_stream) as record_chunk:
                            async for chunk in super().__stream__():  # type: ignore
                                record_chunk(chunk)
                                yield chunk

                kwargs['stream_cls'] = LogfireInstrumentedAsyncStream
            else:

                class LogfireInstrumentedStream(stream_cls):
                    def __stream__(self) -> Iterator[Any]:
                        with record_streaming(logfire_llm, span_data, content_from_stream) as record_chunk:
                            for chunk in super().__stream__():  # type: ignore
                                record_chunk(chunk)
                                yield chunk

                kwargs['stream_cls'] = LogfireInstrumentedStream

        return message_template, span_data, kwargs

    # In these methods, `*args` is only expected to be `(self,)`
    # in the case where we instrument classes rather than client instances.

    def instrumented_llm_request_sync(*args: Any, **kwargs: Any) -> Any:
        message_template, span_data, kwargs = _instrumentation_setup(**kwargs)
        if message_template is None:
            return original_request_method(*args, **kwargs)
        stream = kwargs['stream']
        with logfire_llm.span(message_template, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return original_request_method(*args, **kwargs)
                else:
                    response = on_response_fn(original_request_method(*args, **kwargs), span)
                    return response

    async def instrumented_llm_request_async(*args: Any, **kwargs: Any) -> Any:
        message_template, span_data, kwargs = _instrumentation_setup(**kwargs)
        if message_template is None:
            return await original_request_method(*args, **kwargs)
        stream = kwargs['stream']
        with logfire_llm.span(message_template, **span_data) as span:
            with maybe_suppress_instrumentation(suppress_otel):
                if stream:
                    return await original_request_method(*args, **kwargs)
                else:
                    response = on_response_fn(await original_request_method(*args, **kwargs), span)
                    return response

    if is_async:
        client._request = instrumented_llm_request_async
    else:
        client._request = instrumented_llm_request_sync

    @contextmanager
    def uninstrument_context():
        """Context manager to remove instrumentation from the LLM client.

        The user isn't required (or even expected) to use this context manager,
        which is why the instrumenting has already happened before.
        It exists mostly for tests and just in case users want it.
        """
        try:
            yield
        finally:
            client._request = client._original_request_method  # type: ignore
            del client._original_request_method
            client._is_instrumented_by_logfire = False

    return uninstrument_context()


@contextmanager
def maybe_suppress_instrumentation(suppress: bool) -> Iterator[None]:
    if suppress:
        with suppress_instrumentation():
            yield
    else:
        yield


@contextmanager
def record_streaming(
    logire_llm: Logfire,
    span_data: dict[str, Any],
    content_from_stream: Callable[[Any], str | None],
):
    content: list[str] = []

    def record_chunk(chunk: Any) -> Any:
        chunk_content = content_from_stream(chunk)
        if chunk_content is not None:
            content.append(chunk_content)

    timer = logire_llm._config.ns_timestamp_generator  # type: ignore
    start = timer()
    try:
        yield record_chunk
    finally:
        duration = (timer() - start) / ONE_SECOND_IN_NANOSECONDS
        logire_llm.info(
            'streaming response from {request_data[model]!r} took {duration:.2f}s',
            **span_data,
            duration=duration,
            response_data={'combined_chunk_content': ''.join(content), 'chunk_count': len(content)},
        )
