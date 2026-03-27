from __future__ import annotations

import functools
import logging
import threading
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import Token
from typing import TYPE_CHECKING, Any, cast

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import HookContext, SyncHookJSONOutput
from opentelemetry import context as context_api, trace as trace_api
from opentelemetry.context import Context

from logfire._internal.integrations.llm_providers.semconv import (
    CACHE_CREATION_INPUT_TOKENS,
    CACHE_READ_INPUT_TOKENS,
    CONVERSATION_ID,
    ERROR_TYPE,
    INPUT_MESSAGES,
    INPUT_TOKENS,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    OUTPUT_TOKENS,
    PROVIDER_NAME,
    RESPONSE_MODEL,
    SYSTEM,
    SYSTEM_INSTRUCTIONS,
    TOOL_CALL_ARGUMENTS,
    TOOL_CALL_ID,
    TOOL_CALL_RESULT,
    TOOL_NAME,
    ChatMessage,
    MessagePart,
    OutputMessage,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolCallResponsePart,
)
from logfire._internal.utils import handle_internal_errors

if TYPE_CHECKING:
    from logfire._internal.main import Logfire, LogfireSpan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-local storage for parent span and logfire instance.
#
# The Claude Agent SDK uses anyio internally, and anyio tasks don't propagate
# contextvars from the parent. This means OTel's context propagation breaks
# for hook callbacks. We use threading.local() as a workaround.
# ---------------------------------------------------------------------------
_thread_local = threading.local()

# Active tool spans, keyed by tool_use_id.
_active_tool_spans: dict[str, tuple[LogfireSpan, Token[Context]]] = {}


def _set_parent_span(span: LogfireSpan) -> None:
    _thread_local.parent_span = span


def _get_parent_span() -> LogfireSpan | None:
    return getattr(_thread_local, 'parent_span', None)


def _clear_parent_span() -> None:
    if hasattr(_thread_local, 'parent_span'):
        delattr(_thread_local, 'parent_span')


def _set_logfire_instance(instance: Logfire) -> None:
    _thread_local.logfire_instance = instance


def _get_logfire_instance() -> Logfire | None:
    return getattr(_thread_local, 'logfire_instance', None)


def _set_turn_tracker(tracker: _TurnTracker) -> None:
    _thread_local.turn_tracker = tracker


def _get_turn_tracker() -> _TurnTracker | None:
    return getattr(_thread_local, 'turn_tracker', None)


def _clear_active_tool_spans() -> None:
    """End any orphaned tool spans and clear the dict."""
    for tool_use_id, (span, token) in _active_tool_spans.items():
        try:
            span.__exit__(None, None, None)
            context_api.detach(token)
        except Exception:
            logger.debug('Failed to clean up orphaned tool span %s', tool_use_id, exc_info=True)
    _active_tool_spans.clear()


# ---------------------------------------------------------------------------
# Utility functions for converting SDK types to semconv part dicts.
# ---------------------------------------------------------------------------


def _content_blocks_to_output_messages(content: Any) -> list[OutputMessage]:
    """Convert SDK content block objects into semconv OutputMessages."""
    parts: list[MessagePart] = []
    if not isinstance(content, list):
        return []

    for block in cast('list[TextBlock | ThinkingBlock | ToolUseBlock | ToolResultBlock | Any]', content):
        if isinstance(block, TextBlock):
            parts.append(TextPart(type='text', content=block.text))
        elif isinstance(block, ThinkingBlock):
            parts.append(ReasoningPart(type='reasoning', content=block.thinking))
        elif isinstance(block, ToolUseBlock):
            part = ToolCallPart(
                type='tool_call',
                id=block.id or '',
                name=block.name or '',
            )
            part['arguments'] = block.input
            parts.append(part)
        elif isinstance(block, ToolResultBlock):
            parts.append(
                ToolCallResponsePart(
                    type='tool_call_response',
                    id=block.tool_use_id or '',
                    response=block.content,  # type: ignore
                )
            )
        else:
            parts.append(block)

    msg = OutputMessage(role='assistant', parts=parts)
    return [msg]


