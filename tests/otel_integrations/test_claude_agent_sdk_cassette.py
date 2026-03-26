# pyright: reportPrivateUsage=false
"""POC: Cassette-based tests for Claude Agent SDK instrumentation.

Uses a fake claude process that replays recorded stdin/stdout messages,
exercising the real SubprocessCLITransport instead of a mock.
"""

from __future__ import annotations

import gc
import os
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from inline_snapshot import snapshot

import logfire
from logfire.testing import TestExporter

pytestmark = pytest.mark.filterwarnings('ignore::pytest.PytestUnraisableExceptionWarning')

FAKE_CLAUDE = Path(__file__).parent / 'fake_claude.py'
CASSETTES_DIR = Path(__file__).parent / 'cassettes' / 'test_claude_agent_sdk'


def _force_gc() -> None:
    """Force GC to collect SDK internal streams, suppressing ResourceWarning."""
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


def _make_client(cassette_name: str, *, system_prompt: str = 'Be helpful') -> ClaudeSDKClient:
    """Create a ClaudeSDKClient that talks to the fake_claude replay script."""
    cassette_path = CASSETTES_DIR / cassette_name
    if not cassette_path.exists():
        raise FileNotFoundError(
            f'Cassette not found: {cassette_path}\n'
            f'Record it with: CASSETTE_MODE=record CASSETTE_PATH={cassette_path} ...'
        )

    # Make fake_claude.py executable
    fake_claude_path = str(FAKE_CLAUDE)
    st = os.stat(fake_claude_path)
    if not (st.st_mode & stat.S_IEXEC):
        os.chmod(fake_claude_path, st.st_mode | stat.S_IEXEC)

    # The SDK will spawn fake_claude.py as a subprocess.
    # Environment variables tell it to replay from the cassette.
    os.environ['CASSETTE_PATH'] = str(cassette_path)
    os.environ['CASSETTE_MODE'] = 'replay'
    os.environ['CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK'] = '1'

    return ClaudeSDKClient(
        options=ClaudeAgentOptions(
            system_prompt=system_prompt,
            cli_path=fake_claude_path,
        ),
    )


@pytest.mark.anyio
async def test_basic_conversation_cassette(exporter: TestExporter) -> None:
    """Basic conversation replayed from cassette produces correct spans."""
    client = _make_client('basic_conversation.json')
    try:
        await client.connect()
        await client.query('What is 2+2?')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert len(collected) == 2  # assistant + result

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk_cassette.py',
                    'code.function': 'test_basic_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {'role': 'assistant', 'parts': [{'type': 'text', 'content': '2 + 2 = 4.'}]}
                    ],
                    'gen_ai.input.messages': [{'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}],
                    'gen_ai.usage.input_tokens': 12,
                    'gen_ai.usage.output_tokens': 8,
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
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
                    'code.filepath': 'test_claude_agent_sdk_cassette.py',
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
                    'gen_ai.usage.input_tokens': 12,
                    'gen_ai.usage.output_tokens': 8,
                    'operation.cost': 0.001,
                    'gen_ai.conversation.id': 'sess_abc123',
                    'num_turns': 1,
                    'duration_ms': 1234,
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
async def test_tool_use_conversation_cassette(exporter: TestExporter) -> None:
    """Tool use conversation: assistant calls Bash, gets result, then responds."""
    client = _make_client('tool_use_conversation.json')
    try:
        await client.connect()
        await client.query('List files in the current directory')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    # assistant (tool_use) + user (tool_result) + assistant (text) + result
    assert len(collected) >= 3

    assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
        [
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 3, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 2000000000,
                'end_time': 3000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk_cassette.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'tool_call',
                                    'id': 'toolu_01ABC',
                                    'name': 'Bash',
                                    'arguments': {'command': 'ls'},
                                }
                            ],
                        }
                    ],
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'List files in the current directory'}]}
                    ],
                    'gen_ai.usage.input_tokens': 20,
                    'gen_ai.usage.output_tokens': 15,
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
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
                        },
                    },
                    'logfire.span_type': 'span',
                },
            },
            {
                'name': 'chat claude-sonnet-4-20250514',
                'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                'start_time': 4000000000,
                'end_time': 5000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk_cassette.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'chat',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.response.model': 'claude-sonnet-4-20250514',
                    'gen_ai.output.messages': [
                        {
                            'role': 'assistant',
                            'parts': [
                                {
                                    'type': 'text',
                                    'content': 'The directory contains: file1.txt, file2.txt, and README.md.',
                                }
                            ],
                        }
                    ],
                    'gen_ai.usage.input_tokens': 35,
                    'gen_ai.usage.output_tokens': 20,
                    'logfire.msg_template': 'chat claude-sonnet-4-20250514',
                    'logfire.msg': 'chat claude-sonnet-4-20250514',
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
                'end_time': 6000000000,
                'attributes': {
                    'code.filepath': 'test_claude_agent_sdk_cassette.py',
                    'code.function': 'test_tool_use_conversation_cassette',
                    'code.lineno': 123,
                    'gen_ai.operation.name': 'invoke_agent',
                    'gen_ai.provider.name': 'anthropic',
                    'gen_ai.system': 'anthropic',
                    'gen_ai.input.messages': [
                        {'role': 'user', 'parts': [{'type': 'text', 'content': 'List files in the current directory'}]}
                    ],
                    'gen_ai.system_instructions': [{'type': 'text', 'content': 'Be helpful'}],
                    'logfire.msg_template': 'invoke_agent',
                    'logfire.msg': 'invoke_agent',
                    'logfire.span_type': 'span',
                    'gen_ai.usage.input_tokens': 55,
                    'gen_ai.usage.output_tokens': 35,
                    'operation.cost': 0.003,
                    'gen_ai.conversation.id': 'sess_tool123',
                    'num_turns': 2,
                    'duration_ms': 2500,
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
