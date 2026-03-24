# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnnecessaryTypeIgnoreComment=false
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import Mock

import pytest
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter

# ---------------------------------------------------------------------------
# Mock helpers — create fake SDK message objects with correct type names.
# ---------------------------------------------------------------------------


def _make_block(class_name: str, **attrs: object) -> Mock:
    """Create a mock content block with the given class name."""
    block = Mock()
    block.__class__ = type(class_name, (), {})
    for k, v in attrs.items():
        setattr(block, k, v)
    return block


def _make_assistant_message(text: str = 'Hello!', model: str = 'claude-sonnet-4-20250514') -> Mock:
    msg = Mock()
    msg.__class__ = type('AssistantMessage', (), {})
    msg.content = [_make_block('TextBlock', text=text)]
    msg.model = model
    msg.parent_tool_use_id = None
    return msg


def _make_assistant_message_with_tool_use(
    tool_id: str = 'tool_1',
    tool_name: str = 'Bash',
    tool_input: dict[str, Any] | None = None,
    model: str = 'claude-sonnet-4-20250514',
) -> Mock:
    msg = Mock()
    msg.__class__ = type('AssistantMessage', (), {})
    msg.content = [_make_block('ToolUseBlock', id=tool_id, name=tool_name, input=tool_input or {'command': 'ls'})]
    msg.model = model
    msg.parent_tool_use_id = None
    return msg


def _make_user_message_with_tool_result(
    tool_id: str = 'tool_1',
    content_text: str = 'file1.txt',
    is_error: bool = False,
) -> Mock:
    msg = Mock()
    msg.__class__ = type('UserMessage', (), {})
    text_item = Mock()
    text_item.text = content_text
    msg.content = [_make_block('ToolResultBlock', tool_use_id=tool_id, content=[text_item], is_error=is_error)]
    return msg


def _make_result_message(
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_cost_usd: float = 0.01,
) -> Mock:
    msg = Mock()
    msg.__class__ = type('ResultMessage', (), {})
    msg.usage = {'input_tokens': input_tokens, 'output_tokens': output_tokens}
    msg.total_cost_usd = total_cost_usd
    msg.num_turns = 1
    msg.session_id = 'session_123'
    msg.duration_ms = 500
    msg.is_error = False
    return msg


# ---------------------------------------------------------------------------
# Mock SDK classes for testing instrumentation.
# ---------------------------------------------------------------------------


@dataclass
class MockHookMatcher:
    matcher: str | None = None
    hooks: list[Any] = field(default_factory=list)
    timeout: float | None = None


@dataclass
class MockOptions:
    system_prompt: str | None = None
    hooks: dict[str, list[Any]] | None = None


# ---------------------------------------------------------------------------
# Utility function tests.
# ---------------------------------------------------------------------------