def _extract_usage(usage: Any, *, include_output_tokens: bool = True) -> dict[str, int]:
    """Extract usage metrics from a Claude usage object or dict.

    Args:
        usage: A usage object or dict from the SDK.
        include_output_tokens: Whether to include output_tokens. Set to False for
            chat spans where the SDK reports unreliable per-message output_tokens.
    """
    if not usage:
        return {}

    def get(key: str) -> Any:
        if isinstance(usage, dict):
            return cast(dict[str, Any], usage).get(key)
        return getattr(usage, key, None)

    def to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    result: dict[str, int] = {}

    # gen_ai.usage.input_tokens is the *total* input token count.
    # The Anthropic API's input_tokens only counts uncached tokens,
    # so we sum input + cache_read + cache_creation to get the actual total.
    input_tokens = to_int(get('input_tokens')) or 0
    cache_read = to_int(get('cache_read_input_tokens')) or 0
    cache_creation = to_int(get('cache_creation_input_tokens')) or 0
    total_input = input_tokens + cache_read + cache_creation
    if total_input:
        result[INPUT_TOKENS] = total_input

    if include_output_tokens:
        if (v := to_int(get('output_tokens'))) is not None:
            result[OUTPUT_TOKENS] = v

    if cache_read:
        result[CACHE_READ_INPUT_TOKENS] = cache_read
    if cache_creation:
        result[CACHE_CREATION_INPUT_TOKENS] = cache_creation

    return result


# ---------------------------------------------------------------------------
# Hook callbacks for tool call tracing.
# ---------------------------------------------------------------------------


async def pre_tool_use_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: HookContext,
) -> SyncHookJSONOutput:
    """Create a child span when a tool execution starts."""
    if not tool_use_id:
        return {}

    tool_name = str(input_data.get('tool_name', 'unknown_tool'))
    tool_input = input_data.get('tool_input', {})

    with handle_internal_errors:
        # Close the current chat span so it doesn't overlap with tool execution.
        turn_tracker = _get_turn_tracker()
        if turn_tracker is not None:
            turn_tracker.close_chat_span()

        parent_span = _get_parent_span()
        logfire_instance = _get_logfire_instance()
        if not parent_span or not logfire_instance:
            return {}

        # Create a context with the parent span so the child is properly nested.
        otel_span = parent_span._span  # pyright: ignore[reportPrivateUsage]
        if otel_span is None:  # pragma: no cover
            return {}
        parent_ctx = trace_api.set_span_in_context(otel_span)
        token = context_api.attach(parent_ctx)
        try:
            span_name = f'execute_tool {tool_name}'
            span = logfire_instance.span(span_name)
            span.set_attributes(
                {
                    OPERATION_NAME: 'execute_tool',
                    TOOL_NAME: tool_name,
                    TOOL_CALL_ID: tool_use_id,
                    TOOL_CALL_ARGUMENTS: tool_input,
                }
            )
            span.__enter__()
            _active_tool_spans[tool_use_id] = (span, token)
        except Exception:  # pragma: no cover
            context_api.detach(token)
            raise

    return {}


async def post_tool_use_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: HookContext,
) -> SyncHookJSONOutput:
    """End the tool span after successful execution."""
    if not tool_use_id:
        return {}

    with handle_internal_errors:
        entry = _active_tool_spans.pop(tool_use_id, None)
        if not entry:
            return {}

        span, token = entry
        tool_response = input_data.get('tool_response')
        if tool_response is not None:
            span.set_attribute(TOOL_CALL_RESULT, str(tool_response))
        span.__exit__(None, None, None)
        context_api.detach(token)

        # Record tool result for the next chat span's input messages
        turn_tracker = _get_turn_tracker()
        if turn_tracker is not None:
            tool_name = str(input_data.get('tool_name', 'unknown_tool'))
            turn_tracker.add_tool_result(
                tool_use_id, tool_name, str(tool_response) if tool_response is not None else ''
            )

    return {}


async def post_tool_use_failure_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: HookContext,
) -> SyncHookJSONOutput:
    """End the tool span with an error after failed execution."""
    if not tool_use_id:
        return {}

    with handle_internal_errors:
        entry = _active_tool_spans.pop(tool_use_id, None)
        if not entry:
            return {}

        span, token = entry
        error = str(input_data.get('error', 'Unknown error'))
        span.set_attribute(ERROR_TYPE, error)
        span.set_level('error')
        span.__exit__(None, None, None)
        context_api.detach(token)

        # Record the error as a tool result so the next turn's input is complete.
        turn_tracker = _get_turn_tracker()
        if turn_tracker is not None:  # pragma: no cover
            tool_name = str(input_data.get('tool_name', 'unknown_tool'))
            turn_tracker.add_tool_result(tool_use_id, tool_name, error)

    return {}


# ---------------------------------------------------------------------------
# Instrumentation entry point.
# ---------------------------------------------------------------------------


