# pyright: reportPrivateUsage=false
"""Tests for Claude Agent SDK instrumentation.

Unit tests for helper functions (content block conversion, usage extraction,
hook functions, hook injection) plus cassette-based integration tests that
replay recorded sessions through the real SubprocessCLITransport.

Recording cassettes (requires a real `claude` CLI with valid credentials):
    uv run pytest tests/otel_integrations/test_claude_agent_sdk.py --record-claude-cassettes

Replaying (default, no real CLI needed):
    uv run pytest tests/otel_integrations/test_claude_agent_sdk.py
"""

from __future__ import annotations

import os
import shutil
import stat
from contextlib import suppress
from pathlib import Path
from unittest.mock import Mock

import pytest

pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import HookContext
from dirty_equals import IsStr
from inline_snapshot import snapshot

import logfire
from logfire._internal.integrations.claude_agent_sdk import (
    _active_tool_spans,
    _clear_active_tool_spans,
    _clear_parent_span,
    _content_blocks_to_output_messages,
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
# Constants
# ---------------------------------------------------------------------------

FAKE_CLAUDE = Path(__file__).parent / 'fake_claude.py'
CASSETTES_DIR = Path(__file__).parent / 'cassettes' / 'test_claude_agent_sdk'

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_instrumentation():  # pyright: ignore[reportUnusedFunction]
    """Instrument and reset SDK class patching between tests."""
    with logfire.instrument_claude_agent_sdk():
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _close_sdk_streams(client: ClaudeSDKClient) -> None:
    """Close streams the SDK neglects to close, preventing ResourceWarning on GC.

    The SDK's Query.close() doesn't close its internal MemoryObject streams,
    and SubprocessCLITransport.close() doesn't close stdout. Close them
    explicitly before disconnect() sets _query/_transport to None.
    """
    query = client._query
    if query is not None:
        with suppress(Exception):
            await query._message_send.aclose()
        with suppress(Exception):
            await query._message_receive.aclose()
    transport = client._transport
    if transport is not None:
        stdout = getattr(transport, '_stdout_stream', None)
        if stdout is not None:
            with suppress(Exception):
                await stdout.aclose()


def _make_client(
    cassette_name: str,
    *,
    monkeypatch: pytest.MonkeyPatch,
    system_prompt: str = 'Be helpful',
    record: bool = False,
) -> ClaudeSDKClient:
    """Create a ClaudeSDKClient backed by a cassette file.

    In replay mode (default), uses fake_claude.py to replay a recorded session.
    In record mode, uses fake_claude.py as a proxy to the real claude CLI,
    recording the session to the cassette file.
    """
    cassette_path = CASSETTES_DIR / cassette_name

    if not record and not cassette_path.exists():
        raise FileNotFoundError(
            f'Cassette not found: {cassette_path}\n'
            f'Record it with: uv run pytest {__file__} --record-claude-cassettes -k <test_name>'
        )

    # Ensure fake_claude.py is executable
    fake_claude_path = str(FAKE_CLAUDE)
    st = os.stat(fake_claude_path)
    if not (st.st_mode & stat.S_IEXEC):
        os.chmod(fake_claude_path, st.st_mode | stat.S_IEXEC)

    monkeypatch.setenv('CASSETTE_PATH', str(cassette_path))

    if record:
        real_claude = shutil.which('claude')
        if not real_claude:
            pytest.skip('Real claude CLI not found on PATH; cannot record cassette')
        monkeypatch.setenv('CASSETTE_MODE', 'record')
        monkeypatch.setenv('REAL_CLAUDE_PATH', real_claude)
    else:
        monkeypatch.setenv('CASSETTE_MODE', 'replay')
        monkeypatch.delenv('REAL_CLAUDE_PATH', raising=False)

    monkeypatch.setenv('CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK', '1')

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            system_prompt=system_prompt,
            cli_path=fake_claude_path,
        ),
    )


# ---------------------------------------------------------------------------
# Utility function tests (pure unit tests, no SDK dependency).
# ---------------------------------------------------------------------------


