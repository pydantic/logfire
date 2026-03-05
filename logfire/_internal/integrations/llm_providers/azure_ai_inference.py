# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from typing import TYPE_CHECKING, Any, cast

from opentelemetry.trace import SpanKind

from logfire import attach_context, get_context

from ...constants import ONE_SECOND_IN_NANOSECONDS
from ...utils import handle_internal_errors, is_instrumentation_suppressed, log_internal_error, suppress_instrumentation
from .semconv import (
    INPUT_MESSAGES,
    INPUT_TOKENS,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    OUTPUT_TOKENS,
    PROVIDER_NAME,
    REQUEST_FREQUENCY_PENALTY,
    REQUEST_MAX_TOKENS,
    REQUEST_MODEL,
    REQUEST_PRESENCE_PENALTY,
    REQUEST_SEED,
    REQUEST_STOP_SEQUENCES,
    REQUEST_TEMPERATURE,
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
    OutputMessages,
    Role,
    SystemInstructions,
    TextPart,
    ToolCallPart,
    ToolCallResponsePart,
    UriPart,
)

if TYPE_CHECKING:
    from ...main import Logfire, LogfireSpan

__all__ = ('instrument_azure_ai_inference',)

AZURE_PROVIDER = 'azure.ai.inference'

CHAT_MSG_TEMPLATE = 'Chat completion with {request_data[model]!r}'
CHAT_MSG_TEMPLATE_NO_MODEL = 'Chat completion'
EMBED_MSG_TEMPLATE = 'Embeddings with {request_data[model]!r}'
EMBED_MSG_TEMPLATE_NO_MODEL = 'Embeddings'
STREAM_MSG_TEMPLATE = 'streaming response from {request_data[model]!r} took {duration:.2f}s'
STREAM_MSG_TEMPLATE_NO_MODEL = 'streaming response took {duration:.2f}s'


# --- Main instrumentation entry point ---


def instrument_azure_ai_inference(
    logfire_instance: Logfire,
    client: Any,
    suppress_other_instrumentation: bool,
) -> AbstractContextManager[None]:
    """Instrument Azure AI Inference clients."""
    if client is None:
        try:
            from azure.ai.inference import ChatCompletionsClient, EmbeddingsClient
        except ImportError:  # pragma: no cover
            raise RuntimeError(
                'The `logfire.instrument_azure_ai_inference()` method '
                'requires the `azure-ai-inference` package.\n'
                'You can install this with:\n'
                "    pip install 'logfire[azure-ai-inference]'"
            )

        clients: list[Any] = [ChatCompletionsClient, EmbeddingsClient]
        try:
            from azure.ai.inference.aio import (
                ChatCompletionsClient as AsyncChatCompletionsClient,
                EmbeddingsClient as AsyncEmbeddingsClient,
            )

            clients.extend([AsyncChatCompletionsClient, AsyncEmbeddingsClient])
        except ImportError:  # pragma: no cover
            pass
        client = clients

    if isinstance(client, (tuple, list)):
        context_managers = [
            instrument_azure_ai_inference(logfire_instance, c, suppress_other_instrumentation) for c in client
        ]

        @contextmanager
        def uninstrument_all() -> Iterator[None]:
            with ExitStack() as stack:
                for cm in context_managers:
                    stack.enter_context(cm)
                yield

        return uninstrument_all()

    if getattr(client, '_is_instrumented_by_logfire', False):
        return nullcontext()

    client_cls = client if isinstance(client, type) else type(client)
    is_async = _is_async_client(client_cls)
    client_type = _get_client_type(client_cls)

    if client_type is None:  # pragma: no cover
        return nullcontext()

    logfire_llm = logfire_instance.with_settings(custom_scope_suffix='azure_ai_inference', tags=['LLM'])
    client._is_instrumented_by_logfire = True

    if client_type == 'chat':
        method_name = 'complete'
        original = client.complete
        client._original_logfire_method = original
        client.complete = _make_instrumented_complete(original, logfire_llm, suppress_other_instrumentation, is_async)
    else:
        method_name = 'embed'
        original = client.embed
        client._original_logfire_method = original
        client.embed = _make_instrumented_embed(original, logfire_llm, suppress_other_instrumentation, is_async)

    @contextmanager
    def uninstrument() -> Iterator[None]:
        try:
            yield
        finally:
            setattr(client, method_name, client._original_logfire_method)
            del client._original_logfire_method
            client._is_instrumented_by_logfire = False

    return uninstrument()


# --- Client type detection ---


def _is_async_client(client_cls: type[Any]) -> bool:
    return 'aio' in client_cls.__module__


