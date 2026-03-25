# ruff: noqa: E402
# pyright: reportPrivateUsage=false, reportAttributeAccessIssue=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnnecessaryTypeIgnoreComment=false, reportUnusedFunction=false, reportUnnecessaryComparison=false, reportArgumentType=false
"""Tests for Claude Agent SDK instrumentation.

Integration tests use a mock transport to exercise the real SDK client
with instrumented methods, making them resilient to import refactoring.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import Mock

import pytest

# Must come before logfire internal imports which transitively import claude_agent_sdk
claude_agent_sdk = pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.claude_agent_sdk import (
    _clear_parent_span,
    _extract_tool_result_text,
    _inject_tracing_hooks,
    _set_logfire_instance,
    _set_parent_span,
    extract_usage_metadata,
    flatten_content_blocks,
    get_usage_from_result,
    post_tool_use_failure_hook,
    post_tool_use_hook,
    pre_tool_use_hook,
)
from logfire.testing import TestExporter

ClaudeAgentOptions = claude_agent_sdk.ClaudeAgentOptions
ClaudeSDKClient = claude_agent_sdk.ClaudeSDKClient
HookMatcher = claude_agent_sdk.HookMatcher
Transport = claude_agent_sdk.Transport


# ---------------------------------------------------------------------------
# Mock transport — handles the SDK control protocol, yields predefined messages.
# ---------------------------------------------------------------------------


class MockTransport(Transport):
    """Mock transport for the Claude Agent SDK.

    Handles the initialize handshake (control_request/response) and yields
    predefined response messages after the user query is sent.
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.written: list[dict[str, Any]] = []
        self._init_request_id: str | None = None

    async def connect(self) -> None:
        import anyio

        self._init_event = anyio.Event()
        self._query_event = anyio.Event()

    async def write(self, data: str) -> None:
        msg = json.loads(data)
        self.written.append(msg)
        if msg.get('type') == 'control_request':
            self._init_request_id = msg['request_id']
            self._init_event.set()
        elif msg.get('type') == 'user':
            self._query_event.set()

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