class TestFlattenContentBlocks:
    def test_text_block(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        block = _make_block('TextBlock', text='hello world')
        assert flatten_content_blocks([block]) == [{'type': 'text', 'text': 'hello world'}]

    def test_thinking_block(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        block = _make_block('ThinkingBlock', thinking='let me think...', signature='sig123')
        assert flatten_content_blocks([block]) == [
            {'type': 'thinking', 'thinking': 'let me think...', 'signature': 'sig123'}
        ]

    def test_tool_use_block(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        block = _make_block('ToolUseBlock', id='tool_1', name='Bash', input={'command': 'ls'})
        assert flatten_content_blocks([block]) == [
            {'type': 'tool_use', 'id': 'tool_1', 'name': 'Bash', 'input': {'command': 'ls'}}
        ]

    def test_tool_result_block(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        text_item = Mock()
        text_item.text = 'output text'
        block = _make_block('ToolResultBlock', tool_use_id='tool_1', content=[text_item], is_error=False)
        assert flatten_content_blocks([block]) == [
            {'type': 'tool_result', 'tool_use_id': 'tool_1', 'content': 'output text', 'is_error': False}
        ]

    def test_non_list_passthrough(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        assert flatten_content_blocks('just a string') == 'just a string'


class TestUsageMetadata:
    def test_extract_usage(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        usage = {
            'input_tokens': 100,
            'output_tokens': 50,
            'cache_read_input_tokens': 20,
            'cache_creation_input_tokens': 10,
        }
        result = extract_usage_metadata(usage)
        assert result['input_tokens'] == 100
        assert result['output_tokens'] == 50
        assert result['input_token_details'] == {'cache_read': 20, 'cache_creation': 10}

    def test_extract_empty(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        assert extract_usage_metadata(None) == {}
        assert extract_usage_metadata({}) == {}

    def test_get_usage_from_result(self):
        from logfire._internal.integrations.claude_agent_sdk import get_usage_from_result

        result = get_usage_from_result(
            {
                'input_tokens': 100,
                'output_tokens': 50,
                'cache_read_input_tokens': 20,
                'cache_creation_input_tokens': 10,
            }
        )
        assert result['input_tokens'] == 130  # 100 + 20 + 10
        assert result['output_tokens'] == 50
        assert result['total_tokens'] == 180  # 130 + 50


# ---------------------------------------------------------------------------
# Hook callback tests.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_pre_and_post_tool_use_hooks(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import (
        _clear_parent_span,
        _set_logfire_instance,
        _set_parent_span,
        post_tool_use_hook,
        pre_tool_use_hook,
    )

    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(
        custom_scope_suffix='claude-agent-sdk', tags=['LLM']
    )
    _set_logfire_instance(logfire_instance)

    with logfire_instance.span('root') as root_span:
        _set_parent_span(root_span._span)  # pyright: ignore[reportPrivateUsage]
        try:
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
        finally:
            _clear_parent_span()

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'Bash',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_pre_and_post_tool_use_hooks',
                    'code.lineno': 123,
                    'tool_input': {'command': 'ls'},
                    'logfire.msg_template': 'Bash',
                    'logfire.msg': 'Bash',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'tool_response': 'file1.txt',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'tool_input': {'type': 'object'}, 'tool_response': {}},
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
                    'code.function': 'test_pre_and_post_tool_use_hooks',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


@pytest.mark.anyio
async def test_post_tool_use_failure_hook(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import (
        _clear_parent_span,
        _set_logfire_instance,
        _set_parent_span,
        post_tool_use_failure_hook,
        pre_tool_use_hook,
    )

    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(
        custom_scope_suffix='claude-agent-sdk', tags=['LLM']
    )
    _set_logfire_instance(logfire_instance)

    with logfire_instance.span('root') as root_span:
        _set_parent_span(root_span._span)  # pyright: ignore[reportPrivateUsage]
        try:
            await pre_tool_use_hook(
                {'tool_name': 'Write', 'tool_input': {'path': '/etc/passwd'}, 'tool_use_id': 'tool_2'},
                'tool_2',
                {'signal': None},
            )
            await post_tool_use_failure_hook(
                {
                    'tool_name': 'Write',
                    'tool_input': {'path': '/etc/passwd'},
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
                'name': 'Write',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_post_tool_use_failure_hook',
                    'code.lineno': 123,
                    'tool_input': {'path': "[Scrubbed due to 'passwd']"},
                    'logfire.msg_template': 'Write',
                    'logfire.msg': 'Write',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                    'error': 'Permission denied',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'tool_input': {'type': 'object'}, 'error': {}},
                    },
                    'logfire.scrubbed': [{'path': ['attributes', 'tool_input', 'path'], 'matched_substring': 'passwd'}],
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
                    'code.function': 'test_post_tool_use_failure_hook',
                    'code.lineno': 123,
                    'logfire.msg_template': 'root',
                    'logfire.msg': 'root',
                    'logfire.tags': ('LLM',),
                    'logfire.span_type': 'span',
                },
            },
        ]
    )


# ---------------------------------------------------------------------------
# Integration tests with mock SDK.
# ---------------------------------------------------------------------------


def _setup_mock_sdk(messages: list[Any]) -> tuple[type, Any, Any]:
    """Create a mock ClaudeSDKClient class and register it as a fake module.

    Returns the class, fake module, and previous module. The caller must clean up sys.modules.
    """
    import sys
    import types

    class MockClaudeSDKClient:
        _is_instrumented_by_logfire = False

        def __init__(self, *, options: Any = None):
            self.options = options
            self._logfire_prompt: str | None = None
            self._logfire_start_time: float | None = None
            self._logfire_streamed_input: list[dict[str, Any]] | None = None

        async def query(self, prompt: Any) -> None:
            pass

        async def receive_response(self):  # type: ignore[override]
            for msg in messages:
                yield msg

    _prev_module = sys.modules.get('claude_agent_sdk')

    fake_module = types.ModuleType('claude_agent_sdk')
    fake_module.ClaudeSDKClient = MockClaudeSDKClient  # type: ignore[attr-defined]
    fake_module.HookMatcher = MockHookMatcher  # type: ignore[attr-defined]
    sys.modules['claude_agent_sdk'] = fake_module

    return MockClaudeSDKClient, fake_module, _prev_module


def _teardown_mock_sdk(cls: type, prev_module: Any = None) -> None:
    import sys

    if prev_module is not None:
        sys.modules['claude_agent_sdk'] = prev_module
    else:
        sys.modules.pop('claude_agent_sdk', None)
    cls._is_instrumented_by_logfire = False  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_instrument_basic_conversation(exporter: TestExporter):
    """Verify instrumentation produces conversation and turn spans."""
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [
        _make_assistant_message('Hello! How can I help?'),
        _make_result_message(),
    ]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)

        client = cls(options=MockOptions(system_prompt='Be helpful'))
        await client.query('What is 2+2?')

        collected = []
        async for msg in client.receive_response():
            collected.append(msg)

        assert len(collected) == 2
        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': 'claude.assistant.turn',
                    'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 2000000000,
                    'end_time': 3000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk.py',
                        'code.function': 'test_instrument_basic_conversation',
                        'code.lineno': 123,
                        'content': [{'type': 'text', 'text': 'Hello! How can I help?'}],
                        'model': 'claude-sonnet-4-20250514',
                        'logfire.msg_template': 'claude.assistant.turn',
                        'logfire.msg': 'claude.assistant.turn',
                        'logfire.json_schema': {
                            'type': 'object',
                            'properties': {'content': {'type': 'array'}, 'model': {}},
                        },
                        'logfire.tags': ('LLM',),
                        'logfire.span_type': 'span',
                    },
                },
                {
                    'name': 'claude.conversation',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 4000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk.py',
                        'code.function': 'test_instrument_basic_conversation',
                        'code.lineno': 123,
                        'prompt': 'What is 2+2?',
                        'system_prompt': 'Be helpful',
                        'logfire.msg_template': 'claude.conversation',
                        'logfire.msg': 'claude.conversation',
                        'logfire.tags': ('LLM',),
                        'logfire.span_type': 'span',
                        'usage.input_tokens': 100,
                        'usage.output_tokens': 50,
                        'usage.total_tokens': 150,
                        'total_cost_usd': 0.01,
                        'num_turns': 1,
                        'session_id': "[Scrubbed due to 'session']",
                        'duration_ms': 500,
                        'is_error': False,
                        'logfire.json_schema': {
                            'type': 'object',
                            'properties': {
                                'prompt': {},
                                'system_prompt': {},
                                'usage.input_tokens': {},
                                'usage.output_tokens': {},
                                'usage.total_tokens': {},
                                'total_cost_usd': {},
                                'num_turns': {},
                                'session_id': {},
                                'duration_ms': {},
                                'is_error': {},
                            },
                        },
                        'logfire.scrubbed': [{'path': ['attributes', 'session_id'], 'matched_substring': 'session'}],
                    },
                },
            ]
        )
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_conversation_with_tool_call(exporter: TestExporter):
    """Verify full span tree including tool call turn."""
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [
        _make_assistant_message_with_tool_use(tool_id='tool_1', tool_name='Bash', tool_input={'command': 'ls'}),
        _make_user_message_with_tool_result(tool_id='tool_1', content_text='file1.txt\nfile2.txt'),
        _make_assistant_message('Here are the files: file1.txt, file2.txt'),
        _make_result_message(),
    ]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)

        client = cls(options=MockOptions(system_prompt='Be helpful'))
        await client.query('List files')

        collected = []
        async for msg in client.receive_response():
            collected.append(msg)

        assert len(collected) == 4
        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': 'claude.assistant.turn',
                    'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 2000000000,
                    'end_time': 3000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk.py',
                        'code.function': 'test_instrument_conversation_with_tool_call',
                        'code.lineno': 123,
                        'content': [{'type': 'tool_use', 'id': 'tool_1', 'name': 'Bash', 'input': {'command': 'ls'}}],
                        'model': 'claude-sonnet-4-20250514',
                        'logfire.msg_template': 'claude.assistant.turn',
                        'logfire.msg': 'claude.assistant.turn',
                        'logfire.json_schema': {
                            'type': 'object',
                            'properties': {'content': {'type': 'array'}, 'model': {}},
                        },
                        'logfire.tags': ('LLM',),
                        'logfire.span_type': 'span',
                    },
                },
                {
                    'name': 'claude.assistant.turn',
                    'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 4000000000,
                    'end_time': 5000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk.py',
                        'code.function': 'test_instrument_conversation_with_tool_call',
                        'code.lineno': 123,
                        'content': [{'type': 'text', 'text': 'Here are the files: file1.txt, file2.txt'}],
                        'model': 'claude-sonnet-4-20250514',
                        'logfire.msg_template': 'claude.assistant.turn',
                        'logfire.msg': 'claude.assistant.turn',
                        'logfire.json_schema': {
                            'type': 'object',
                            'properties': {'content': {'type': 'array'}, 'model': {}},
                        },
                        'logfire.tags': ('LLM',),
                        'logfire.span_type': 'span',
                    },
                },
                {
                    'name': 'claude.conversation',
                    'context': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'parent': None,
                    'start_time': 1000000000,
                    'end_time': 6000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk.py',
                        'code.function': 'test_instrument_conversation_with_tool_call',
                        'code.lineno': 123,
                        'prompt': 'List files',
                        'system_prompt': 'Be helpful',
                        'logfire.msg_template': 'claude.conversation',
                        'logfire.msg': 'claude.conversation',
                        'logfire.tags': ('LLM',),
                        'logfire.span_type': 'span',
                        'usage.input_tokens': 100,
                        'usage.output_tokens': 50,
                        'usage.total_tokens': 150,
                        'total_cost_usd': 0.01,
                        'num_turns': 1,
                        'session_id': "[Scrubbed due to 'session']",
                        'duration_ms': 500,
                        'is_error': False,
                        'logfire.json_schema': {
                            'type': 'object',
                            'properties': {
                                'prompt': {},
                                'system_prompt': {},
                                'usage.input_tokens': {},
                                'usage.output_tokens': {},
                                'usage.total_tokens': {},
                                'total_cost_usd': {},
                                'num_turns': {},
                                'session_id': {},
                                'duration_ms': {},
                                'is_error': {},
                            },
                        },
                        'logfire.scrubbed': [{'path': ['attributes', 'session_id'], 'matched_substring': 'session'}],
                    },
                },
            ]
        )
    finally:
        _teardown_mock_sdk(cls, prev)