def _get_client_type(client_cls: type[Any]) -> str | None:
    name = client_cls.__name__
    if 'ChatCompletions' in name:
        return 'chat'
    if 'Embeddings' in name:
        return 'embeddings'
    return None  # pragma: no cover


# --- Instrumented method factories ---


def _make_instrumented_complete(
    original: Any,
    logfire_llm: Logfire,
    suppress: bool,
    is_async: bool,
) -> Any:
    if is_async:

        async def instrumented_complete(*args: Any, **kwargs: Any) -> Any:
            if is_instrumentation_suppressed():  # pragma: no cover
                return await original(*args, **kwargs)
            try:
                span_data = _build_chat_span_data(args, kwargs)
            except Exception:  # pragma: no cover
                log_internal_error()
                return await original(*args, **kwargs)

            is_streaming = kwargs.get('stream', False)
            original_context = get_context()
            msg = CHAT_MSG_TEMPLATE if span_data['request_data']['model'] else CHAT_MSG_TEMPLATE_NO_MODEL

            with logfire_llm.span(msg, _span_kind=SpanKind.CLIENT, **span_data) as span:
                if suppress:
                    with suppress_instrumentation():
                        response = await original(*args, **kwargs)
                else:
                    response = await original(*args, **kwargs)

                if is_streaming:
                    return _AsyncStreamWrapper(response, logfire_llm, span_data, original_context)
                _on_chat_response(response, span, span_data)
                return response

        return instrumented_complete
    else:

        def instrumented_complete_sync(*args: Any, **kwargs: Any) -> Any:
            if is_instrumentation_suppressed():  # pragma: no cover
                return original(*args, **kwargs)
            try:
                span_data = _build_chat_span_data(args, kwargs)
            except Exception:  # pragma: no cover
                log_internal_error()
                return original(*args, **kwargs)

            is_streaming = kwargs.get('stream', False)
            original_context = get_context()
            msg = CHAT_MSG_TEMPLATE if span_data['request_data']['model'] else CHAT_MSG_TEMPLATE_NO_MODEL

            with logfire_llm.span(msg, _span_kind=SpanKind.CLIENT, **span_data) as span:
                if suppress:
                    with suppress_instrumentation():
                        response = original(*args, **kwargs)
                else:
                    response = original(*args, **kwargs)

                if is_streaming:
                    return _SyncStreamWrapper(response, logfire_llm, span_data, original_context)
                _on_chat_response(response, span, span_data)
                return response

        return instrumented_complete_sync


def _make_instrumented_embed(
    original: Any,
    logfire_llm: Logfire,
    suppress: bool,
    is_async: bool,
) -> Any:
    if is_async:

        async def instrumented_embed(*args: Any, **kwargs: Any) -> Any:
            if is_instrumentation_suppressed():  # pragma: no cover
                return await original(*args, **kwargs)
            try:
                span_data = _build_embed_span_data(args, kwargs)
            except Exception:  # pragma: no cover
                log_internal_error()
                return await original(*args, **kwargs)

            msg = EMBED_MSG_TEMPLATE if span_data['request_data']['model'] else EMBED_MSG_TEMPLATE_NO_MODEL

            with logfire_llm.span(msg, _span_kind=SpanKind.CLIENT, **span_data) as span:
                if suppress:
                    with suppress_instrumentation():
                        response = await original(*args, **kwargs)
                else:
                    response = await original(*args, **kwargs)
                _on_embed_response(response, span, span_data)
                return response

        return instrumented_embed
    else:

        def instrumented_embed_sync(*args: Any, **kwargs: Any) -> Any:
            if is_instrumentation_suppressed():  # pragma: no cover
                return original(*args, **kwargs)
            try:
                span_data = _build_embed_span_data(args, kwargs)
            except Exception:  # pragma: no cover
                log_internal_error()
                return original(*args, **kwargs)

            msg = EMBED_MSG_TEMPLATE if span_data['request_data']['model'] else EMBED_MSG_TEMPLATE_NO_MODEL

            with logfire_llm.span(msg, _span_kind=SpanKind.CLIENT, **span_data) as span:
                if suppress:
                    with suppress_instrumentation():
                        response = original(*args, **kwargs)
                else:
                    response = original(*args, **kwargs)
                _on_embed_response(response, span, span_data)
                return response

        return instrumented_embed_sync


# --- Span data builders ---


