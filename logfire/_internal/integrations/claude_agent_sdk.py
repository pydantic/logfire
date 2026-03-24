# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAttributeAccessIssue=false
from __future__ import annotations

import functools
import logging
import threading
import time
from collections.abc import AsyncGenerator, AsyncIterable
from typing import TYPE_CHECKING, Any

from opentelemetry import context as context_api, trace as trace_api

from logfire._internal.utils import handle_internal_errors

if TYPE_CHECKING:
    from logfire._internal.main import Logfire

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
_active_tool_spans: dict[str, Any] = {}


def _set_parent_span(span: Any) -> None:
    _thread_local.parent_span = span


def _get_parent_span() -> Any:
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
    for tool_use_id, (span, token) in _active_tool_spans.items():  # pragma: no cover
        try:
            span.__exit__(None, None, None)
            context_api.detach(token)
        except Exception:
            logger.debug('Failed to clean up orphaned tool span %s', tool_use_id, exc_info=True)
    _active_tool_spans.clear()


# ---------------------------------------------------------------------------
# Utility functions for converting SDK types to serializable dicts.
# ---------------------------------------------------------------------------


def flatten_content_blocks(content: Any) -> Any:
    """Convert SDK content block objects into serializable dicts."""
    if not isinstance(content, list):
        return content

    result: list[Any] = []
    for block in content:
        block_type: str = block.__class__.__name__

        if block_type == 'TextBlock':
            result.append({'type': 'text', 'text': getattr(block, 'text', '')})
        elif block_type == 'ThinkingBlock':
            result.append(
                {
                    'type': 'thinking',
                    'thinking': getattr(block, 'thinking', ''),
                    'signature': getattr(block, 'signature', ''),
                }
            )
        elif block_type == 'ToolUseBlock':
            result.append(
                {
                    'type': 'tool_use',
                    'id': getattr(block, 'id', None),
                    'name': getattr(block, 'name', None),
                    'input': getattr(block, 'input', None),
                }
            )
        elif block_type == 'ToolResultBlock':
            tool_content = getattr(block, 'content', None)
            content_text = _extract_tool_result_text(tool_content)
            result.append(
                {
                    'type': 'tool_result',
                    'tool_use_id': getattr(block, 'tool_use_id', None),
                    'content': content_text,
                    'is_error': getattr(block, 'is_error', False),
                }
            )
        else:
            result.append(block)
    return result


def _extract_tool_result_text(content: Any) -> str:
    """Extract text content from tool result content blocks."""
    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
            elif hasattr(item, 'text'):  # pragma: no branch
                texts.append(getattr(item, 'text', ''))
        return '\n'.join(texts) if texts else str(content)
    return str(content)


def extract_usage_metadata(usage: Any) -> Any:
    """Extract and normalize usage metrics from a Claude usage object or dict."""
    if not usage:
        return {}

    get = usage.get if isinstance(usage, dict) else lambda k: getattr(usage, k, None)  # pyright: ignore[reportUnknownLambdaType]

    def to_int(value: Any) -> int | None:
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    meta: dict[str, Any] = {}
    if (v := to_int(get('input_tokens'))) is not None:
        meta['input_tokens'] = v
    if (v := to_int(get('output_tokens'))) is not None:
        meta['output_tokens'] = v

    cache_read = to_int(get('cache_read_input_tokens'))
    cache_create = to_int(get('cache_creation_input_tokens'))
    if cache_read is not None or cache_create is not None:
        meta['input_token_details'] = {}
        if cache_read is not None:
            meta['input_token_details']['cache_read'] = cache_read
        if cache_create is not None:
            meta['input_token_details']['cache_creation'] = cache_create

    return meta


