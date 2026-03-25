# pyright: reportPrivateUsage=false
"""Tests for Claude Agent SDK (native) instrumentation.

This tests the native ``claude_agent_sdk`` integration
(``logfire.instrument_claude_agent_sdk``), which hooks into the SDK's
transport layer directly.  ``test_claude_sdk.py`` tests the separate
LangSmith-based integration.

Integration tests use a mock transport to exercise the real SDK client
with instrumented methods, making them resilient to import refactoring.
"""

from __future__ import annotations

import gc
import json
import sys
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import Mock

import anyio
import pytest

pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, Transport
from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.claude_agent_sdk import (
    _active_tool_spans,
    _clear_active_tool_spans,
    _clear_parent_span,
    _content_blocks_to_output_messages,
    _extract_tool_result_text,
    _extract_usage,
    _inject_tracing_hooks,
    _set_logfire_instance,
    _set_parent_span,
    post_tool_use_failure_hook,
    post_tool_use_hook,
    pre_tool_use_hook,
)
from logfire.testing import TestExporter

# The SDK doesn't close anyio MemoryObjectStreams in Query.close(). They get GC'd during
# pytest cleanup, triggering ResourceWarning via __del__. We can't force earlier collection
# with del+gc.collect() because the SDK's internal reference chain keeps them alive until
# the test function's frame is destroyed by pytest.
pytestmark = pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')


# ---------------------------------------------------------------------------
# Mock transport — handles the SDK control protocol, yields predefined messages,
# and dispatches hook callbacks for tool_use blocks.
# ---------------------------------------------------------------------------


