"""LangChain/LangGraph instrumentation for capturing tool definitions.

This module provides callback-based instrumentation for LangChain that captures
tool definitions, which are not available through LangSmith's OTEL integration.
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager, contextmanager
from contextvars import Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from opentelemetry import context as context_api, trace
from opentelemetry.trace import SpanKind

if TYPE_CHECKING:
    from ..main import Logfire, LogfireSpan

# GenAI semantic convention attribute names (inline to keep LangChain instrumentation self-contained)
OPERATION_NAME = 'gen_ai.operation.name'
REQUEST_MODEL = 'gen_ai.request.model'
RESPONSE_MODEL = 'gen_ai.response.model'
RESPONSE_FINISH_REASONS = 'gen_ai.response.finish_reasons'
INPUT_TOKENS = 'gen_ai.usage.input_tokens'
OUTPUT_TOKENS = 'gen_ai.usage.output_tokens'
INPUT_MESSAGES = 'gen_ai.input.messages'
OUTPUT_MESSAGES = 'gen_ai.output.messages'
SYSTEM_INSTRUCTIONS = 'gen_ai.system_instructions'
TOOL_DEFINITIONS = 'gen_ai.tool.definitions'
CONVERSATION_ID = 'gen_ai.conversation.id'


try:
    from langchain_core.callbacks.base import BaseCallbackHandler

    _BASE_CLASS = BaseCallbackHandler
except ImportError:
    _BASE_CLASS = object


@dataclass
class SpanWithToken:
    """Container for span and its context token."""

    span: Any
    token: Token | None = None


def _set_span_in_context(span: LogfireSpan) -> Token:
    """Attach span to context and return token for later detachment."""
    otel_context = trace.set_span_in_context(span._span)
    return context_api.attach(otel_context)


def _detach_span_from_context(token: Token) -> None:
    """Detach span from context using token."""
    try:
        context_api.detach(token)
    except ValueError:
        pass


def _normalize_content_block(block: dict[str, Any]) -> dict[str, Any]:
    """Normalize a content block to OTel GenAI schema.

    Handles:
    - Text: converts 'text' field to 'content' (OTel uses 'content')
    - tool_use: converts to 'tool_call' (OTel standard)
    - tool_result: converts to 'tool_call_response' (OTel standard)
    """
    block_type = block.get('type', 'text')

    if block_type == 'text':
        return {
            'type': 'text',
            'content': block.get('content', block.get('text', '')),
        }

    if block_type == 'tool_use':
        return {
            'type': 'tool_call',
            'id': block.get('id'),
            'name': block.get('name'),
            'arguments': block.get('input', block.get('arguments')),
        }

    if block_type == 'tool_result':
        return {
            'type': 'tool_call_response',
            'id': block.get('tool_use_id', block.get('id')),
            'response': block.get('content', block.get('response')),
        }

    return block


class LogfireLangchainCallbackHandler(_BASE_CLASS):  # type: ignore[misc]
    """LangChain callback handler that captures full execution hierarchy.

    This handler captures:
    - Chain execution (on_chain_start/end)
    - Tool execution (on_tool_start/end)
    - Retriever execution (on_retriever_start/end)
    - LLM calls with tool definitions (on_chat_model_start/on_llm_start)

    Uses parent_run_id for hierarchy instead of context propagation.
    """

    def __init__(self, logfire: Logfire):
        super().__init__()
        self.run_inline = True
        self._logfire = logfire
        self._run_span_mapping: dict[str, SpanWithToken] = {}

    def _get_span_by_run_id(self, run_id: UUID) -> Any | None:
        """Get span from run_id mapping."""
        if st := self._run_span_mapping.get(str(run_id)):
            return st.span
        return None

    def _get_parent_span(self, parent_run_id: UUID | None) -> Any | None:
        """Get parent span from parent_run_id mapping."""
        if parent_run_id:
            if st := self._run_span_mapping.get(str(parent_run_id)):
                return st.span
        return None

    def _get_span_name(self, serialized: dict[str, Any], default: str = 'unknown') -> str:
        """Extract span name from serialized dict."""
        return serialized.get('name', serialized.get('id', [default])[-1])

    def _extract_conversation_id(self, metadata: dict[str, Any] | None) -> str | None:
        """Extract thread_id from metadata for gen_ai.conversation.id."""
        if metadata:
            return metadata.get('thread_id')
        return None

    def _start_span(
        self,
        span_name: str,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        span_kind: SpanKind = SpanKind.INTERNAL,
        conversation_id: str | None = None,
        **span_data: Any,
    ) -> Any:
        """Start a span with proper parent linkage using parent_run_id."""
        parent_span = self._get_parent_span(parent_run_id)

        parent_token = None
        if parent_span and parent_span._span:
            parent_context = trace.set_span_in_context(parent_span._span)
            parent_token = context_api.attach(parent_context)

        try:
            span = self._logfire.span(
                span_name,
                _span_kind=span_kind,
                **span_data,
            )
            span._start()
            if conversation_id:
                span.set_attribute(CONVERSATION_ID, conversation_id)
        finally:
            if parent_token is not None:
                context_api.detach(parent_token)

        self._run_span_mapping[str(run_id)] = SpanWithToken(span, None)
        return span

    def _end_span(
        self,
        run_id: UUID,
        outputs: Any = None,
        error: BaseException | None = None,
    ) -> None:
        """End span and clean up mapping."""
        st = self._run_span_mapping.pop(str(run_id), None)
        if not st:
            return

        try:
            if error and st.span._span and st.span._span.is_recording():
                st.span._span.record_exception(error, escaped=True)
            st.span._end()
        finally:
            if st.token:
                _detach_span_from_context(st.token)

    def _extract_tool_definitions(self, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool definitions from invocation_params.tools."""
        raw_tools = kwargs.get('invocation_params', {}).get('tools', [])
        tools = []
        for raw_tool in raw_tools:
            if raw_tool.get('type') == 'function':
                tools.append(raw_tool)
            elif 'name' in raw_tool:
                tools.append(
                    {
                        'type': 'function',
                        'function': {
                            'name': raw_tool.get('name'),
                            'description': raw_tool.get('description'),
                            'parameters': raw_tool.get('input_schema', raw_tool.get('parameters')),
                        },
                    }
                )
        return tools

    def _convert_messages_to_otel(
        self, messages: list[list[Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Convert LangChain messages to OTel GenAI format."""
        input_msgs: list[dict[str, Any]] = []
        system_instructions: list[dict[str, Any]] = []

        for msg_list in messages:
            for msg in msg_list:
                msg_type = getattr(msg, 'type', 'unknown')
                content = getattr(msg, 'content', str(msg))

                if msg_type == 'system':
                    if isinstance(content, str):
                        system_instructions.append({'type': 'text', 'content': content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if 'text' in item and 'content' not in item:
                                    system_instructions.append({
                                        'type': item.get('type', 'text'),
                                        'content': item['text'],
                                    })
                                else:
                                    system_instructions.append(item)
                            elif isinstance(item, str):
                                system_instructions.append({'type': 'text', 'content': item})
                elif msg_type == 'tool':
                    tool_call_id = getattr(msg, 'tool_call_id', None)
                    response_content = content if isinstance(content, str) else str(content)
                    parts: list[dict[str, Any]] = [{
                        'type': 'tool_call_response',
                        'id': tool_call_id,
                        'response': response_content,
                    }]
                    input_msgs.append({'role': 'tool', 'parts': parts})
                else:
                    otel_role = {'human': 'user', 'ai': 'assistant'}.get(msg_type, msg_type)
                    parts = []

                    if isinstance(content, str):
                        parts.append({'type': 'text', 'content': content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get('type') == 'tool_use':
                                    continue
                                parts.append(_normalize_content_block(item))
                            elif isinstance(item, str):
                                parts.append({'type': 'text', 'content': item})

                    if tool_calls := getattr(msg, 'tool_calls', None):
                        for tc in tool_calls:
                            if isinstance(tc, dict):
                                parts.append({
                                    'type': 'tool_call',
                                    'id': tc.get('id'),
                                    'name': tc.get('name'),
                                    'arguments': tc.get('args'),
                                })

                    input_msgs.append({'role': otel_role, 'parts': parts})

        return input_msgs, system_instructions

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        run_type: str | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain starts - creates parent span for hierarchy."""
        span_name = name or self._get_span_name(serialized, 'chain')
        conversation_id = self._extract_conversation_id(metadata)
        self._start_span(span_name, run_id, parent_run_id, SpanKind.INTERNAL, conversation_id=conversation_id)

    def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chain ends."""
        self._end_span(run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a chain errors."""
        self._end_span(run_id, error=error)

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts."""
        span_name = name or self._get_span_name(serialized, 'tool')
        conversation_id = self._extract_conversation_id(metadata)
        self._start_span(span_name, run_id, parent_run_id, SpanKind.INTERNAL, conversation_id=conversation_id)

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a tool ends."""
        self._end_span(run_id)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors."""
        self._end_span(run_id, error=error)

    def on_retriever_start(
        self,
        serialized: dict[str, Any],
        query: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever starts."""
        span_name = name or self._get_span_name(serialized, 'retriever')
        conversation_id = self._extract_conversation_id(metadata)
        self._start_span(span_name, run_id, parent_run_id, SpanKind.INTERNAL, conversation_id=conversation_id)

    def on_retriever_end(
        self,
        documents: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever ends."""
        self._end_span(run_id)

    def on_retriever_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when a retriever errors."""
        self._end_span(run_id, error=error)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a chat model starts - captures tool definitions."""
        invocation_params = kwargs.get('invocation_params', {})
        model = invocation_params.get('model', invocation_params.get('model_name', 'unknown'))

        span_name = name or self._get_span_name(serialized, f'chat {model}')
        span_data: dict[str, Any] = {
            OPERATION_NAME: 'chat',
            REQUEST_MODEL: model,
        }

        if tools := self._extract_tool_definitions(kwargs):
            span_data[TOOL_DEFINITIONS] = tools

        try:
            input_msgs, system_instructions = self._convert_messages_to_otel(messages)
            if input_msgs:
                span_data[INPUT_MESSAGES] = input_msgs
            if system_instructions:
                span_data[SYSTEM_INSTRUCTIONS] = system_instructions
        except Exception:
            pass

        conversation_id = self._extract_conversation_id(metadata)
        self._start_span(span_name, run_id, parent_run_id, SpanKind.CLIENT, conversation_id=conversation_id, **span_data)

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a non-chat LLM starts."""
        invocation_params = kwargs.get('invocation_params', {})
        model = invocation_params.get('model', invocation_params.get('model_name', 'unknown'))

        span_name = name or self._get_span_name(serialized, f'llm {model}')
        span_data: dict[str, Any] = {
            OPERATION_NAME: 'completion',
            REQUEST_MODEL: model,
        }

        if tools := self._extract_tool_definitions(kwargs):
            span_data[TOOL_DEFINITIONS] = tools

        conversation_id = self._extract_conversation_id(metadata)
        self._start_span(span_name, run_id, parent_run_id, SpanKind.CLIENT, conversation_id=conversation_id, **span_data)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when LLM ends."""
        span = self._get_span_by_run_id(run_id)
        if not span:
            return

        try:
            generations = getattr(response, 'generations', [[]])
            if generations and generations[0]:
                gen = generations[0][0]
                message = getattr(gen, 'message', None)
                if message:
                    response_metadata = getattr(message, 'response_metadata', {}) or {}
                    if stop_reason := response_metadata.get('stop_reason', response_metadata.get('finish_reason')):
                        span.set_attribute(RESPONSE_FINISH_REASONS, json.dumps([stop_reason]))

                    if model_name := response_metadata.get('model_name', response_metadata.get('model')):
                        span.set_attribute(RESPONSE_MODEL, model_name)

                    content = getattr(message, 'content', '')
                    output_msg: dict[str, Any] = {'role': 'assistant', 'parts': []}

                    if isinstance(content, str):
                        output_msg['parts'].append({'type': 'text', 'content': content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get('type') == 'tool_use':
                                    continue
                                output_msg['parts'].append(_normalize_content_block(item))
                            elif isinstance(item, str):
                                output_msg['parts'].append({'type': 'text', 'content': item})

                    if tool_calls := getattr(message, 'tool_calls', None):
                        for tc in tool_calls:
                            if isinstance(tc, dict):
                                output_msg['parts'].append(
                                    {
                                        'type': 'tool_call',
                                        'id': tc.get('id'),
                                        'name': tc.get('name'),
                                        'arguments': tc.get('args'),
                                    }
                                )

                    span.set_attribute(OUTPUT_MESSAGES, [output_msg])

            llm_output = getattr(response, 'llm_output', {}) or {}
            usage = llm_output.get('usage') or llm_output.get('token_usage') or {}
            if input_tokens := usage.get('input_tokens', usage.get('prompt_tokens')):
                span.set_attribute(INPUT_TOKENS, input_tokens)
            if output_tokens := usage.get('output_tokens', usage.get('completion_tokens')):
                span.set_attribute(OUTPUT_TOKENS, output_tokens)
        except Exception:
            pass
        finally:
            self._end_span(run_id)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors."""
        self._end_span(run_id, error=error)


_original_callback_manager_init: Any = None
_logfire_instance: Logfire | None = None
_handler_instance: LogfireLangchainCallbackHandler | None = None


def _patch_callback_manager(logfire: Logfire) -> None:
    """Patch BaseCallbackManager to inject our handler."""
    global _original_callback_manager_init, _logfire_instance, _handler_instance

    try:
        from langchain_core.callbacks import BaseCallbackManager
    except ImportError as e:
        raise ImportError(
            'langchain-core is required for LangChain instrumentation. Install it with: pip install langchain-core'
        ) from e

    if _original_callback_manager_init is not None:
        return

    _logfire_instance = logfire
    _handler_instance = None
    _original_callback_manager_init = BaseCallbackManager.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        global _handler_instance
        _original_callback_manager_init(self, *args, **kwargs)

        for handler in list(getattr(self, 'handlers', [])) + list(getattr(self, 'inheritable_handlers', [])):
            if isinstance(handler, LogfireLangchainCallbackHandler):
                return

        if _logfire_instance is not None:
            if _handler_instance is None:
                _handler_instance = LogfireLangchainCallbackHandler(_logfire_instance)
            self.add_handler(_handler_instance, inherit=True)

    BaseCallbackManager.__init__ = patched_init


def _unpatch_callback_manager() -> None:
    """Restore original BaseCallbackManager.__init__."""
    global _original_callback_manager_init, _logfire_instance, _handler_instance

    if _original_callback_manager_init is None:
        return

    try:
        from langchain_core.callbacks import BaseCallbackManager

        BaseCallbackManager.__init__ = _original_callback_manager_init
    except ImportError:
        pass

    _original_callback_manager_init = None
    _logfire_instance = None
    _handler_instance = None


def instrument_langchain(logfire: Logfire) -> AbstractContextManager[None]:
    """Instrument LangChain to capture full execution hierarchy.

    This patches LangChain's BaseCallbackManager to inject a callback handler
    that captures the complete execution hierarchy including chains, tools,
    retrievers, and LLMs with tool definitions.

    The patching happens immediately when this function is called.
    Returns a context manager that can be used to uninstrument if needed.

    Args:
        logfire: The Logfire instance to use for creating spans.

    Returns:
        A context manager for optional cleanup/uninstrumentation.

    Example:
        ```python
        import logfire

        logfire.configure()
        logfire.instrument_langchain()

        # Now LangChain operations will be traced with full hierarchy
        ```
    """
    _patch_callback_manager(logfire)

    @contextmanager
    def cleanup_context():
        try:
            yield
        finally:
            _unpatch_callback_manager()

    return cleanup_context()
