# pyright: reportPrivateUsage=false
"""Cassette-based tests for Claude Agent SDK instrumentation.

Uses a fake claude process that replays recorded stdin/stdout messages,
exercising the real SubprocessCLITransport instead of a mock.

Recording cassettes (requires a real `claude` CLI with valid credentials):
    uv run pytest tests/otel_integrations/test_claude_agent_sdk_cassette.py --record-cassettes

Replaying (default, no real CLI needed):
    uv run pytest tests/otel_integrations/test_claude_agent_sdk_cassette.py
"""

from __future__ import annotations

import gc
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

pytest.importorskip('claude_agent_sdk', reason='claude_agent_sdk requires Python 3.10+')

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from dirty_equals import IsStr
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
            f'Record it with: uv run pytest {__file__} --record-cassettes -k <test_name>'
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


@pytest.mark.anyio
async def test_basic_conversation_cassette(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, exporter: TestExporter
) -> None:
    """Basic conversation replayed from cassette produces correct spans."""
    record = request.config.getoption('--record-cassettes', default=False)
    client = _make_client('basic_conversation.json', monkeypatch=monkeypatch, record=bool(record))
    try:
        await client.connect()
        await client.query('What is 2+2?')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    assert len(collected) >= 2  # system + assistant + result

    if not record:
        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': 'chat claude-sonnet-4-6',
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
                        'gen_ai.response.model': 'claude-sonnet-4-6',
                        'gen_ai.output.messages': [{'role': 'assistant', 'parts': [{'type': 'text', 'content': '4'}]}],
                        'gen_ai.input.messages': [
                            {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}
                        ],
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
                        'code.filepath': 'test_claude_agent_sdk_cassette.py',
                        'code.function': 'test_basic_conversation_cassette',
                        'code.lineno': 123,
                        'gen_ai.operation.name': 'invoke_agent',
                        'gen_ai.provider.name': 'anthropic',
                        'gen_ai.system': 'anthropic',
                        'gen_ai.input.messages': [
                            {'role': 'user', 'parts': [{'type': 'text', 'content': 'What is 2+2?'}]}
                        ],
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
    record = request.config.getoption('--record-cassettes', default=False)
    client = _make_client('tool_use_conversation.json', monkeypatch=monkeypatch, record=bool(record))
    try:
        await client.connect()
        await client.query('List files in the current directory')
        collected = [msg async for msg in client.receive_response()]
    finally:
        await client.disconnect()

    # assistant (tool_use) + user (tool_result) + assistant (text) + result
    assert len(collected) >= 3

    if not record:
        assert exporter.exported_spans_as_dict(parse_json_attributes=True) == snapshot(
            [
                {
                    'name': 'chat claude-sonnet-4-6',
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
                        'gen_ai.response.model': 'claude-sonnet-4-6',
                        'gen_ai.output.messages': [
                            {
                                'role': 'assistant',
                                'parts': [
                                    {
                                        'type': 'thinking',
                                        'content': 'Let me list the files in the current directory.',
                                        'signature': 'EuoBClkIDBgCKkASXqZcani1cS2F0io8DhUZtOWls/UWUA6bZT1K3rfAItRtZNk2mY7QJlEXq/45nQ31If9WpgVb/W9hWond2BSVMhFjbGF1ZGUtc29ubmV0LTQtNhIMo+SLoTXu/es6+jKxGgzhGqGCjpe87cObsPoiMM1hGKFBHv/PenktJb+hzvA/EGZRy5MR4b0+VJz/iDgkXhp7j0LcjJrD4BeFEeeFlio/kvJLtts/vOiMgrO3lD1XzJC0hX3hTCxDV3Ye6oMoanejZW5bGZoJNGbhFBqMG8pJog7gkLEPOpeZoyZlhMmsGAE=',
                                    }
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
                    'name': 'execute_tool {tool_name}',
                    'context': {'trace_id': 1, 'span_id': 7, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 5000000000,
                    'end_time': 6000000000,
                    'attributes': {
                        'code.filepath': IsStr(),
                        'tool_name': 'Bash',
                        'code.lineno': 123,
                        'gen_ai.operation.name': 'execute_tool',
                        'gen_ai.tool.name': 'Bash',
                        'gen_ai.tool.call.id': 'toolu_01MRdgcFhYNo1LHvRQKvKckg',
                        'gen_ai.tool.call.arguments': {
                            'command': 'ls',
                            'description': 'List files in current directory',
                        },
                        'gen_ai.tool.call.result': "{'stdout': 'CHANGELOG.md\\nCLAUDE.md\\nCONTRIBUTING.md\\nLICENSE\\nMakefile\\nREADME.md\\ndist\\ndocs\\nexamples\\nignoreme\\nlogfire\\nlogfire-api\\nmkdocs.yml\\nplans\\npyodide_test\\npyproject.toml\\nrelease\\nscratch\\nsite\\nspecs\\ntests\\nuv.lock', 'stderr': '', 'interrupted': False, 'isImage': False, 'noOutputExpected': False}",
                        'logfire.msg_template': 'execute_tool {tool_name}',
                        'logfire.msg': 'execute_tool Bash',
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
                        'logfire.span_type': 'span',
                    },
                },
                {
                    'name': 'chat claude-sonnet-4-6',
                    'context': {'trace_id': 1, 'span_id': 5, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 4000000000,
                    'end_time': 7000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk_cassette.py',
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
                        'gen_ai.usage.cache_read.input_tokens': 8313,
                        'gen_ai.usage.cache_creation.input_tokens': 1027,
                        'logfire.msg_template': 'chat claude-sonnet-4-6',
                        'logfire.msg': 'chat claude-sonnet-4-6',
                        'logfire.span_type': 'span',
                        'gen_ai.usage.input_tokens': 3,
                        'gen_ai.usage.output_tokens': 0,
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
                    },
                },
                {
                    'name': 'chat claude-sonnet-4-6',
                    'context': {'trace_id': 1, 'span_id': 9, 'is_remote': False},
                    'parent': {'trace_id': 1, 'span_id': 1, 'is_remote': False},
                    'start_time': 8000000000,
                    'end_time': 9000000000,
                    'attributes': {
                        'code.filepath': 'test_claude_agent_sdk_cassette.py',
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
                                'name': 'Bash',
                                'parts': [
                                    {
                                        'type': 'tool_call_response',
                                        'id': 'toolu_01MRdgcFhYNo1LHvRQKvKckg',
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
                        'code.filepath': 'test_claude_agent_sdk_cassette.py',
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