class MockTransport(Transport):
    """Mock transport for the Claude Agent SDK.

    Handles the initialize handshake (control_request/response), yields
    predefined response messages after the user query is sent, and dispatches
    hook callbacks for tool_use content blocks via the control protocol.
    """

    def __init__(
        self,
        responses: list[dict[str, Any]],
        *,
        tool_failure_ids: set[str] | None = None,
    ) -> None:
        self.responses = responses
        self.written: list[dict[str, Any]] = []
        self._init_request_id: str | None = None
        self._hook_callback_ids: dict[str, str] = {}
        self._control_response_events: dict[str, Any] = {}  # request_id -> anyio.Event
        self._tool_failure_ids = tool_failure_ids or set()

    async def connect(self) -> None:
        self._init_event = anyio.Event()
        self._query_event = anyio.Event()

    async def write(self, data: str) -> None:
        msg = json.loads(data)
        self.written.append(msg)
        if msg.get('type') == 'control_request':
            self._init_request_id = msg['request_id']
            # Extract hook callback IDs from init config
            hooks_config: dict[str, list[dict[str, Any]]] = msg.get('request', {}).get('hooks') or {}
            for event_name, matchers in hooks_config.items():
                for matcher in matchers:
                    for cb_id in matcher.get('hookCallbackIds', []):
                        self._hook_callback_ids[event_name] = cb_id
            self._init_event.set()
        elif msg.get('type') == 'user':
            self._query_event.set()
        elif msg.get('type') == 'control_response':
            # SDK responding to our hook callback request
            response = msg.get('response', {})
            request_id = response.get('request_id')
            event = self._control_response_events.get(request_id)
            if event is not None:
                event.set()

    def _make_hook_request(
        self, request_id: str, callback_id: str, input_data: dict[str, Any], tool_use_id: str
    ) -> dict[str, Any]:
        return {
            'type': 'control_request',
            'request_id': request_id,
            'request': {
                'subtype': 'hook_callback',
                'callback_id': callback_id,
                'input': input_data,
                'tool_use_id': tool_use_id,
            },
        }

    async def _read_impl(self) -> AsyncIterator[dict[str, Any]]:
        # Wait for initialize request, then respond
        await self._init_event.wait()
        yield {
            'type': 'control_response',
            'response': {
                'subtype': 'success',
                'request_id': self._init_request_id,
                'response': {},
            },
        }
        # Wait for user query, then yield responses
        await self._query_event.wait()
        for msg in self.responses:
            yield msg
            # After yielding an assistant message, dispatch hook callbacks for any tool_use blocks.
            # Yields must be inline here since async generators can't delegate yields.
            if msg.get('type') == 'assistant':
                content: list[dict[str, Any]] = msg.get('message', {}).get('content', [])
                for block in content:
                    if block.get('type') != 'tool_use':
                        continue
                    tool_use_id: str = block['id']
                    tool_name: str = block['name']
                    tool_input: dict[str, Any] = block.get('input', {})
                    is_failure = tool_use_id in self._tool_failure_ids

                    # PreToolUse hook
                    pre_cb = self._hook_callback_ids.get('PreToolUse')
                    if pre_cb:
                        req_id = f'hook_pre_{tool_use_id}'
                        event = anyio.Event()
                        self._control_response_events[req_id] = event
                        yield self._make_hook_request(
                            req_id,
                            pre_cb,
                            {
                                'hook_event_name': 'PreToolUse',
                                'tool_name': tool_name,
                                'tool_input': tool_input,
                                'tool_use_id': tool_use_id,
                            },
                            tool_use_id,
                        )
                        await event.wait()

                    # PostToolUse or PostToolUseFailure hook
                    if is_failure:
                        fail_cb = self._hook_callback_ids.get('PostToolUseFailure')
                        if fail_cb:
                            req_id = f'hook_fail_{tool_use_id}'
                            event = anyio.Event()
                            self._control_response_events[req_id] = event
                            yield self._make_hook_request(
                                req_id,
                                fail_cb,
                                {
                                    'hook_event_name': 'PostToolUseFailure',
                                    'tool_name': tool_name,
                                    'tool_input': tool_input,
                                    'tool_use_id': tool_use_id,
                                    'error': 'Tool execution failed',
                                },
                                tool_use_id,
                            )
                            await event.wait()
                    else:
                        post_cb = self._hook_callback_ids.get('PostToolUse')
                        if post_cb:
                            req_id = f'hook_post_{tool_use_id}'
                            event = anyio.Event()
                            self._control_response_events[req_id] = event
                            yield self._make_hook_request(
                                req_id,
                                post_cb,
                                {
                                    'hook_event_name': 'PostToolUse',
                                    'tool_name': tool_name,
                                    'tool_input': tool_input,
                                    'tool_use_id': tool_use_id,
                                    'tool_response': 'mock_response',
                                },
                                tool_use_id,
                            )
                            await event.wait()

    def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        return self._read_impl()

    async def close(self) -> None:
        pass

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _force_gc() -> None:
    """Force GC to collect SDK internal streams, suppressing ResourceWarning.

    The SDK's Query.close() doesn't close anyio MemoryObjectStreams. When
    collected, __del__ raises ResourceWarning via sys.unraisablehook. We
    temporarily replace the hook to suppress these during collection.
    """
    original_hook = sys.unraisablehook

    def _silent(unraisable: sys.UnraisableHookArgs) -> None:
        if isinstance(unraisable.exc_value, ResourceWarning):
            return
        original_hook(unraisable)  # pragma: no cover

    sys.unraisablehook = _silent
    try:
        gc.collect()
    finally:
        sys.unraisablehook = original_hook


@pytest.fixture(autouse=True)
def _reset_instrumentation():  # pyright: ignore[reportUnusedFunction]
    """Instrument and reset SDK class patching between tests."""
    with logfire.instrument_claude_agent_sdk():
        yield
    _force_gc()


# ---------------------------------------------------------------------------
# Helpers for building transport response messages.
# ---------------------------------------------------------------------------

ASSISTANT_HELLO = {
    'type': 'assistant',
    'message': {
        'role': 'assistant',
        'content': [{'type': 'text', 'text': 'Hello! How can I help?'}],
        'model': 'claude-sonnet-4-20250514',
    },
}