# ---------------------------------------------------------------------------
# Additional coverage tests for edge cases and utility branches.
# ---------------------------------------------------------------------------


class TestExtractToolResultText:
    def test_none_content(self):
        from logfire._internal.integrations.claude_agent_sdk import _extract_tool_result_text

        assert _extract_tool_result_text(None) == ''

    def test_string_content(self):
        from logfire._internal.integrations.claude_agent_sdk import _extract_tool_result_text

        assert _extract_tool_result_text('hello') == 'hello'

    def test_dict_text_items(self):
        from logfire._internal.integrations.claude_agent_sdk import _extract_tool_result_text

        items = [{'type': 'text', 'text': 'line1'}, {'type': 'text', 'text': 'line2'}]
        assert _extract_tool_result_text(items) == 'line1\nline2'

    def test_empty_list_fallback(self):
        from logfire._internal.integrations.claude_agent_sdk import _extract_tool_result_text

        items: list[dict[str, str]] = [{'type': 'image'}]
        assert _extract_tool_result_text(items) == str(items)

    def test_non_list_non_string(self):
        from logfire._internal.integrations.claude_agent_sdk import _extract_tool_result_text

        assert _extract_tool_result_text(42) == '42'


class TestFlattenContentBlocksExtra:
    def test_unknown_block_type(self):
        from logfire._internal.integrations.claude_agent_sdk import flatten_content_blocks

        block = _make_block('UnknownBlock', data='test')
        result = flatten_content_blocks([block])
        assert len(result) == 1
        assert result[0] is block