def test_content_blocks_to_output_messages() -> None:
    # Non-list returns empty
    assert _content_blocks_to_output_messages('just a string') == []

    # TextBlock
    assert _content_blocks_to_output_messages([TextBlock(text='hello world')]) == [
        {'role': 'assistant', 'parts': [{'type': 'text', 'content': 'hello world'}]}
    ]

    # ThinkingBlock → ReasoningPart
    assert _content_blocks_to_output_messages([ThinkingBlock(thinking='let me think...', signature='sig123')]) == [
        {'role': 'assistant', 'parts': [{'type': 'reasoning', 'content': 'let me think...'}]}
    ]

    # ToolUseBlock
    assert _content_blocks_to_output_messages([ToolUseBlock(id='tool_1', name='Bash', input={'command': 'ls'})]) == [
        {
            'role': 'assistant',
            'parts': [{'type': 'tool_call', 'id': 'tool_1', 'name': 'Bash', 'arguments': {'command': 'ls'}}],
        }
    ]

    # ToolResultBlock — content passed through directly
    assert _content_blocks_to_output_messages([ToolResultBlock(tool_use_id='tool_1', content='output text')]) == [
        {'role': 'assistant', 'parts': [{'type': 'tool_call_response', 'id': 'tool_1', 'response': 'output text'}]}
    ]

    # Unknown block type passes through
    block = Mock()
    result = _content_blocks_to_output_messages([block])
    assert len(result) == 1
    assert result[0]['parts'][0] is block


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
        _set_parent_span(root_span)
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
                'name': 'execute_tool Bash',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'logfire.msg_template': 'execute_tool Bash',
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
                'name': 'execute_tool Read',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'logfire.msg_template': 'execute_tool Read',
                    'logfire.msg': 'execute_tool Read',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Read',
                    'gen_ai.tool.call.id': 'tool_no_resp',
                    'gen_ai.tool.call.arguments': {'path': '/tmp'},
                    'logfire.span_type': 'span',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.tool.name': {},
                            'gen_ai.tool.call.id': {},
                            'gen_ai.tool.call.arguments': {'type': 'object'},
                        },
                    },
                },
            },
            {
                'name': 'execute_tool Write',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 6000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_hooks',
                    'code.lineno': 123,
                    'logfire.msg_template': 'execute_tool Write',
                    'logfire.msg': 'execute_tool Write',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Write',
                    'gen_ai.tool.call.id': 'tool_2',
                    'gen_ai.tool.call.arguments': {'path': '/tmp/test'},
                    'logfire.span_type': 'span',
                    'error.type': 'Permission denied',
                    'logfire.level_num': 17,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
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
        _set_parent_span(root_span)
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
                'name': 'execute_tool OrphanTool',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_clear_orphaned_tool_spans',
                    'code.lineno': 123,
                    'logfire.msg_template': 'execute_tool OrphanTool',
                    'logfire.msg': 'execute_tool OrphanTool',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'OrphanTool',
                    'gen_ai.tool.call.id': 'orphan_1',
                    'gen_ai.tool.call.arguments': {},
                    'logfire.span_type': 'span',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
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


# ---------------------------------------------------------------------------
# Cassette-based integration tests (replay through real transport).
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_basic_conversation_cassette(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, exporter: TestExporter
) -> None:
    """Basic conversation replayed from cassette produces correct spans."""
    record = request.config.getoption('--record-claude-cassettes', default=False)
    client = _make_client('basic_conversation.json', monkeypatch=monkeypatch, record=bool(record))
    try:
        await client.connect()
        await client.query('What is 2+2?')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await _close_sdk_streams(client)
        await client.disconnect()

    assert len(collected) >= 2  # system + assistant + result

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-6',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_basic_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-6',
                    'gen_ai.output.messages': [{'role': 'assistant', 'parts': [{'type': 'text', 'content': '4'}]}],
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}],
                    'gen_ai.usage.input_tokens': 3,
                    'gen_ai.usage.output_tokens': 1,
                    'gen_ai.usage.cache_read.input_tokens': 7166,
                    'gen_ai.usage.cache_creation.input_tokens': 2175,
                    'logfire.msg_template': 'chat claude-sonnet-4-6',
                    'logfire.msg': 'chat claude-sonnet-4-6',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.cache_read.input_tokens': {},
                            'gen_ai.usage.cache_creation.input_tokens': {},
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
                    'code.function': 'test_basic_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'Be helpful'}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 3,
                    'gen_ai.usage.output_tokens': 5,
                    'gen_ai.usage.cache_read.input_tokens': 7166,
                    'gen_ai.usage.cache_creation.input_tokens': 2175,
                    'operation.cost': 0.01039005,
                    'gen_ai.conversation.id': '7ed3c21d-374b-491a-8c66-05e191f6a0be',
                    'num_turns': 1,
                    'duration_ms': 2263,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
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
async def test_tool_use_conversation_cassette(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, exporter: TestExporter
) -> None:
    """Tool use conversation: assistant calls Bash, gets result, then responds."""
    record = request.config.getoption('--record-claude-cassettes', default=False)
    client = _make_client('tool_use_conversation.json', monkeypatch=monkeypatch, record=bool(record))
    try:
        await client.connect()
        await client.query('List files in the current directory')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await _close_sdk_streams(client)
        await client.disconnect()

    # assistant (tool_use) + user (tool_result) + assistant (text) + result
    assert len(collected) >= 3

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-6',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-6',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {'type': 'reasoning', 'content': 'Let me list the files in the current directory.'}
                            ],
                        }
                    ],
                    'gen_ai.input.messages': [
                        {
                            'role': 'user',
                            'parts': [{'type': 'text', 'content': 'List files in the current directory'}],
                        }
                    ],
                    'gen_ai.usage.input_tokens': 3,
                    'gen_ai.usage.output_tokens': 0,
                    'gen_ai.usage.cache_read.input_tokens': 8313,
                    'gen_ai.usage.cache_creation.input_tokens': 1027,
                    'logfire.msg_template': 'chat claude-sonnet-4-6',
                    'logfire.msg': 'chat claude-sonnet-4-6',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.cache_read.input_tokens': {},
                            'gen_ai.usage.cache_creation.input_tokens': {},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'execute_tool Bash',
                'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 5000000000,
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': IsStr(),
                    'code.lineno': 123,
                    'logfire.msg_template': 'execute_tool Bash',
                    'logfire.msg': 'execute_tool Bash',
                    'gen_ai.operation.name': 'execute_tool',
                    'gen_ai.tool.name': 'Bash',
                    'gen_ai.tool.call.id': 'toolu_01MRdgcFhYNo1LHvRQKvKckg',
                    'gen_ai.tool.call.arguments': {
                        'command': 'ls',
                        'description': 'List files in current directory',
                    },
                    'logfire.span_type': 'span',
                    'gen_ai.tool.call.result': "{'stdout': 'CHANGELOG.md\\nCLAUDE.md\\nCONTRIBUTING.md\\nLICENSE\\nMakefile\\nREADME.md\\ndist\\ndocs\\nexamples\\nignoreme\\nlogfire\\nlogfire-api\\nmkdocs.yml\\nplans\\npyodide_test\\npyproject.toml\\nrelease\\nscratch\\nsite\\nspecs\\ntests\\nuv.lock', 'stderr': '', 'interrupted': False, 'isImage': False, 'noOutputExpected': False}",
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
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
                'name': 'chat claude-sonnet-4-6',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 7000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-6',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'toolu_01MRdgcFhYNo1LHvRQKvKckg',
                                    'name': 'Bash',
                                    'arguments': {
                                        'command': 'ls',
                                        'description': 'List files in current directory',
                                    },
                                }
                            ],
                        }
                    ],
                    'gen_ai.usage.input_tokens': 3,
                    'gen_ai.usage.output_tokens': 0,
                    'gen_ai.usage.cache_read.input_tokens': 8313,
                    'gen_ai.usage.cache_creation.input_tokens': 1027,
                    'logfire.msg_template': 'chat claude-sonnet-4-6',
                    'logfire.msg': 'chat claude-sonnet-4-6',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.cache_read.input_tokens': {},
                            'gen_ai.usage.cache_creation.input_tokens': {},
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'chat claude-sonnet-4-6',
                'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 8000000000,
                'end_time': 9000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-6',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': """\
Here are the files and directories in the current directory:

| Name | Type |
|------|------|
| `CHANGELOG.md` | File |
| `CLAUDE.md` | File |
| `CONTRIBUTING.md` | File |
| `LICENSE` | File |
| `Makefile` | File |
| `README.md` | File |
| `mkdocs.yml` | File |
| `pyproject.toml` | File |
| `uv.lock` | File |
| `dist/` | Directory |
| `docs/` | Directory |
| `examples/` | Directory |
| `ignoreme/` | Directory |
| `logfire/` | Directory |
| `logfire-api/` | Directory |
| `plans/` | Directory |
| `pyodide_test/` | Directory |
| `release/` | Directory |
| `scratch/` | Directory |
| `site/` | Directory |
| `specs/` | Directory |
| `tests/` | Directory |

There are **9 files** and **12 directories** in the current directory. It looks like a Python project (given `pyproject.toml`, `uv.lock`) — likely the **Logfire** SDK or library based on the `logfire/` and `logfire-api/` directories.\
""",
                                }
                            ],
                        }
                    ],
                    'gen_ai.input.messages': [
                        {
                            'role': 'tool',
                            'parts': [
                                {
                                    'type': 'tool_call_response',
                                    'id': 'toolu_01MRdgcFhYNo1LHvRQKvKckg',
                                    'name': 'Bash',
                                    'response': "{'stdout': 'CHANGELOG.md\\nCLAUDE.md\\nCONTRIBUTING.md\\nLICENSE\\nMakefile\\nREADME.md\\ndist\\ndocs\\nexamples\\nignoreme\\nlogfire\\nlogfire-api\\nmkdocs.yml\\nplans\\npyodide_test\\npyproject.toml\\nrelease\\nscratch\\nsite\\nspecs\\ntests\\nuv.lock', 'stderr': '', 'interrupted': False, 'isImage': False, 'noOutputExpected': False}",
                                }
                            ],
                        }
                    ],
                    'gen_ai.usage.input_tokens': 1,
                    'gen_ai.usage.output_tokens': 1,
                    'gen_ai.usage.cache_read.input_tokens': 9340,
                    'gen_ai.usage.cache_creation.input_tokens': 188,
                    'logfire.msg_template': 'chat claude-sonnet-4-6',
                    'logfire.msg': 'chat claude-sonnet-4-6',
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.response.model': {},
                            'gen_ai.output.messages': {'type': 'array'},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.usage.input_tokens': {},
                            'gen_ai.usage.output_tokens': {},
                            'gen_ai.usage.cache_read.input_tokens': {},
                            'gen_ai.usage.cache_creation.input_tokens': {},
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
                'end_time': 10000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.input.messages': [
                        {
                            'role': 'user',
                            'parts': [{'type': 'text', 'content': 'List files in the current directory'}],
                        }
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'Be helpful'}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 4,
                    'gen_ai.usage.output_tokens': 415,
                    'gen_ai.usage.cache_read.input_tokens': 17653,
                    'gen_ai.usage.cache_creation.input_tokens': 1215,
                    'operation.cost': 0.01608915,
                    'gen_ai.conversation.id': 'ca03765b-a7e1-483b-9629-448c7aba5e7a',
                    'num_turns': 2,
                    'duration_ms': 9352,
                    'logfire.json_schema': {
                        'type': 'object',
                        'properties': {
                            'gen_ai.operation.name': {},
                            'gen_ai.provider.name': {},
                            'gen_ai.system': {},
                            'gen_ai.input.messages': {'type': 'array'},
                            'gen_ai.system_instructions': {'type': 'array'},
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
