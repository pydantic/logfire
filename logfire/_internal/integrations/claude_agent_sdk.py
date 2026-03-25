from __future__ import annotations

import functools
import logging
import threading
from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import AbstractContextManager, contextmanager
from contextvars import Token
from typing import TYPE_CHECKING, Any, cast

import claude_agent_sdk
from claude_agent_sdk.types import HookContext, SyncHookJSONOutput
from opentelemetry import context as context_api, trace as trace_api
from opentelemetry.context import Context

from logfire._internal.integrations.llm_providers.semconv import (
    CONVERSATION_ID,
    INPUT_MESSAGES,
    INPUT_TOKENS,
    OPERATION_NAME,
    OUTPUT_MESSAGES,
    OUTPUT_TOKENS,
    PROVIDER_NAME,
    RESPONSE_MODEL,
    SYSTEM_INSTRUCTIONS,
    OutputMessage,
    TextPart,
    ToolCallPart,
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


def _set_parent_span(span: trace_api.Span) -> None:
    _thread_local.parent_span = span


def _get_parent_span() -> trace_api.Span | None:
    return getattr(_thread_local, 'parent_span', None)


def _clear_parent_span() -> None:
    if hasattr(_thread_local, 'parent_span'):
        delattr(_thread_local, 'parent_span')


def _set_logfire_instance(instance: Logfire) -> None:
    _thread_local.logfire_instance = instance


def _get_logfire_instance() -> Logfire | None:
    return getattr(_thread_local, 'logfire_instance', None)


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


def _content_blocks_to_output_messages(content: Any, model: str | None) -> list[OutputMessage]:
    """Convert SDK content block objects into semconv OutputMessages."""
    parts: list[Any] = []
    if not isinstance(content, list):
        return []

    for block in cast(list[Any], content):
        block_type: str = block.__class__.__name__

        if block_type == 'TextBlock':
            parts.append(TextPart(type='text', content=getattr(block, 'text', '')))
        elif block_type == 'ThinkingBlock':
            parts.append(
                {
                    'type': 'thinking',
                    'content': getattr(block, 'thinking', ''),
                    'signature': getattr(block, 'signature', ''),
                }
            )
        elif block_type == 'ToolUseBlock':
            part = ToolCallPart(
                type='tool_call',
                id=getattr(block, 'id', '') or '',
                name=getattr(block, 'name', '') or '',
            )
            tool_input = getattr(block, 'input', None)
            if tool_input is not None:
                part['arguments'] = tool_input
            parts.append(part)
        elif block_type == 'ToolResultBlock':
            tool_content = getattr(block, 'content', None)
            content_text = _extract_tool_result_text(tool_content)
            parts.append(
                {
                    'type': 'tool_call_response',
                    'id': getattr(block, 'tool_use_id', '') or '',
                    'response': content_text,
                }
            )
        else:
            parts.append(block)

    msg = OutputMessage(role='assistant', parts=parts)
    return [msg]


def _extract_tool_result_text(content: Any) -> str:
    """Extract text content from tool result content blocks."""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        items = cast(list[Any], content)
        texts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                d = cast(dict[str, Any], item)
                if d.get('type') == 'text':
                    texts.append(d.get('text', ''))
            elif hasattr(item, 'text'):
                texts.append(getattr(item, 'text', ''))
        return '\n'.join(texts) if texts else str(items)
    return str(content)


def _extract_usage(usage: Any) -> dict[str, int]:
    """Extract usage metrics from a Claude usage object or dict."""
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
    if (v := to_int(get('input_tokens'))) is not None:
        result[INPUT_TOKENS] = v
    if (v := to_int(get('output_tokens'))) is not None:
        result[OUTPUT_TOKENS] = v

    cache_read = to_int(get('cache_read_input_tokens'))
    cache_create = to_int(get('cache_creation_input_tokens'))
    if cache_read is not None:
        result['gen_ai.usage.cache_read.input_tokens'] = cache_read
    if cache_create is not None:
        result['gen_ai.usage.cache_creation.input_tokens'] = cache_create

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
        parent_span = _get_parent_span()
        logfire_instance = _get_logfire_instance()
        if not parent_span or not logfire_instance:
            return {}

        # Create a context with the parent span so the child is properly nested.
        parent_ctx = trace_api.set_span_in_context(parent_span)
        token = context_api.attach(parent_ctx)
        try:
            span = logfire_instance.span(f'execute_tool {tool_name}')
            span.set_attribute(OPERATION_NAME, 'execute_tool')
            span.set_attribute('gen_ai.tool.name', tool_name)
            span.set_attribute('gen_ai.tool.call.id', tool_use_id)
            span.set_attribute('gen_ai.tool.call.arguments', tool_input)
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
            span.set_attribute('gen_ai.tool.call.result', str(tool_response))
        span.__exit__(None, None, None)
        context_api.detach(token)

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
        span.set_attribute('error.type', error)
        span.__exit__(None, None, None)
        context_api.detach(token)

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
        return _noop_context()

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
        span_data: dict[str, Any] = {
            OPERATION_NAME: 'invoke_agent',
            PROVIDER_NAME: 'anthropic',
        }
        if prompt:  # pragma: no branch
            span_data[INPUT_MESSAGES] = [{'role': 'user', 'parts': [TextPart(type='text', content=prompt)]}]
        if hasattr(self, 'options') and self.options:  # pragma: no branch
            system_prompt = getattr(self.options, 'system_prompt', None)
            if system_prompt:
                text = system_prompt if isinstance(system_prompt, str) else str(system_prompt)
                span_data[SYSTEM_INSTRUCTIONS] = [TextPart(type='text', content=text)]

        with logfire_claude.span('invoke_agent', **span_data) as root_span:
            otel_span = root_span._span  # pyright: ignore[reportPrivateUsage]
            if otel_span is not None:
                _set_parent_span(otel_span)
            _set_logfire_instance(logfire_claude)
            turn_tracker = _TurnTracker(logfire_claude)

            try:
                async for msg in original_receive_response(self):
                    msg_type = msg.__class__.__name__

                    with handle_internal_errors:
                        if msg_type == 'AssistantMessage':
                            turn_tracker.start_turn(msg)
                        elif msg_type == 'ResultMessage':  # pragma: no branch
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


@contextmanager
def _noop_context():  # pragma: no cover
    yield


def _inject_tracing_hooks(options: Any) -> None:
    """Inject logfire tracing hooks into ClaudeAgentOptions."""
    if not hasattr(options, 'hooks'):
        return

    hooks: dict[str, list[Any]]
    if options.hooks is None:
        hooks = options.hooks = {}
    else:
        hooks = options.hooks
    for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):
        hooks.setdefault(event, [])

    if getattr(options, '_logfire_hooks_injected', False):
        return

    with handle_internal_errors:
        hooks['PreToolUse'].insert(0, claude_agent_sdk.HookMatcher(matcher=None, hooks=[pre_tool_use_hook]))
        hooks['PostToolUse'].insert(0, claude_agent_sdk.HookMatcher(matcher=None, hooks=[post_tool_use_hook]))
        hooks['PostToolUseFailure'].insert(
            0, claude_agent_sdk.HookMatcher(matcher=None, hooks=[post_tool_use_failure_hook])
        )
        options._logfire_hooks_injected = True