ASSISTANT_TOOL_USE = {
    'type': 'assistant',
    'message': {
        'role': 'assistant',
        'content': [{'type': 'tool_use', 'id': 'tool_1', 'name': 'Bash', 'input': {'command': 'ls'}}],
        'model': 'claude-sonnet-4-20250514',
    },
}

ASSISTANT_FILES = {
    'type': 'assistant',
    'message': {
        'role': 'assistant',
        'content': [{'type': 'text', 'text': 'Here are the files: file1.txt, file2.txt'}],
        'model': 'claude-sonnet-4-20250514',
    },
}


def make_result(
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_cost_usd: float | None = 0.01,
    cache_read: int | None = None,
    cache_create: int | None = None,
    usage: dict[str, Any] | None = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Build a result message for the mock transport."""
    if usage is ...:  # pyright: ignore[reportUnnecessaryComparison]
        u: dict[str, Any] = {'input_tokens': input_tokens, 'output_tokens': output_tokens}
        if cache_read is not None:
            u['cache_read_input_tokens'] = cache_read
        if cache_create is not None:
            u['cache_creation_input_tokens'] = cache_create
        usage = u
    result: dict[str, Any] = {
        'type': 'result',
        'subtype': 'completion',
        'duration_ms': 500,
        'duration_api_ms': 400,
        'is_error': False,
        'num_turns': 1,
        'session_id': 'sess_123',
        'usage': usage,
    }
    if total_cost_usd is not None:
        result['total_cost_usd'] = total_cost_usd
    return result


# ---------------------------------------------------------------------------
# Helpers for unit tests that don't need the SDK.
# ---------------------------------------------------------------------------


def _make_block(class_name: str, **attrs: object) -> Mock:
    """Create a mock content block with the given class name."""
    block = Mock()
    block.__class__ = type(class_name, (), {})  # pyright: ignore[reportAttributeAccessIssue]
    for k, v in attrs.items():
        setattr(block, k, v)
    return block


# ---------------------------------------------------------------------------
# Utility function tests (pure unit tests, no SDK dependency).
# ---------------------------------------------------------------------------


class TestContentBlocksToOutputMessages:
    def test_text_block(self) -> None:
        block = _make_block('TextBlock', text='hello world')
        result = _content_blocks_to_output_messages([block], 'claude-3')
        assert result == [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'hello world'}]}]

    def test_thinking_block(self) -> None:
        block = _make_block('ThinkingBlock', thinking='let me think...', signature='sig123')
        result = _content_blocks_to_output_messages([block], None)
        assert result == [
            {'role': 'assistant', 'parts': [{'type': 'thinking', 'content': 'let me think...', 'signature': 'sig123'}]}
        ]

    def test_tool_use_block(self) -> None:
        block = _make_block('ToolUseBlock', id='tool_1', name='Bash', input={'command': 'ls'})
        result = _content_blocks_to_output_messages([block], None)
        assert result == [
            {
                'role': 'assistant',
                'parts': [{'type': 'tool_call', 'id': 'tool_1', 'name': 'Bash', 'arguments': {'command': 'ls'}}],
            }
        ]

    def test_tool_result_block(self) -> None:
        text_item = Mock()
        text_item.text = 'output text'
        block = _make_block('ToolResultBlock', tool_use_id='tool_1', content=[text_item], is_error=False)
        result = _content_blocks_to_output_messages([block], None)
        assert result == [
            {'role': 'assistant', 'parts': [{'type': 'tool_call_response', 'id': 'tool_1', 'response': 'output text'}]}
        ]

    def test_non_list_returns_empty(self) -> None:
        assert _content_blocks_to_output_messages('just a string', None) == []

    def test_unknown_block_type(self) -> None:
        block = _make_block('UnknownBlock', data='test')
        result = _content_blocks_to_output_messages([block], None)
        assert len(result) == 1
        assert result[0]['parts'][0] is block


class TestExtractToolResultText:
    def test_none_content(self) -> None:
        assert _extract_tool_result_text(None) == ''

    def test_string_content(self) -> None:
        assert _extract_tool_result_text('hello') == 'hello'

    def test_dict_text_items(self) -> None:
        items = [{'type': 'text', 'text': 'line1'}, {'type': 'text', 'text': 'line2'}]
        assert _extract_tool_result_text(items) == 'line1\nline2'

    def test_empty_list_fallback(self) -> None:
        items: list[dict[str, str]] = [{'type': 'image'}]
        assert _extract_tool_result_text(items) == str(items)

    def test_non_list_non_string(self) -> None:
        assert _extract_tool_result_text(42) == '42'

    def test_list_with_hasattr_text(self) -> None:
        item = Mock()
        item.text = 'from attr'
        assert _extract_tool_result_text([item]) == 'from attr'

    def test_list_with_non_text_items(self) -> None:
        """List item that is not a dict and has no .text attribute."""
        result = _extract_tool_result_text([42, 'not a dict'])
        assert result == str([42, 'not a dict'])


class TestExtractUsage:
    def test_extract_usage(self) -> None:
        usage = {
            'input_tokens': 100,
            'output_tokens': 50,
            'cache_read_input_tokens': 20,
            'cache_creation_input_tokens': 10,
        }
        result = _extract_usage(usage)
        assert result['gen_ai.usage.input_tokens'] == 100
        assert result['gen_ai.usage.output_tokens'] == 50
        assert result['gen_ai.usage.cache_read.input_tokens'] == 20
        assert result['gen_ai.usage.cache_creation.input_tokens'] == 10

    def test_extract_empty(self) -> None:
        assert _extract_usage(None) == {}
        assert _extract_usage({}) == {}

    def test_only_cache_read(self) -> None:
        result = _extract_usage({'input_tokens': 50, 'cache_read_input_tokens': 10})
        assert result['gen_ai.usage.cache_read.input_tokens'] == 10

    def test_only_cache_create(self) -> None:
        result = _extract_usage({'output_tokens': 30, 'cache_creation_input_tokens': 5})
        assert result['gen_ai.usage.cache_creation.input_tokens'] == 5

    def test_non_dict_usage(self) -> None:
        class UsageObj:
            input_tokens = 100
            output_tokens = 50
            cache_read_input_tokens = None
            cache_creation_input_tokens = None

        result = _extract_usage(UsageObj())
        assert result == {'gen_ai.usage.input_tokens': 100, 'gen_ai.usage.output_tokens': 50}

    def test_invalid_token_values(self) -> None:
        result = _extract_usage({'input_tokens': 'not_a_number', 'output_tokens': None})
        assert result == {}


# ---------------------------------------------------------------------------
# Hook function tests (direct calls, no transport needed).
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tool_use_hooks(exporter: TestExporter) -> None:
    """Test pre/post tool use hooks create proper child spans."""
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(custom_scope_suffix='claude_agent_sdk')
    _set_logfire_instance(logfire_instance)

    with logfire_instance.span('root') as root_span:
        _set_parent_span(root_span._span)
        try:
            # Successful tool call
            await pre_tool_use_hook(
                {'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'tool_use_id': 'tool_1'},
                'tool_1',
                {'signal': None},
            )
            await post_tool_use_hook(
                {
                    'tool_name': 'Bash',
                    'tool_input': {'command': 'ls'},
                    'tool_response': 'file1.txt',
                    'tool_use_id': 'tool_1',
                },
                'tool_1',
                {'signal': None},
            )
            # Successful tool call with no tool_response
            await pre_tool_use_hook(
                {'tool_name': 'Read', 'tool_input': {'path': '/tmp'}, 'tool_use_id': 'tool_no_resp'},
                'tool_no_resp',
                {'signal': None},
            )
            await post_tool_use_hook(
                {'tool_name': 'Read', 'tool_input': {'path': '/tmp'}, 'tool_use_id': 'tool_no_resp'},
                'tool_no_resp',
                {'signal': None},
            )
            # Failed tool call
            await pre_tool_use_hook(
                {'tool_name': 'Write', 'tool_input': {'path': '/tmp/test'}, 'tool_use_id': 'tool_2'},
                'tool_2',
                {'signal': None},
            )
            await post_tool_use_failure_hook(
                {
                    'tool_name': 'Write',
                    'tool_input': {'path': '/tmp/test'},
                    'error': 'Permission denied',
                    'tool_use_id': 'tool_2',
                },
                'tool_2',
                {'signal': None},
            )
        finally:
            _clear_parent_span()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'execute_tool {tool_name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'tool_name': 'Bash',
                    'logfire.msg_template': 'execute_tool {tool_name}',
                    'logfire.msg': 'execute_tool Bash',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Bash',
                    'gen_ai.tool.call.id': 'tool_1',
                    'gen_ai.tool.call.arguments': {'command': 'ls'},
                    'logfire.span_type': 'span',
                    'gen_ai.tool.call.result': 'file1.txt',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'tool_name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                            'gen_ai.tool.call.result': {},
                        },
                    },
                },
            },
            {
                'name': 'execute_tool {tool_name}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'tool_name': 'Read',
                    'logfire.msg_template': 'execute_tool {tool_name}',
                    'logfire.msg': 'execute_tool Read',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Read',
                    'gen_ai.tool.call.id': 'tool_no_resp',
                    'gen_ai.tool.call.arguments': {'path': '/tmp'},
                    'logfire.span_type': 'span',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'tool_name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                        },
                    },
                },
            },
            {
                'name': 'execute_tool {tool_name}',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'tool_name': 'Write',
                    'logfire.msg_template': 'execute_tool {tool_name}',
                    'logfire.msg': 'execute_tool Write',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Write',
                    'gen_ai.tool.call.id': 'tool_2',
                    'gen_ai.tool.call.arguments': {'path': '/tmp/test'},
                    'logfire.span_type': 'span',
                    'error.type': 'Permission denied',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'tool_name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                            'error.type': {},
                        },
                    },
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_clear_orphaned_tool_spans(exporter: TestExporter) -> None:
    """_clear_active_tool_spans ends and removes any orphaned tool spans."""
    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(custom_scope_suffix='claude_agent_sdk')
    _set_logfire_instance(logfire_instance)

    with logfire_instance.span('root') as root_span:
        _set_parent_span(root_span._span)
        try:
            # Start a tool span but never call post_tool_use_hook
            await pre_tool_use_hook(
                {'tool_name': 'OrphanTool', 'tool_input': {}, 'tool_use_id': 'orphan_1'},
                'orphan_1',
                {'signal': None},
            )
            assert 'orphan_1' in _active_tool_spans
            _clear_active_tool_spans()
            assert 'orphan_1' not in _active_tool_spans
            assert len(_active_tool_spans) == 0
        finally:
            _clear_parent_span()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'execute_tool {tool_name}',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_clear_orphaned_tool_spans',
                    'code.lineno': 123,
                    'tool_name': 'OrphanTool',
                    'logfire.msg_template': 'execute_tool {tool_name}',
                    'logfire.msg': 'execute_tool OrphanTool',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'OrphanTool',
                    'gen_ai.tool.call.id': 'orphan_1',
                    'gen_ai.tool.call.arguments': {},
                    'logfire.span_type': 'span',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'tool_name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                        },
                    },
                },
            },
            {
                'name': 'root',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_clear_orphaned_tool_spans',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


def test_clear_orphaned_tool_spans_error() -> None:
    """_clear_active_tool_spans handles exceptions during cleanup gracefully."""
    broken_span = Mock()
    broken_span.__exit__ = Mock(side_effect=RuntimeError('span already ended'))
    broken_token = Mock()
    _active_tool_spans['broken_1'] = (broken_span, broken_token)
    _clear_active_tool_spans()
    assert len(_active_tool_spans) == 0


@pytest.mark.anyio
async def test_hook_edge_cases() -> None:
    """Hooks return empty dict for edge cases: None tool_use_id, no parent span, missing entry."""
    # None tool_use_id
    assert await pre_tool_use_hook({}, None, {}) == {}
    assert await post_tool_use_hook({}, None, {}) == {}
    assert await post_tool_use_failure_hook({}, None, {}) == {}

    # No parent span set
    _clear_parent_span()
    assert await pre_tool_use_hook({'tool_name': 'Bash', 'tool_input': {}}, 'tool_1', {}) == {}

    # Post hooks with no matching pre entry
    assert await post_tool_use_hook({'tool_response': 'test'}, 'nonexistent', {}) == {}
    assert await post_tool_use_failure_hook({'error': 'test'}, 'nonexistent', {}) == {}


# ---------------------------------------------------------------------------
# Hook injection tests (use real HookMatcher from SDK).
# ---------------------------------------------------------------------------


def test_inject_hooks_no_hooks_attr() -> None:
    class NoHooksOptions:
        pass

    _inject_tracing_hooks(NoHooksOptions())


def test_inject_hooks_none_hooks() -> None:
    options = ClaudeAgentOptions(hooks=None)
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    assert 'PreToolUse' in options.hooks
    assert len(options.hooks['PreToolUse']) == 1


def test_inject_hooks_idempotent() -> None:
    options = ClaudeAgentOptions(hooks=None)
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    count_after_first = len(options.hooks['PreToolUse'])
    _inject_tracing_hooks(options)
    assert len(options.hooks['PreToolUse']) == count_after_first


def test_inject_hooks_with_existing_events() -> None:
    existing_hook = HookMatcher(matcher='existing', hooks=[pre_tool_use_hook])

    class Opts:
        hooks: dict[str, list[Any]] | None = {
            'PreToolUse': [existing_hook],
            'PostToolUse': [],
            'PostToolUseFailure': [],
        }

    options = Opts()
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    assert len(options.hooks['PreToolUse']) == 2
    assert options.hooks['PreToolUse'][1] is existing_hook


# ---------------------------------------------------------------------------
# Integration tests with mock transport and real SDK client.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_basic_conversation(exporter: TestExporter) -> None:
    """Basic conversation: one assistant turn + result."""
    transport = MockTransport([ASSISTANT_HELLO, make_result()])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(system_prompt='Be helpful'), transport=transport)
    try:
        await client.connect()
        await client.query('What is 2+2?')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert len(collected) == 2
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_basic_conversation',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Hello! How can I help?'}]}
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_basic_conversation',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'Be helpful'}],
                    'logfire.msg_template': 'invoke_agent',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_conversation_with_two_turns(exporter: TestExporter) -> None:
    """Two assistant turns (e.g. tool use then result) produce sibling turn spans."""
    transport = MockTransport([ASSISTANT_TOOL_USE, ASSISTANT_FILES, make_result()])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(system_prompt='Be helpful'), transport=transport)
    try:
        await client.connect()
        await client.query('List files')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert len(collected) == 3
    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'execute_tool {tool_name}',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 3000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': IsStr(),
                    'code.lineno': 123,
                    'tool_name': 'Bash',
                    'logfire.msg_template': 'execute_tool {tool_name}',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Bash',
                    'gen_ai.tool.call.id': 'tool_1',
                    'gen_ai.tool.call.arguments': {'command': 'ls'},
                    'logfire.msg': 'execute_tool Bash',
                    'gen_ai.tool.call.result': 'mock_response',
                    'logfire.span_type': 'span',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'tool_name': {},
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                            'gen_ai.tool.call.result': {},
                        },
                    },
                },
            },
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_conversation_with_two_turns',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {'type': 'tool_call', 'id': 'tool_1', 'name': 'Bash', 'arguments': {'command': 'ls'}}
                            ],
                        }
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_conversation_with_two_turns',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [{'type': 'text', 'content': 'Here are the files: file1.txt, file2.txt'}],
                        }
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 8000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_conversation_with_two_turns',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'List files'}]}],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'Be helpful'}],
                    'logfire.msg_template': 'invoke_agent',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_usage_and_cost_attributes(exporter: TestExporter) -> None:
    """Result message usage metrics (including cache details) appear on the conversation span."""
    transport = MockTransport(
        [
            ASSISTANT_HELLO,
            make_result(input_tokens=100, output_tokens=50, total_cost_usd=0.01, cache_read=20, cache_create=10),
        ]
    )
    client = ClaudeSDKClient(options=ClaudeAgentOptions(), transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert spans == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_usage_and_cost_attributes',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Hello! How can I help?'}]}
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_usage_and_cost_attributes',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hi'}]}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'gen_ai.usage.cache_read.input_tokens': 20,
                    'gen_ai.usage.cache_creation.input_tokens': 10,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'logfire.span_type': 'span',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.cache_read.input_tokens': {},
                            'gen_ai.usage.cache_creation.input_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_result_no_usage_or_cost(exporter: TestExporter) -> None:
    """Result without usage or cost should omit those attributes."""
    transport = MockTransport([ASSISTANT_HELLO, make_result(usage=None, total_cost_usd=None)])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(), transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_result_no_usage_or_cost',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Hello! How can I help?'}]}
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_result_no_usage_or_cost',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hi'}]}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.conversation.id': 'sess_123',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_result_only(exporter: TestExporter) -> None:
    """Conversation with only ResultMessage (no assistant turn)."""
    transport = MockTransport([make_result()])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(), transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 2000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_result_only',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hi'}]}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            }
        ]
    )


@pytest.mark.anyio
async def test_non_string_system_prompt(exporter: TestExporter) -> None:
    """Non-string system prompt gets stringified."""
    options = ClaudeAgentOptions()
    # Bypass type checking to test the defensive code path
    object.__setattr__(options, 'system_prompt', ['Be helpful', 'Be concise'])

    transport = MockTransport([ASSISTANT_HELLO, make_result()])
    client = ClaudeSDKClient(options=options, transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_non_string_system_prompt',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Hello! How can I help?'}]}
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_non_string_system_prompt',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hi'}]}],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': "['Be helpful', 'Be concise']"}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_already_instrumented() -> None:
    """Calling instrument twice is a no-op (idempotent)."""
    logfire.instrument_claude_agent_sdk()
    logfire.instrument_claude_agent_sdk()
    # No error, and only one layer of patching


@pytest.mark.anyio
async def test_default_options_get_hooks_injected(exporter: TestExporter) -> None:
    """Client created without explicit options still gets hooks injected."""
    transport = MockTransport([ASSISTANT_HELLO, make_result()])
    client = ClaudeSDKClient(transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_default_options_get_hooks_injected',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'Hello! How can I help?'}]}
                    ],
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'invoke_agent',
                'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'parent': None,
                'start_time': 1000000000,
                'end_time': 4000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_default_options_get_hooks_injected',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'Hi'}]}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 100,
                    'gen_ai.usage.output_tokens': 50,
                    'operation.cost': 0.01,
                    'gen_ai.conversation.id': 'sess_123',
                    'num_turns': 1,
                    'duration_ms': 500,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'operation.cost': {},
                            'gen_ai.conversation.id': {},
                            'num_turns': {},
                            'duration_ms': {},
                        },
                    },
                },
            },
        ]
    )