def instrument_claude_agent_sdk(logfire_instance: Logfire) -> AbstractContextManager[None]:
    """Instrument the Claude Agent SDK by monkey-patching ClaudeSDKClient.

    Returns:
        A context manager that will revert the instrumentation when exited.
            This context manager doesn't take into account threads or other concurrency.
            Calling this function will immediately apply the instrumentation
            without waiting for the context manager to be opened,
            i.e. it's not necessary to use this as a context manager.
    """
    cls = claude_agent_sdk.ClaudeSDKClient

    if getattr(cls, '_is_instrumented_by_logfire', False):
        return nullcontext()

    original_init = cls.__init__
    original_query = cls.query
    original_receive_response = cls.receive_response

    cls._is_instrumented_by_logfire = True  # pyright: ignore[reportAttributeAccessIssue]

    logfire_claude = logfire_instance.with_settings(custom_scope_suffix='claude_agent_sdk')

    # --- Patch __init__ ---
    @functools.wraps(original_init)
    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)

        self._logfire_prompt = None

        if self.options:  # pragma: no branch
            _inject_tracing_hooks(self.options)

    cls.__init__ = patched_init

    # --- Patch query ---
    @functools.wraps(original_query)
    async def patched_query(self: Any, *args: Any, **kwargs: Any) -> Any:
        self._logfire_prompt = None
        prompt = args[0] if args else kwargs.get('prompt')

        if isinstance(prompt, str):
            self._logfire_prompt = prompt
        elif prompt is not None and not isinstance(prompt, AsyncIterable):  # pragma: no cover
            self._logfire_prompt = str(prompt)

        return await original_query(self, *args, **kwargs)

    cls.query = patched_query

    # --- Patch receive_response ---
    @functools.wraps(original_receive_response)
    async def patched_receive_response(self: Any) -> AsyncGenerator[Any, None]:
        prompt = getattr(self, '_logfire_prompt', None)
        input_messages: list[ChatMessage] = []
        if prompt:  # pragma: no branch
            input_messages = [ChatMessage(role='user', parts=[TextPart(type='text', content=prompt)])]

        span_data: dict[str, Any] = {
            OPERATION_NAME: 'invoke_agent',
            PROVIDER_NAME: 'anthropic',
            SYSTEM: 'anthropic',
        }
        if input_messages:  # pragma: no branch
            span_data[INPUT_MESSAGES] = input_messages
        if hasattr(self, 'options') and self.options:  # pragma: no branch
            system_prompt = getattr(self.options, 'system_prompt', None)
            if system_prompt:  # pragma: no branch
                text = str(system_prompt)
                span_data[SYSTEM_INSTRUCTIONS] = [TextPart(type='text', content=text)]

        with logfire_claude.span('invoke_agent', **span_data) as root_span:
            _set_parent_span(root_span)
            _set_logfire_instance(logfire_claude)
            turn_tracker = _TurnTracker(logfire_claude, input_messages)
            _set_turn_tracker(turn_tracker)
            # Open the first chat span now — the LLM call starts at query time.
            turn_tracker.open_chat_span()

            try:
                async for msg in original_receive_response(self):
                    with handle_internal_errors:
                        if isinstance(msg, AssistantMessage):
                            turn_tracker.handle_assistant_message(msg)
                        elif isinstance(msg, UserMessage):
                            turn_tracker.handle_user_message()
                        elif isinstance(msg, ResultMessage):  # pragma: no branch
                            _record_result(root_span, msg)

                    yield msg
            finally:
                turn_tracker.close()
                _clear_parent_span()
                _clear_active_tool_spans()

    cls.receive_response = patched_receive_response

    @contextmanager
    def uninstrument_context():
        try:
            yield
        finally:
            cls.__init__ = original_init
            cls.query = original_query
            cls.receive_response = original_receive_response
            cls._is_instrumented_by_logfire = False  # pyright: ignore[reportAttributeAccessIssue]

    return uninstrument_context()


def _inject_tracing_hooks(options: Any) -> None:
    """Inject logfire tracing hooks into ClaudeAgentOptions.

    Guards against duplicate injection when the same options object is reused
    across multiple ClaudeSDKClient instances.
    """
    if not hasattr(options, 'hooks'):
        return

    hooks: dict[str, list[HookMatcher]]
    if options.hooks is None:
        hooks = options.hooks = {}
    else:
        hooks = options.hooks
    with handle_internal_errors:
        # Guard against duplicate injection when the same options object is reused.
        if getattr(options, '_logfire_hooks_injected', False):  # pragma: no cover
            return
        options._logfire_hooks_injected = True

        for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):
            hooks.setdefault(event, [])
        hooks['PreToolUse'].insert(0, HookMatcher(matcher=None, hooks=[pre_tool_use_hook]))
        hooks['PostToolUse'].insert(0, HookMatcher(matcher=None, hooks=[post_tool_use_hook]))
        hooks['PostToolUseFailure'].insert(0, HookMatcher(matcher=None, hooks=[post_tool_use_failure_hook]))