def get_usage_from_result(usage: Any) -> Any:
    """Extract usage metadata and compute totals."""
    metrics = extract_usage_metadata(usage)
    if not metrics:
        return {}

    details = metrics.get('input_token_details') or {}
    cache_read = details.get('cache_read', 0) or 0
    cache_create = details.get('cache_creation', 0) or 0

    input_tokens = (metrics.get('input_tokens') or 0) + cache_read + cache_create
    output_tokens = metrics.get('output_tokens') or 0

    return {
        **metrics,
        'input_tokens': input_tokens,
        'total_tokens': input_tokens + output_tokens,
    }


# ---------------------------------------------------------------------------
# Hook callbacks for tool call tracing.
# ---------------------------------------------------------------------------


async def pre_tool_use_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: Any,
) -> Any:
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
            span = logfire_instance.span(tool_name, tool_input=tool_input)
            span.__enter__()
            _active_tool_spans[tool_use_id] = (span, token)
        except Exception:  # pragma: no cover
            context_api.detach(token)
            raise

    return {}


async def post_tool_use_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: Any,
) -> Any:
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
            span.set_attribute('tool_response', str(tool_response))
        span.__exit__(None, None, None)
        context_api.detach(token)

    return {}


async def post_tool_use_failure_hook(
    input_data: Any,
    tool_use_id: str | None,
    _context: Any,
) -> Any:
    """End the tool span with an error after failed execution."""
    if not tool_use_id:
        return {}

    with handle_internal_errors:
        entry = _active_tool_spans.pop(tool_use_id, None)
        if not entry:
            return {}

        span, token = entry
        error = str(input_data.get('error', 'Unknown error'))
        span.set_attribute('error', error)
        span.__exit__(None, None, None)
        context_api.detach(token)

    return {}


# ---------------------------------------------------------------------------
# Instrumentation entry point.
# ---------------------------------------------------------------------------


def instrument_claude_agent_sdk(logfire_instance: Logfire) -> None:
    """Instrument the Claude Agent SDK by monkey-patching ClaudeSDKClient."""
    import claude_agent_sdk

    cls = claude_agent_sdk.ClaudeSDKClient

    if getattr(cls, '_is_instrumented_by_logfire', False):
        return
    cls._is_instrumented_by_logfire = True

    logfire_claude = logfire_instance.with_settings(custom_scope_suffix='claude-agent-sdk', tags=['LLM'])

    # --- Patch __init__ ---
    original_init = cls.__init__

    @functools.wraps(original_init)
    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        original_init(self, *args, **kwargs)

        self._logfire_prompt = None
        self._logfire_start_time = None
        self._logfire_streamed_input = None

        options = kwargs.get('options') or (args[0] if args else None)
        if options:
            _inject_tracing_hooks(options)

    cls.__init__ = patched_init
    # --- Patch query ---
    original_query = cls.query

    @functools.wraps(original_query)
    async def patched_query(self: Any, *args: Any, **kwargs: Any) -> Any:
        self._logfire_start_time = time.time()
        self._logfire_streamed_input = None
        prompt = args[0] if args else kwargs.get('prompt')

        if prompt is None:
            pass
        elif isinstance(prompt, str):
            self._logfire_prompt = prompt
        elif isinstance(prompt, AsyncIterable):  # pragma: no cover
            collector: list[dict[str, Any]] = []
            self._logfire_streamed_input = collector
            self._logfire_prompt = None

            async def _gen_wrapper() -> AsyncGenerator[dict[str, Any], None]:
                async for msg in prompt:
                    collector.append(msg)
                    yield msg

            if args:
                args = (_gen_wrapper(),) + args[1:]
            else:
                kwargs['prompt'] = _gen_wrapper()
        else:
            self._logfire_prompt = str(prompt)

        return await original_query(self, *args, **kwargs)

    cls.query = patched_query
    # --- Patch receive_response ---
    original_receive_response = cls.receive_response

    @functools.wraps(original_receive_response)
    async def patched_receive_response(self: Any) -> AsyncGenerator[Any, None]:
        prompt = getattr(self, '_logfire_prompt', None)
        span_data: dict[str, Any] = {}
        if prompt:
            span_data['prompt'] = prompt
        if hasattr(self, 'options') and self.options:
            system_prompt = getattr(self.options, 'system_prompt', None)
            if system_prompt:
                if isinstance(system_prompt, str):
                    span_data['system_prompt'] = system_prompt
                else:
                    span_data['system_prompt'] = str(system_prompt)

        with logfire_claude.span('claude.conversation', **span_data) as root_span:
            _set_parent_span(root_span._span)  # pyright: ignore[reportPrivateUsage]
            _set_logfire_instance(logfire_claude)
            turn_tracker = _TurnTracker(logfire_claude, getattr(self, '_logfire_start_time', None))

            try:
                async for msg in original_receive_response(self):
                    msg_type = msg.__class__.__name__

                    with handle_internal_errors:
                        if msg_type == 'AssistantMessage':
                            turn_tracker.start_turn(msg)
                        elif msg_type == 'UserMessage':
                            turn_tracker.mark_next_start()
                        elif msg_type == 'ResultMessage':
                            _record_result(root_span, msg)

                    yield msg
            finally:
                turn_tracker.close()
                _clear_parent_span()
                _clear_active_tool_spans()

    cls.receive_response = patched_receive_response