class TestUsageMetadataExtra:
    def test_only_cache_read(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        result = extract_usage_metadata({'input_tokens': 50, 'cache_read_input_tokens': 10})
        assert result['input_token_details'] == {'cache_read': 10}

    def test_only_cache_create(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        result = extract_usage_metadata({'output_tokens': 30, 'cache_creation_input_tokens': 5})
        assert result['input_token_details'] == {'cache_creation': 5}

    def test_non_dict_usage(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        class UsageObj:
            input_tokens = 100
            output_tokens = 50
            cache_read_input_tokens = None
            cache_creation_input_tokens = None

        result = extract_usage_metadata(UsageObj())
        assert result == {'input_tokens': 100, 'output_tokens': 50}

    def test_invalid_token_values(self):
        from logfire._internal.integrations.claude_agent_sdk import extract_usage_metadata

        result = extract_usage_metadata({'input_tokens': 'not_a_number', 'output_tokens': None})
        assert result == {}

    def test_get_usage_from_result_empty(self):
        from logfire._internal.integrations.claude_agent_sdk import get_usage_from_result

        assert get_usage_from_result(None) == {}
        assert get_usage_from_result({}) == {}

    def test_get_usage_no_cache(self):
        from logfire._internal.integrations.claude_agent_sdk import get_usage_from_result

        result = get_usage_from_result({'input_tokens': 100, 'output_tokens': 50})
        assert result['input_tokens'] == 100
        assert result['total_tokens'] == 150


@pytest.mark.anyio
async def test_hook_with_none_tool_use_id():
    from logfire._internal.integrations.claude_agent_sdk import (
        post_tool_use_failure_hook,
        post_tool_use_hook,
        pre_tool_use_hook,
    )

    assert await pre_tool_use_hook({}, None, {}) == {}
    assert await post_tool_use_hook({}, None, {}) == {}
    assert await post_tool_use_failure_hook({}, None, {}) == {}


@pytest.mark.anyio
async def test_hook_with_no_parent_span():
    from logfire._internal.integrations.claude_agent_sdk import _clear_parent_span, pre_tool_use_hook

    _clear_parent_span()
    assert await pre_tool_use_hook({'tool_name': 'Bash', 'tool_input': {}}, 'tool_1', {}) == {}


@pytest.mark.anyio
async def test_post_hook_with_missing_entry():
    from logfire._internal.integrations.claude_agent_sdk import post_tool_use_failure_hook, post_tool_use_hook

    assert await post_tool_use_hook({'tool_response': 'test'}, 'nonexistent', {}) == {}
    assert await post_tool_use_failure_hook({'error': 'test'}, 'nonexistent', {}) == {}


@pytest.mark.anyio
async def test_instrument_already_instrumented(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [_make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_no_options(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [_make_assistant_message('Hi'), _make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls()
        await client.query('Hello')
        msgs = [msg async for msg in client.receive_response()]
        assert len(msgs) == 2
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_non_string_system_prompt(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [_make_assistant_message('Hi'), _make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions(system_prompt=['Be helpful', 'Be concise']))  # type: ignore[arg-type]
        await client.query('Hello')
        [msg async for msg in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        conversation_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
        assert conversation_span['attributes']['system_prompt'] == "['Be helpful', 'Be concise']"
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_query_none_prompt(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [_make_assistant_message('Hi'), _make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions())
        await client.query(None)
        [msg async for msg in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        conversation_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
        assert 'prompt' not in conversation_span['attributes']
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_query_non_string_prompt(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    messages = [_make_assistant_message('Hi'), _make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions())
        await client.query(42)
        [msg async for msg in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        conversation_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
        assert conversation_span['attributes']['prompt'] == '42'
    finally:
        _teardown_mock_sdk(cls, prev)


def test_inject_hooks_no_hooks_attr():
    from logfire._internal.integrations.claude_agent_sdk import _inject_tracing_hooks

    class NoHooksOptions:
        pass

    _inject_tracing_hooks(NoHooksOptions())


def test_inject_hooks_none_hooks():
    import sys
    import types

    from logfire._internal.integrations.claude_agent_sdk import _inject_tracing_hooks

    prev = sys.modules.get('claude_agent_sdk')
    fake_module = types.ModuleType('claude_agent_sdk')
    fake_module.HookMatcher = MockHookMatcher  # type: ignore[attr-defined]
    sys.modules['claude_agent_sdk'] = fake_module
    try:
        options = MockOptions(hooks=None)
        _inject_tracing_hooks(options)
        assert options.hooks is not None
        assert 'PreToolUse' in options.hooks
        assert len(options.hooks['PreToolUse']) == 1
    finally:
        if prev is not None:
            sys.modules['claude_agent_sdk'] = prev
        else:
            sys.modules.pop('claude_agent_sdk', None)


def test_inject_hooks_idempotent():
    import sys
    import types

    from logfire._internal.integrations.claude_agent_sdk import _inject_tracing_hooks

    prev = sys.modules.get('claude_agent_sdk')
    fake_module = types.ModuleType('claude_agent_sdk')
    fake_module.HookMatcher = MockHookMatcher  # type: ignore[attr-defined]
    sys.modules['claude_agent_sdk'] = fake_module
    try:
        options = MockOptions(hooks=None)
        _inject_tracing_hooks(options)
        assert options.hooks is not None
        count_after_first = len(options.hooks['PreToolUse'])
        _inject_tracing_hooks(options)
        assert len(options.hooks['PreToolUse']) == count_after_first
    finally:
        if prev is not None:
            sys.modules['claude_agent_sdk'] = prev
        else:
            sys.modules.pop('claude_agent_sdk', None)


@pytest.mark.anyio
async def test_instrument_with_cache_usage(exporter: TestExporter):
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    msg = Mock()
    msg.__class__ = type('ResultMessage', (), {})
    msg.usage = {
        'input_tokens': 100,
        'output_tokens': 50,
        'cache_read_input_tokens': 20,
        'cache_creation_input_tokens': 10,
    }
    msg.total_cost_usd = None
    msg.num_turns = None
    msg.session_id = None
    msg.duration_ms = None
    msg.is_error = None

    messages = [_make_assistant_message('Hi'), msg]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions())
        await client.query('Hello')
        [m async for m in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        conversation_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
        attrs = conversation_span['attributes']
        assert attrs['usage.input_token_details.cache_read'] == 20
        assert attrs['usage.input_token_details.cache_creation'] == 10
        assert attrs['usage.input_tokens'] == 130
        assert attrs['usage.total_tokens'] == 180
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_no_content_no_model_turn(exporter: TestExporter):
    """Turn with no content and no model should still produce a span."""
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    msg = Mock()
    msg.__class__ = type('AssistantMessage', (), {})
    msg.content = []
    msg.model = None
    msg.parent_tool_use_id = None

    messages = [msg, _make_result_message()]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions())
        await client.query('Hello')
        [m async for m in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        turn_spans = [s for s in spans if s['name'] == 'claude.assistant.turn']
        assert len(turn_spans) == 1
        assert 'content' not in turn_spans[0]['attributes']
        assert 'model' not in turn_spans[0]['attributes']
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_instrument_result_no_usage(exporter: TestExporter):
    """ResultMessage without usage should still work."""
    from logfire._internal.integrations.claude_agent_sdk import instrument_claude_agent_sdk

    msg = Mock()
    msg.__class__ = type('ResultMessage', (), {})
    msg.usage = None
    msg.total_cost_usd = None
    msg.num_turns = None
    msg.session_id = None
    msg.duration_ms = None
    msg.is_error = None

    messages = [_make_assistant_message('Hi'), msg]
    cls, _, prev = _setup_mock_sdk(messages)
    try:
        instrument_claude_agent_sdk(logfire.DEFAULT_LOGFIRE_INSTANCE)
        client = cls(options=MockOptions())
        await client.query('Hello')
        [m async for m in client.receive_response()]
        spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
        conversation_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
        assert 'usage.input_tokens' not in conversation_span['attributes']
    finally:
        _teardown_mock_sdk(cls, prev)


@pytest.mark.anyio
async def test_post_tool_use_hook_no_tool_response(exporter: TestExporter):
    """post_tool_use_hook when tool_response is absent."""
    from logfire._internal.integrations.claude_agent_sdk import (
        _clear_parent_span,
        _set_logfire_instance,
        _set_parent_span,
        post_tool_use_hook,
        pre_tool_use_hook,
    )

    logfire_instance = logfire.DEFAULT_LOGFIRE_INSTANCE.with_settings(
        custom_scope_suffix='claude-agent-sdk', tags=['LLM']
    )
    _set_logfire_instance(logfire_instance)

    with logfire_instance.span('root') as root_span:
        _set_parent_span(root_span._span)  # pyright: ignore[reportPrivateUsage]
        try:
            await pre_tool_use_hook(
                {'tool_name': 'Read', 'tool_input': {}, 'tool_use_id': 'tool_3'},
                'tool_3',
                {},
            )
            await post_tool_use_hook(
                {'tool_name': 'Read', 'tool_input': {}},
                'tool_3',
                {},
            )
        finally:
            _clear_parent_span()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    tool_span = [s for s in spans if s['name'] == 'Read'][0]
    assert 'tool_response' not in tool_span['attributes']


def test_inject_hooks_with_existing_events():
    """Hooks should be added when events already exist in options.hooks."""
    import sys
    import types

    from logfire._internal.integrations.claude_agent_sdk import _inject_tracing_hooks

    prev = sys.modules.get('claude_agent_sdk')
    fake_module = types.ModuleType('claude_agent_sdk')
    fake_module.HookMatcher = MockHookMatcher  # type: ignore[attr-defined]
    sys.modules['claude_agent_sdk'] = fake_module
    try:
        existing_hook = MockHookMatcher(matcher='existing', hooks=[lambda: None])
        options = MockOptions(hooks={'PreToolUse': [existing_hook], 'PostToolUse': [], 'PostToolUseFailure': []})
        _inject_tracing_hooks(options)
        assert options.hooks is not None
        assert len(options.hooks['PreToolUse']) == 2
        assert options.hooks['PreToolUse'][1] is existing_hook
    finally:
        if prev is not None:
            sys.modules['claude_agent_sdk'] = prev
        else:
            sys.modules.pop('claude_agent_sdk', None)