def _build_chat_span_data(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    params = _extract_params(args, kwargs)
    messages = params.get('messages', [])
    model = params.get('model')

    span_data: dict[str, Any] = {
        'request_data': {'model': model},
        PROVIDER_NAME: AZURE_PROVIDER,
        OPERATION_NAME: 'chat',
    }
    if model:
        span_data[REQUEST_MODEL] = model

    _extract_request_parameters(params, span_data)

    if messages:
        input_messages, system_instructions = convert_messages_to_semconv(messages)
        span_data[INPUT_MESSAGES] = input_messages
        if system_instructions:
            span_data[SYSTEM_INSTRUCTIONS] = system_instructions

    return span_data


def _build_embed_span_data(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    params = _extract_params(args, kwargs)
    model = params.get('model')

    span_data: dict[str, Any] = {
        'request_data': {'model': model},
        PROVIDER_NAME: AZURE_PROVIDER,
        OPERATION_NAME: 'embeddings',
    }
    if model:
        span_data[REQUEST_MODEL] = model

    return span_data


def _extract_params(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    """Extract parameters from method call, handling both body and keyword styles."""
    if 'body' in kwargs and isinstance(kwargs['body'], dict):
        return kwargs['body']
    for arg in args:
        if isinstance(arg, dict) and ('messages' in arg or 'input' in arg):
            return arg
    return kwargs


def _extract_request_parameters(params: dict[str, Any], span_data: dict[str, Any]) -> None:
    if (max_tokens := params.get('max_tokens')) is not None:
        span_data[REQUEST_MAX_TOKENS] = max_tokens
    if (temperature := params.get('temperature')) is not None:
        span_data[REQUEST_TEMPERATURE] = temperature
    if (top_p := params.get('top_p')) is not None:
        span_data[REQUEST_TOP_P] = top_p
    if (frequency_penalty := params.get('frequency_penalty')) is not None:
        span_data[REQUEST_FREQUENCY_PENALTY] = frequency_penalty
    if (presence_penalty := params.get('presence_penalty')) is not None:
        span_data[REQUEST_PRESENCE_PENALTY] = presence_penalty
    if (seed := params.get('seed')) is not None:
        span_data[REQUEST_SEED] = seed
    if (stop := params.get('stop')) is not None:
        span_data[REQUEST_STOP_SEQUENCES] = json.dumps(stop)
    if (tools := params.get('tools')) is not None:
        span_data[TOOL_DEFINITIONS] = json.dumps([t if isinstance(t, dict) else t.as_dict() for t in tools])


# --- Response processors ---


def _backfill_model(response: Any, span: LogfireSpan, span_data: dict[str, Any], operation: str = 'chat') -> None:
    """If the request model was None, backfill it from the response model."""
    model = getattr(response, 'model', None)
    if not model:
        return
    request_data = span_data.get('request_data')
    if not isinstance(request_data, dict) or request_data.get('model') is not None:
        return
    request_data['model'] = model
    span.set_attribute('request_data', request_data)
    span.set_attribute(REQUEST_MODEL, model)
    if operation == 'chat':
        span.message = f'Chat completion with {model!r}'
    else:
        span.message = f'Embeddings with {model!r}'


@handle_internal_errors
def _on_chat_response(response: Any, span: LogfireSpan, span_data: dict[str, Any]) -> None:
    _backfill_model(response, span, span_data)
    choices = getattr(response, 'choices', [])
    usage = getattr(response, 'usage', None)

    output_messages = convert_response_to_semconv(response)
    if output_messages:
        span.set_attribute(OUTPUT_MESSAGES, output_messages)

    model = getattr(response, 'model', None)
    if model:
        span.set_attribute(RESPONSE_MODEL, model)

    response_id = getattr(response, 'id', None)
    if response_id:
        span.set_attribute(RESPONSE_ID, response_id)

    if usage:
        prompt_tokens = getattr(usage, 'prompt_tokens', None)
        if prompt_tokens is not None:
            span.set_attribute(INPUT_TOKENS, prompt_tokens)
        completion_tokens = getattr(usage, 'completion_tokens', None)
        if completion_tokens is not None:
            span.set_attribute(OUTPUT_TOKENS, completion_tokens)

    finish_reasons = [str(c.finish_reason) for c in choices if getattr(c, 'finish_reason', None)]
    if finish_reasons:
        span.set_attribute(RESPONSE_FINISH_REASONS, finish_reasons)


@handle_internal_errors
def _on_embed_response(response: Any, span: LogfireSpan, span_data: dict[str, Any]) -> None:
    _backfill_model(response, span, span_data, operation='embeddings')
    usage = getattr(response, 'usage', None)

    model = getattr(response, 'model', None)
    if model:
        span.set_attribute(RESPONSE_MODEL, model)

    response_id = getattr(response, 'id', None)
    if response_id:
        span.set_attribute(RESPONSE_ID, response_id)

    if usage:
        prompt_tokens = getattr(usage, 'prompt_tokens', None)
        if prompt_tokens is not None:
            span.set_attribute(INPUT_TOKENS, prompt_tokens)


# --- Message conversion ---


def convert_messages_to_semconv(messages: list[Any]) -> tuple[InputMessages, SystemInstructions]:
    """Convert Azure AI Inference messages to OTel GenAI semconv format."""
    input_messages: InputMessages = []
    system_instructions: SystemInstructions = []

    for msg in messages:
        msg_dict = _msg_to_dict(msg)
        role: str = msg_dict.get('role', 'user')
        content = msg_dict.get('content')

        if role in ('system', 'developer'):
            if isinstance(content, str):
                system_instructions.append(TextPart(type='text', content=content))
            continue

        if role == 'tool':
            tool_call_id = msg_dict.get('tool_call_id', '')
            input_messages.append(
                ChatMessage(
                    role='tool',
                    parts=[
                        ToolCallResponsePart(
                            type='tool_call_response',
                            id=tool_call_id,
                            response=content if isinstance(content, str) else str(content) if content else '',
                        )
                    ],
                )
            )
            continue

        parts: list[MessagePart] = []
        if isinstance(content, str) and content:
            parts.append(TextPart(type='text', content=content))
        elif isinstance(content, list):
            for item in content:
                parts.append(_convert_content_item(item))

        tool_calls = msg_dict.get('tool_calls')
        if tool_calls:
            for tc in tool_calls:
                tc_dict = tc if isinstance(tc, dict) else (tc.as_dict() if hasattr(tc, 'as_dict') else {})
                func = tc_dict.get('function', {})
                parts.append(
                    ToolCallPart(
                        type='tool_call',
                        id=tc_dict.get('id', ''),
                        name=func.get('name', ''),
                        arguments=func.get('arguments'),
                    )
                )

        chat_role: Role = cast('Role', role if role in ('user', 'assistant') else 'user')
        input_messages.append(ChatMessage(role=chat_role, parts=parts))

    return input_messages, system_instructions


def _msg_to_dict(msg: Any) -> dict[str, Any]:
    """Convert an Azure message object or dict to a plain dict."""
    if isinstance(msg, dict):
        return msg
    if hasattr(msg, 'as_dict'):
        return msg.as_dict()
    return {}  # pragma: no cover


def _convert_content_item(item: Any) -> MessagePart:
    """Convert a content item (text, image, audio) to semconv format."""
    if isinstance(item, str):
        return TextPart(type='text', content=item)

    item_dict = item if isinstance(item, dict) else (item.as_dict() if hasattr(item, 'as_dict') else {})
    item_type = item_dict.get('type', 'text')

    if item_type == 'text':
        return TextPart(type='text', content=item_dict.get('text', ''))
    elif item_type == 'image_url':
        image_url = item_dict.get('image_url', {})
        return UriPart(type='uri', uri=image_url.get('url', ''), modality='image')
    elif item_type == 'input_audio':
        audio = item_dict.get('input_audio', {})
        return BlobPart(
            type='blob',
            content=audio.get('data', ''),
            media_type=f'audio/{audio.get("format", "wav")}',
            modality='audio',
        )
    else:  # pragma: no cover
        return cast('MessagePart', item_dict)


def convert_response_to_semconv(response: Any) -> OutputMessages:
    """Convert a ChatCompletions response to OTel GenAI semconv format."""
    output_messages: OutputMessages = []

    for choice in getattr(response, 'choices', []):
        message = getattr(choice, 'message', None)
        if not message:
            continue

        parts: list[MessagePart] = []
        content = getattr(message, 'content', None)
        if content:
            parts.append(TextPart(type='text', content=content))

        tool_calls = getattr(message, 'tool_calls', None)
        if tool_calls:
            for tc in tool_calls:
                func = getattr(tc, 'function', None)
                if func:
                    parts.append(
                        ToolCallPart(
                            type='tool_call',
                            id=getattr(tc, 'id', ''),
                            name=getattr(func, 'name', ''),
                            arguments=getattr(func, 'arguments', None),
                        )
                    )

        output_msg: OutputMessage = {
            'role': cast('Role', getattr(message, 'role', 'assistant')),
            'parts': parts,
        }
        finish_reason = getattr(choice, 'finish_reason', None)
        if finish_reason:
            output_msg['finish_reason'] = str(finish_reason)
        output_messages.append(output_msg)

    return output_messages


# --- Streaming wrappers ---


class _SyncStreamWrapper:
    """Wraps a sync streaming response to record chunks and emit a streaming info span."""

    def __init__(
        self,
        wrapped: Any,
        logfire_llm: Logfire,
        span_data: dict[str, Any],
        original_context: Any,
    ) -> None:
        self._wrapped = wrapped
        self._logfire_llm = logfire_llm
        self._span_data = span_data
        self._original_context = original_context
        self._chunks: list[str] = []

    def __enter__(self) -> _SyncStreamWrapper:
        if hasattr(self._wrapped, '__enter__'):
            self._wrapped.__enter__()
        return self

    def __exit__(self, *args: Any) -> None:
        if hasattr(self._wrapped, '__exit__'):
            self._wrapped.__exit__(*args)

    def __iter__(self) -> Iterator[Any]:
        timer = self._logfire_llm._config.advanced.ns_timestamp_generator  # type: ignore
        start = timer()
        try:
            for chunk in self._wrapped:
                self._record_chunk(chunk)
                yield chunk
        finally:
            duration = (timer() - start) / ONE_SECOND_IN_NANOSECONDS
            has_model = self._span_data.get('request_data', {}).get('model') is not None
            msg = STREAM_MSG_TEMPLATE if has_model else STREAM_MSG_TEMPLATE_NO_MODEL
            with attach_context(self._original_context):
                self._logfire_llm.info(msg, duration=duration, **self._get_stream_attributes())

    def _record_chunk(self, chunk: Any) -> None:
        if self._span_data.get('request_data', {}).get('model') is None:
            model = getattr(chunk, 'model', None)
            if model:
                self._span_data['request_data']['model'] = model
                self._span_data[REQUEST_MODEL] = model
        for choice in getattr(chunk, 'choices', []):
            delta = getattr(choice, 'delta', None)
            if delta:
                content = getattr(delta, 'content', None)
                if content:
                    self._chunks.append(content)

    def _get_stream_attributes(self) -> dict[str, Any]:
        result = dict(**self._span_data)
        combined = ''.join(self._chunks)
        if self._chunks:
            result[OUTPUT_MESSAGES] = [
                OutputMessage(
                    role='assistant',
                    parts=[TextPart(type='text', content=combined)],
                )
            ]
        return result


class _AsyncStreamWrapper:
    """Wraps an async streaming response to record chunks and emit a streaming info span."""

    def __init__(
        self,
        wrapped: Any,
        logfire_llm: Logfire,
        span_data: dict[str, Any],
        original_context: Any,
    ) -> None:
        self._wrapped = wrapped
        self._logfire_llm = logfire_llm
        self._span_data = span_data
        self._original_context = original_context
        self._chunks: list[str] = []

    async def __aenter__(self) -> _AsyncStreamWrapper:
        if hasattr(self._wrapped, '__aenter__'):
            await self._wrapped.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if hasattr(self._wrapped, '__aexit__'):
            await self._wrapped.__aexit__(*args)

    async def __aiter__(self) -> AsyncIterator[Any]:
        timer = self._logfire_llm._config.advanced.ns_timestamp_generator  # type: ignore
        start = timer()
        try:
            async for chunk in self._wrapped:
                self._record_chunk(chunk)
                yield chunk
        finally:
            duration = (timer() - start) / ONE_SECOND_IN_NANOSECONDS
            has_model = self._span_data.get('request_data', {}).get('model') is not None
            msg = STREAM_MSG_TEMPLATE if has_model else STREAM_MSG_TEMPLATE_NO_MODEL
            with attach_context(self._original_context):
                self._logfire_llm.info(msg, duration=duration, **self._get_stream_attributes())

    def _record_chunk(self, chunk: Any) -> None:
        if self._span_data.get('request_data', {}).get('model') is None:
            model = getattr(chunk, 'model', None)
            if model:
                self._span_data['request_data']['model'] = model
                self._span_data[REQUEST_MODEL] = model
        for choice in getattr(chunk, 'choices', []):
            delta = getattr(choice, 'delta', None)
            if delta:
                content = getattr(delta, 'content', None)
                if content:
                    self._chunks.append(content)

    def _get_stream_attributes(self) -> dict[str, Any]:
        result = dict(**self._span_data)
        combined = ''.join(self._chunks)
        if self._chunks:
            result[OUTPUT_MESSAGES] = [
                OutputMessage(
                    role='assistant',
                    parts=[TextPart(type='text', content=combined)],
                )
            ]
        return result