class _TurnTracker:
    """Track chat spans whose lifetime approximates the LLM API call duration.

    Span lifecycle:
    - **Open** when the LLM call starts: at query time (first turn) or when a
      UserMessage arrives (subsequent turns — tool results sent back to model).
    - **Populated** when AssistantMessage(s) arrive with output content and usage.
      Consecutive AssistantMessages from the same API call are merged into the
      open span rather than creating new ones.
    - **Closed** when the next turn opens, or at close().
    """

    def __init__(self, logfire_instance: Logfire, initial_input_messages: list[ChatMessage]) -> None:
        self._logfire = logfire_instance
        self._current_span: LogfireSpan | None = None
        # Running conversation history — each chat span gets the full history as input.
        self._history: list[ChatMessage] = list(initial_input_messages)
        # Track current span's output parts for merging consecutive messages.
        self._current_output_parts: list[MessagePart] = []

    def add_tool_result(self, tool_use_id: str, tool_name: str, result: str) -> None:
        """Record a tool result to include in the next chat span's input messages."""
        msg = ChatMessage(
            role='tool',
            parts=[ToolCallResponsePart(type='tool_call_response', id=tool_use_id, name=tool_name, response=result)],
        )
        self._history.append(msg)

    def open_chat_span(self) -> None:
        """Open a new chat span — call when the LLM starts processing."""
        self.close_chat_span()

        span_data: dict[str, Any] = {
            OPERATION_NAME: 'chat',
            PROVIDER_NAME: 'anthropic',
            SYSTEM: 'anthropic',
        }
        if self._history:  # pragma: no branch
            span_data[INPUT_MESSAGES] = list(self._history)

        self._current_span = self._logfire.span('chat', **span_data)
        # Start without entering context — chat spans don't need to be on the
        # context stack, and this allows close_chat_span() to be called safely
        # from hooks running in different async contexts.
        self._current_span._start()  # pyright: ignore[reportPrivateUsage]
        self._current_output_parts = []

    def close_chat_span(self) -> None:
        """Close the current chat span without opening a new one.

        Safe to call from hooks (different async contexts) because chat spans
        are never entered into the OTel context stack.
        """
        if self._current_span is not None:
            if self._current_output_parts:  # pragma: no branch
                self._history.append(ChatMessage(role='assistant', parts=list(self._current_output_parts)))
            self._current_span._end()  # pyright: ignore[reportPrivateUsage]
            self._current_span = None
            self._current_output_parts = []

    def handle_user_message(self) -> None:
        """Handle UserMessage: open a new chat span for the next LLM call."""
        self.open_chat_span()

    def handle_assistant_message(self, message: AssistantMessage) -> None:
        """Handle AssistantMessage: add output and usage to the current chat span."""
        if self._current_span is None:  # pragma: no cover
            return

        content = getattr(message, 'content', [])
        output_messages = _content_blocks_to_output_messages(content)
        new_parts = output_messages[0]['parts'] if output_messages else []

        self._current_output_parts.extend(new_parts)
        self._current_span.set_attribute(
            OUTPUT_MESSAGES, [OutputMessage(role='assistant', parts=self._current_output_parts)]
        )

        model = getattr(message, 'model', None)
        if model:  # pragma: no branch
            self._current_span.set_attribute(RESPONSE_MODEL, model)
            # Update span name to include model.
            self._current_span.message = f'chat {model}'

        usage = getattr(message, 'usage', None)
        if usage:  # pragma: no branch
            self._current_span.set_attributes(_extract_usage(usage, include_output_tokens=False))

        error = getattr(message, 'error', None)
        if error:  # pragma: no cover
            self._current_span.set_attribute(ERROR_TYPE, str(error))
            self._current_span.set_level('error')

    def close(self) -> None:
        self.close_chat_span()


def _record_result(span: LogfireSpan, msg: ResultMessage) -> None:
    """Record ResultMessage data onto the root span."""
    attrs: dict[str, Any] = {}

    if hasattr(msg, 'usage') and msg.usage:  # pragma: no branch
        attrs.update(_extract_usage(msg.usage))

    if hasattr(msg, 'total_cost_usd') and msg.total_cost_usd is not None:  # pragma: no branch
        attrs['operation.cost'] = float(msg.total_cost_usd)

    session_id = getattr(msg, 'session_id', None)
    if session_id is not None:  # pragma: no branch
        attrs[CONVERSATION_ID] = session_id

    for attr in ('num_turns', 'duration_ms'):
        if (value := getattr(msg, attr, None)) is not None:  # pragma: no branch
            attrs[attr] = value

    span.set_attributes(attrs)

    is_error = getattr(msg, 'is_error', None)
    if is_error:  # pragma: no cover
        span.set_level('error')