def _inject_tracing_hooks(options: Any) -> None:
    """Inject logfire tracing hooks into ClaudeAgentOptions."""
    if not hasattr(options, 'hooks'):
        return

    if options.hooks is None:
        options.hooks = {}

    for event in ('PreToolUse', 'PostToolUse', 'PostToolUseFailure'):  # pragma: no branch
        if event not in options.hooks:
            options.hooks[event] = []

    if getattr(options, '_logfire_hooks_injected', False):
        return

    with handle_internal_errors:
        from claude_agent_sdk import HookMatcher

        options.hooks['PreToolUse'].insert(0, HookMatcher(matcher=None, hooks=[pre_tool_use_hook]))
        options.hooks['PostToolUse'].insert(0, HookMatcher(matcher=None, hooks=[post_tool_use_hook]))
        options.hooks['PostToolUseFailure'].insert(0, HookMatcher(matcher=None, hooks=[post_tool_use_failure_hook]))
        options._logfire_hooks_injected = True


class _TurnTracker:
    """Track assistant turn spans so consecutive turns are recorded as siblings."""

    def __init__(self, logfire_instance: Logfire, start_time: float | None = None) -> None:
        self._logfire = logfire_instance
        self._current_span: Any | None = None
        self._next_start_time: float | None = start_time

    def start_turn(self, message: Any) -> None:
        """Close previous turn span if open, open a new one."""
        if self._current_span is not None:
            self._current_span.__exit__(None, None, None)

        content = flatten_content_blocks(getattr(message, 'content', []))
        model = getattr(message, 'model', None)

        span_data: dict[str, Any] = {}
        if content:
            span_data['content'] = content
        if model:
            span_data['model'] = model

        self._current_span = self._logfire.span('claude.assistant.turn', **span_data)
        self._current_span.__enter__()
        self._next_start_time = None

    def mark_next_start(self) -> None:
        self._next_start_time = time.time()

    def close(self) -> None:
        if self._current_span is not None:
            self._current_span.__exit__(None, None, None)
            self._current_span = None


def _record_result(span: Any, msg: Any) -> None:
    """Record ResultMessage data onto the root span."""
    if hasattr(msg, 'usage') and msg.usage:
        usage = get_usage_from_result(msg.usage)
        for key, value in usage.items():
            if key == 'input_token_details':
                for detail_key, detail_value in value.items():
                    span.set_attribute(f'usage.{key}.{detail_key}', detail_value)
            else:
                span.set_attribute(f'usage.{key}', value)

    if hasattr(msg, 'total_cost_usd') and msg.total_cost_usd is not None:
        span.set_attribute('total_cost_usd', msg.total_cost_usd)

    for attr in ('num_turns', 'session_id', 'duration_ms', 'is_error'):
        if (value := getattr(msg, attr, None)) is not None:
            span.set_attribute(attr, value)
