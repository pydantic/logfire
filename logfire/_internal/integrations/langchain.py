"""LangChain/LangGraph instrumentation for capturing tool definitions.

This module provides callback-based instrumentation for LangChain that captures
tool definitions, which are not available through LangSmith's OTEL integration.

The approach is based on MLflow's LangChain instrumentation:
- Patches BaseCallbackManager.__init__ to inject a callback handler
- Captures tool definitions from kwargs.invocation_params.tools in on_chat_model_start()
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from opentelemetry.trace import SpanKind

from .llm_providers.semconv import (
    INPUT_MESSAGES,
    INPUT_TOKENS,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    OUTPUT_TOKENS,
    PROVIDER_NAME,
    REQUEST_MODEL,
    RESPONSE_FINISH_REASONS,
    RESPONSE_MODEL,
    SYSTEM_INSTRUCTIONS,
    TOOL_DEFINITIONS,
)

if TYPE_CHECKING:
    from ..main import Logfire


# Import BaseCallbackHandler at runtime to get all required attributes
try:
    from langchain_core.callbacks.base import BaseCallbackHandler

    _BASE_CLASS = BaseCallbackHandler
except ImportError:
    _BASE_CLASS = object  # Fallback if langchain_core not installed


class LogfireLangchainCallbackHandler(_BASE_CLASS):  # type: ignore[misc]
    """LangChain callback handler that captures traces with tool definitions.

    This handler is injected into LangChain's callback system to capture:
    - Tool definitions (gen_ai.tool.definitions) - THE KEY FEATURE
    - Input/output messages in OTel format
    - Token usage
    - Model information
    """

    def __init__(self, logfire: Logfire):
        super().__init__()  # Initialize BaseCallbackHandler
        self.run_inline = True  # Run in main async task for proper context propagation
        self._logfire = logfire
        self._run_span_mapping: dict[str, Any] = {}  # run_id -> span

    def _get_span_by_run_id(self, run_id: UUID) -> Any:
        return self._run_span_mapping.get(str(run_id))

    def _extract_tool_definitions(self, kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool definitions from invocation_params.tools.

        Handles both OpenAI and Anthropic tool formats.
        """
        raw_tools = kwargs.get('invocation_params', {}).get('tools', [])
        tools = []
        for raw_tool in raw_tools:
            # OpenAI format: {"type": "function", "function": {...}}
            if raw_tool.get('type') == 'function':
                tools.append(raw_tool)
            # Anthropic format: {"name": "...", "description": "...", "input_schema": {...}}
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

    def _guess_provider(self, model: str) -> str:
        """Guess provider from model name."""
        model_lower = model.lower()
        if 'gpt' in model_lower or 'openai' in model_lower or 'o1' in model_lower or 'o3' in model_lower:
            return 'openai'
        elif 'claude' in model_lower or 'anthropic' in model_lower:
            return 'anthropic'
        elif 'gemini' in model_lower or 'google' in model_lower:
            return 'google'
        return 'unknown'

    def _convert_messages_to_otel(self, messages: list[list[Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
                        system_instructions.extend(content)
                else:
                    otel_role = {'human': 'user', 'ai': 'assistant', 'tool': 'tool'}.get(msg_type, msg_type)
                    parts: list[dict[str, Any]] = []

                    if isinstance(content, str):
                        parts.append({'type': 'text', 'content': content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                parts.append(item)
                            elif isinstance(item, str):
                                parts.append({'type': 'text', 'content': item})

                    input_msgs.append({'role': otel_role, 'parts': parts})

        return input_msgs, system_instructions

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
        """Called when a chat model starts - THIS IS WHERE TOOLS ARE AVAILABLE."""
        invocation_params = kwargs.get('invocation_params', {})
        model = invocation_params.get('model', invocation_params.get('model_name', 'unknown'))

        span_data: dict[str, Any] = {
            OPERATION_NAME: 'chat',
            REQUEST_MODEL: model,
            PROVIDER_NAME: self._guess_provider(model),
        }

        # THE KEY FEATURE: Extract tool definitions
        if tools := self._extract_tool_definitions(kwargs):
            span_data[TOOL_DEFINITIONS] = tools

        # Convert input messages to OTel format
        try:
            input_msgs, system_instructions = self._convert_messages_to_otel(messages)
            if input_msgs:
                span_data[INPUT_MESSAGES] = input_msgs
            if system_instructions:
                span_data[SYSTEM_INSTRUCTIONS] = system_instructions
        except Exception:
            pass  # Don't fail if message conversion fails

        # Start span (use _start() without _attach() to avoid async context issues)
        span = self._logfire.span(
            f'Chat {model}',
            _span_kind=SpanKind.CLIENT,
            **span_data,
        )
        span._start()  # Don't attach to context - avoids async context token errors
        self._run_span_mapping[str(run_id)] = span

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

        span_data: dict[str, Any] = {
            OPERATION_NAME: 'completion',
            REQUEST_MODEL: model,
            PROVIDER_NAME: self._guess_provider(model),
        }

        # Extract tool definitions (may be present for function-calling models)
        if tools := self._extract_tool_definitions(kwargs):
            span_data[TOOL_DEFINITIONS] = tools

        # Start span (use _start() without _attach() to avoid async context issues)
        span = self._logfire.span(
            f'LLM {model}',
            _span_kind=SpanKind.CLIENT,
            **span_data,
        )
        span._start()  # Don't attach to context - avoids async context token errors
        self._run_span_mapping[str(run_id)] = span

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
            # Extract response data
            generations = getattr(response, 'generations', [[]])
            if generations and generations[0]:
                gen = generations[0][0]
                message = getattr(gen, 'message', None)
                if message:
                    # Extract finish reason
                    response_metadata = getattr(message, 'response_metadata', {}) or {}
                    if stop_reason := response_metadata.get('stop_reason', response_metadata.get('finish_reason')):
                        span.set_attribute(RESPONSE_FINISH_REASONS, json.dumps([stop_reason]))

                    # Extract model
                    if model_name := response_metadata.get('model_name', response_metadata.get('model')):
                        span.set_attribute(RESPONSE_MODEL, model_name)

                    # Extract output message
                    content = getattr(message, 'content', '')
                    output_msg: dict[str, Any] = {'role': 'assistant', 'parts': []}

                    if isinstance(content, str):
                        output_msg['parts'].append({'type': 'text', 'content': content})
                    elif isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                output_msg['parts'].append(item)
                            elif isinstance(item, str):
                                output_msg['parts'].append({'type': 'text', 'content': item})

                    # Handle tool calls
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

            # Extract token usage
            llm_output = getattr(response, 'llm_output', {}) or {}
            usage = llm_output.get('usage') or llm_output.get('token_usage') or {}
            if input_tokens := usage.get('input_tokens', usage.get('prompt_tokens')):
                span.set_attribute(INPUT_TOKENS, input_tokens)
            if output_tokens := usage.get('output_tokens', usage.get('completion_tokens')):
                span.set_attribute(OUTPUT_TOKENS, output_tokens)
        except Exception:
            pass  # Don't fail on response parsing errors
        finally:
            span._end()  # End span without detaching (we never attached)
            self._run_span_mapping.pop(str(run_id), None)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        """Called when LLM errors."""
        span = self._get_span_by_run_id(run_id)
        if span:
            # Record exception and end span (without detaching since we never attached)
            if span._span and span._span.is_recording():
                span._span.record_exception(error, escaped=True)
            span._end()
            self._run_span_mapping.pop(str(run_id), None)

    # Chain callbacks - pass through for now
    def on_chain_start(
        self, serialized: dict[str, Any], inputs: dict[str, Any], *, run_id: UUID, **kwargs: Any
    ) -> None:
        pass

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    # Tool callbacks - pass through for now
    def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    # Retriever callbacks - pass through for now
    def on_retriever_start(self, serialized: dict[str, Any], query: str, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_retriever_end(self, documents: Any, *, run_id: UUID, **kwargs: Any) -> None:
        pass

    def on_retriever_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        pass


# Global state for patching
_original_callback_manager_init: Any = None
_logfire_instance: Logfire | None = None


def _patch_callback_manager(logfire: Logfire) -> None:
    """Patch BaseCallbackManager to inject our handler."""
    global _original_callback_manager_init, _logfire_instance

    try:
        from langchain_core.callbacks import BaseCallbackManager
    except ImportError as e:
        raise ImportError(
            'langchain-core is required for LangChain instrumentation. Install it with: pip install langchain-core'
        ) from e

    if _original_callback_manager_init is not None:
        return  # Already patched

    _logfire_instance = logfire
    _original_callback_manager_init = BaseCallbackManager.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        _original_callback_manager_init(self, *args, **kwargs)

        # Check if our handler is already present
        for handler in self.inheritable_handlers:
            if isinstance(handler, LogfireLangchainCallbackHandler):
                return

        # Inject our handler
        if _logfire_instance is not None:
            handler = LogfireLangchainCallbackHandler(_logfire_instance)
            self.add_handler(handler, inherit=True)

    BaseCallbackManager.__init__ = patched_init


def _unpatch_callback_manager() -> None:
    """Restore original BaseCallbackManager.__init__."""
    global _original_callback_manager_init, _logfire_instance

    if _original_callback_manager_init is None:
        return

    try:
        from langchain_core.callbacks import BaseCallbackManager

        BaseCallbackManager.__init__ = _original_callback_manager_init
    except ImportError:
        pass

    _original_callback_manager_init = None
    _logfire_instance = None


def instrument_langchain(logfire: Logfire) -> AbstractContextManager[None]:
    """Instrument LangChain to capture tool definitions.

    This patches LangChain's BaseCallbackManager to inject a callback handler
    that captures tool definitions and other trace data.

    The patching happens immediately when this function is called.
    Returns a context manager that can be used to uninstrument if needed.

    Args:
        logfire: The Logfire instance to use for creating spans.

    Returns:
        A context manager for optional cleanup/uninstrumentation.
    """
    # Patch immediately when called (like MLflow's autolog)
    _patch_callback_manager(logfire)

    @contextmanager
    def cleanup_context():
        try:
            yield
        finally:
            _unpatch_callback_manager()

    return cleanup_context()
