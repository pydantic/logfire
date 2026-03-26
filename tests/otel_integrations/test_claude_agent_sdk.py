# pyright: reportPrivateUsage=false
"""Unit tests for Claude Agent SDK instrumentation helpers.

Tests pure utility functions (content block conversion, usage extraction,
tool result text extraction), hook functions, and hook injection logic.
These don't need the SDK's transport layer — integration tests that exercise
the full message flow live in test_claude_agent_sdk_cassette.py.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
from claude_agent_sdk.types import HookContext
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_instrumentation():  # pyright: ignore[reportUnusedFunction]
    """Instrument and reset SDK class patching between tests."""
    with logfire.instrument_claude_agent_sdk():
        yield


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
        result = _content_blocks_to_output_messages([block])
        assert result == [{'role': 'assistant', 'parts': [{'type': 'text', 'content': 'hello world'}]}]

    def test_thinking_block(self) -> None:
        block = _make_block('ThinkingBlock', thinking='let me think...', signature='sig123')
        result = _content_blocks_to_output_messages([block])
        assert result == [
            {'role': 'assistant', 'parts': [{'type': 'thinking', 'content': 'let me think...', 'signature': 'sig123'}]}
        ]

    def test_tool_use_block(self) -> None:
        block = _make_block('ToolUseBlock', id='tool_1', name='Bash', input={'command': 'ls'})
        result = _content_blocks_to_output_messages([block])
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
        result = _content_blocks_to_output_messages([block])
        assert result == [
            {'role': 'assistant', 'parts': [{'type': 'tool_call_response', 'id': 'tool_1', 'response': 'output text'}]}
        ]

    def test_non_list_returns_empty(self) -> None:
        assert _content_blocks_to_output_messages('just a string') == []

    def test_unknown_block_type(self) -> None:
        block = _make_block('UnknownBlock', data='test')
        result = _content_blocks_to_output_messages([block])
        assert len(result) == 1
        assert result[0]['parts'][0] is block


def test_extract_tool_result_text() -> None:
    assert _extract_tool_result_text(None) == ''
    assert _extract_tool_result_text('hello') == 'hello'
    assert (
        _extract_tool_result_text([{'type': 'text', 'text': 'line1'}, {'type': 'text', 'text': 'line2'}])
        == 'line1\nline2'
    )
    assert _extract_tool_result_text([{'type': 'image'}]) == str([{'type': 'image'}])
    assert _extract_tool_result_text(42) == '42'
    # Object with .text attribute
    item = Mock()
    item.text = 'from attr'
    assert _extract_tool_result_text([item]) == 'from attr'
    # List items that are not dicts and have no .text attribute
    assert _extract_tool_result_text([42, 'not a dict']) == str([42, 'not a dict'])


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
        assert root_span._span is not None
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
        assert root_span._span is not None
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
    ctx: HookContext = {'signal': None}

    # None tool_use_id
    assert await pre_tool_use_hook({}, None, ctx) == {}
    assert await post_tool_use_hook({}, None, ctx) == {}
    assert await post_tool_use_failure_hook({}, None, ctx) == {}

    # No parent span set
    _clear_parent_span()
    assert await pre_tool_use_hook({'tool_name': 'Bash', 'tool_input': {}}, 'tool_1', ctx) == {}

    # Post hooks with no matching pre entry
    assert await post_tool_use_hook({'tool_response': 'test'}, 'nonexistent', ctx) == {}
    assert await post_tool_use_failure_hook({'error': 'test'}, 'nonexistent', ctx) == {}


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
        hooks: dict[str, list[HookMatcher]] | None = {
            'PreToolUse': [existing_hook],
            'PostToolUse': [],
            'PostToolUseFailure': [],
        }

    options = Opts()
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    assert len(options.hooks['PreToolUse']) == 2
    assert options.hooks['PreToolUse'][1] is existing_hook


@pytest.mark.anyio
async def test_already_instrumented() -> None:
    """Calling instrument twice is a no-op (idempotent)."""
    logfire.instrument_claude_agent_sdk()
    logfire.instrument_claude_agent_sdk()
    # No error, and only one layer of patching