class _TurnTracker:
    """Track assistant turn spans so consecutive turns are recorded as siblings."""

    def __init__(self, logfire_instance: Logfire) -> None:
        self._logfire = logfire_instance
        self._current_span: LogfireSpan | None = None

    def start_turn(self, message: Any) -> None:
        """Close previous turn span if open, open a new one."""
        if self._current_span is not None:
            self._current_span.__exit__(None, None, None)

        model = getattr(message, 'model', None)
        content = getattr(message, 'content', [])
        output_messages = _content_blocks_to_output_messages(content, model)

        span_data: dict[str, Any] = {OPERATION_NAME: 'chat'}
        if model:  # pragma: no branch
            span_data[RESPONSE_MODEL] = model
        if output_messages:  # pragma: no branch
            span_data[OUTPUT_MESSAGES] = output_messages

        span_name = f'chat {model}' if model else 'chat'
        self._current_span = self._logfire.span(span_name, **span_data)
        self._current_span.__enter__()

    def close(self) -> None:
        if self._current_span is not None:
            self._current_span.__exit__(None, None, None)
            self._current_span = None


def _record_result(span: LogfireSpan, msg: Any) -> None:
    """Record ResultMessage data onto the root span."""
    if hasattr(msg, 'usage') and msg.usage:
        usage = _extract_usage(msg.usage)
        for key, value in usage.items():
            span.set_attribute(key, value)

    model = getattr(msg, 'model', None)
    if model:
        span.set_attribute(RESPONSE_MODEL, model)

    if hasattr(msg, 'total_cost_usd') and msg.total_cost_usd is not None:
        span.set_attribute('operation.cost', float(msg.total_cost_usd))

    session_id = getattr(msg, 'session_id', None)
    if session_id is not None:
        span.set_attribute(CONVERSATION_ID, session_id)

    for attr in ('num_turns', 'duration_ms'):
        if (value := getattr(msg, attr, None)) is not None:  # pragma: no branch
            span.set_attribute(attr, value)

    is_error = getattr(msg, 'is_error', None)
    if is_error:
        span.set_level('error')