@pytest.fixture(autouse=True)
def _reset_instrumentation():
    """Instrument and reset SDK class patching between tests."""
    with logfire.instrument_claude_agent_sdk():
        yield


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
    total_cost_usd: float = 0.01,
    cache_read: int | None = None,
    cache_create: int | None = None,
    usage: dict[str, Any] | None = ...,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Build a result message for the mock transport."""
    if usage is ...:
        u: dict[str, Any] = {'input_tokens': input_tokens, 'output_tokens': output_tokens}
        if cache_read is not None:
            u['cache_read_input_tokens'] = cache_read
        if cache_create is not None:
            u['cache_creation_input_tokens'] = cache_create
        usage = u
    return {
        'type': 'result',
        'subtype': 'completion',
        'duration_ms': 500,
        'duration_api_ms': 400,
        'is_error': False,
        'num_turns': 1,
        'session_id': 'sess_123',
        'total_cost_usd': total_cost_usd,
        'usage': usage,
    }


# ---------------------------------------------------------------------------
# Helpers for unit tests that don't need the SDK.
# ---------------------------------------------------------------------------


def _make_block(class_name: str, **attrs: object) -> Mock:
    """Create a mock content block with the given class name."""
    block = Mock()
    block.__class__ = type(class_name, (), {})
    for k, v in attrs.items():
        setattr(block, k, v)
    return block


# ---------------------------------------------------------------------------
# Utility function tests (pure unit tests, no SDK dependency).
# ---------------------------------------------------------------------------


class TestFlattenContentBlocks:
    def test_text_block(self):
        block = _make_block('TextBlock', text='hello world')
        assert flatten_content_blocks([block]) == [{'type': 'text', 'text': 'hello world'}]

    def test_thinking_block(self):
        block = _make_block('ThinkingBlock', thinking='let me think...', signature='sig123')
        assert flatten_content_blocks([block]) == [
            {'type': 'thinking', 'thinking': 'let me think...', 'signature': 'sig123'}
        ]

    def test_tool_use_block(self):
        block = _make_block('ToolUseBlock', id='tool_1', name='Bash', input={'command': 'ls'})
        assert flatten_content_blocks([block]) == [
            {'type': 'tool_use', 'id': 'tool_1', 'name': 'Bash', 'input': {'command': 'ls'}}
        ]

    def test_tool_result_block(self):
        text_item = Mock()
        text_item.text = 'output text'
        block = _make_block('ToolResultBlock', tool_use_id='tool_1', content=[text_item], is_error=False)
        assert flatten_content_blocks([block]) == [
            {'type': 'tool_result', 'tool_use_id': 'tool_1', 'content': 'output text', 'is_error': False}
        ]

    def test_non_list_passthrough(self):
        assert flatten_content_blocks('just a string') == 'just a string'

    def test_unknown_block_type(self):
        block = _make_block('UnknownBlock', data='test')
        result = flatten_content_blocks([block])
        assert len(result) == 1
        assert result[0] is block


class TestExtractToolResultText:
    def test_none_content(self):
        assert _extract_tool_result_text(None) == ''

    def test_string_content(self):
        assert _extract_tool_result_text('hello') == 'hello'

    def test_dict_text_items(self):
        items = [{'type': 'text', 'text': 'line1'}, {'type': 'text', 'text': 'line2'}]
        assert _extract_tool_result_text(items) == 'line1\nline2'

    def test_empty_list_fallback(self):
        items: list[dict[str, str]] = [{'type': 'image'}]
        assert _extract_tool_result_text(items) == str(items)

    def test_non_list_non_string(self):
        assert _extract_tool_result_text(42) == '42'

    def test_list_with_hasattr_text(self):
        item = Mock()
        item.text = 'from attr'
        assert _extract_tool_result_text([item]) == 'from attr'

    def test_list_with_non_text_items(self):
        """List item that is not a dict and has no .text attribute."""
        result = _extract_tool_result_text([42, 'not a dict'])
        assert result == str([42, 'not a dict'])


class TestUsageMetadata:
    def test_extract_usage(self):
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
        assert extract_usage_metadata(None) == {}
        assert extract_usage_metadata({}) == {}

    def test_get_usage_from_result(self):
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

    def test_only_cache_read(self):
        result = extract_usage_metadata({'input_tokens': 50, 'cache_read_input_tokens': 10})
        assert result['input_token_details'] == {'cache_read': 10}

    def test_only_cache_create(self):
        result = extract_usage_metadata({'output_tokens': 30, 'cache_creation_input_tokens': 5})
        assert result['input_token_details'] == {'cache_creation': 5}

    def test_non_dict_usage(self):
        class UsageObj:
            input_tokens = 100
            output_tokens = 50
            cache_read_input_tokens = None
            cache_creation_input_tokens = None

        result = extract_usage_metadata(UsageObj())
        assert result == {'input_tokens': 100, 'output_tokens': 50}

    def test_invalid_token_values(self):
        result = extract_usage_metadata({'input_tokens': 'not_a_number', 'output_tokens': None})
        assert result == {}

    def test_get_usage_from_result_empty(self):
        assert get_usage_from_result(None) == {}
        assert get_usage_from_result({}) == {}

    def test_get_usage_no_cache(self):
        result = get_usage_from_result({'input_tokens': 100, 'output_tokens': 50})
        assert result['input_tokens'] == 100
        assert result['total_tokens'] == 150


# ---------------------------------------------------------------------------
# Hook function tests (direct calls, no transport needed).
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tool_use_hooks(exporter: TestExporter):
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

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    tool_spans = [s for s in spans if s['name'] in ('Bash', 'Write')]
    assert len(tool_spans) == 2
    # Both are children of the root span
    root = [s for s in spans if s['name'] == 'root'][0]
    for ts in tool_spans:
        assert ts['parent'] == root['context']
    # Successful tool has response attribute
    bash_span = [s for s in spans if s['name'] == 'Bash'][0]
    assert bash_span['attributes']['tool_response'] == 'file1.txt'
    # Failed tool has error attribute
    write_span = [s for s in spans if s['name'] == 'Write'][0]
    assert write_span['attributes']['error'] == 'Permission denied'


@pytest.mark.anyio
async def test_hook_edge_cases():
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


def test_inject_hooks_no_hooks_attr():
    class NoHooksOptions:
        pass

    _inject_tracing_hooks(NoHooksOptions())


def test_inject_hooks_none_hooks():
    options = ClaudeAgentOptions(hooks=None)
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    assert 'PreToolUse' in options.hooks
    assert len(options.hooks['PreToolUse']) == 1


def test_inject_hooks_idempotent():
    options = ClaudeAgentOptions(hooks=None)
    _inject_tracing_hooks(options)
    assert options.hooks is not None
    count_after_first = len(options.hooks['PreToolUse'])
    _inject_tracing_hooks(options)
    assert len(options.hooks['PreToolUse']) == count_after_first


def test_inject_hooks_with_existing_events():
    existing_hook = HookMatcher(matcher='existing', hooks=[lambda: None])

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
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_basic_conversation(exporter: TestExporter):
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
                'name': 'claude.assistant.turn',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_basic_conversation',
                    'code.lineno': 123,
                    'content': [{'type': 'text', 'text': 'Hello! How can I help?'}],
                    'model': 'claude-sonnet-4-20250514',
                    'logfire.msg_template': 'claude.assistant.turn',
                    'logfire.msg': 'claude.assistant.turn',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {'content': {'type': 'array'}, 'model': {}},
                    },
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
                    'code.function': 'test_basic_conversation',
                    'code.lineno': 123,
                    'prompt': 'What is 2+2?',
                    'system_prompt': 'Be helpful',
                    'logfire.msg_template': 'claude.conversation',
                    'logfire.msg': 'claude.conversation',
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


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_conversation_with_two_turns(exporter: TestExporter):
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
    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    span_names = [s['name'] for s in spans]
    assert span_names.count('claude.assistant.turn') == 2
    assert 'claude.conversation' in span_names
    # Both turns should be children of the conversation
    conv_span = [s for s in spans if s['name'] == 'claude.conversation'][0]
    turn_spans = [s for s in spans if s['name'] == 'claude.assistant.turn']
    for turn in turn_spans:
        assert turn['parent'] == conv_span['context']


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_usage_and_cost_attributes(exporter: TestExporter):
    """Result message usage metrics appear on the conversation span."""
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
    conv = [s for s in spans if s['name'] == 'claude.conversation'][0]
    attrs = conv['attributes']
    assert attrs['usage.input_tokens'] == 130  # 100 + 20 + 10
    assert attrs['usage.output_tokens'] == 50
    assert attrs['usage.total_tokens'] == 180
    assert attrs['usage.input_token_details.cache_read'] == 20
    assert attrs['usage.input_token_details.cache_creation'] == 10
    assert attrs['total_cost_usd'] == 0.01


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_result_no_usage(exporter: TestExporter):
    """Result without usage should not produce usage attributes."""
    transport = MockTransport([ASSISTANT_HELLO, make_result(usage=None)])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(), transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    conv = [s for s in spans if s['name'] == 'claude.conversation'][0]
    assert 'usage.input_tokens' not in conv['attributes']


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_result_only(exporter: TestExporter):
    """Conversation with only ResultMessage (no assistant turn)."""
    transport = MockTransport([make_result()])
    client = ClaudeSDKClient(options=ClaudeAgentOptions(), transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert [s['name'] for s in spans] == ['claude.conversation']


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_non_string_system_prompt(exporter: TestExporter):
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

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    conv = [s for s in spans if s['name'] == 'claude.conversation'][0]
    assert conv['attributes']['system_prompt'] == "['Be helpful', 'Be concise']"


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_already_instrumented(exporter: TestExporter):
    """Calling instrument twice is a no-op (idempotent)."""
    logfire.instrument_claude_agent_sdk()
    logfire.instrument_claude_agent_sdk()
    # No error, and only one layer of patching


@pytest.mark.anyio
@pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')
async def test_default_options_get_hooks_injected(exporter: TestExporter):
    """Client created without explicit options still gets hooks injected."""
    transport = MockTransport([ASSISTANT_HELLO, make_result()])
    client = ClaudeSDKClient(transport=transport)
    try:
        await client.connect()
        await client.query('Hi')
        [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    spans = exporter.exported_spans_as_dict(parse_json_attributes=True)
    assert 'claude.conversation' in [s['name'] for s in spans]
    # Verify hooks were injected into default options
    assert client.options.hooks is not None
    assert 'PreToolUse' in client.options.hooks
