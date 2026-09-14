# pyright: reportPrivateUsage=false
"""What a published config does to a session the real `claude` CLI ran.

Every other test in this directory reads what the SDK *would* send: the command line it would spawn,
the tool definitions it would serve. That leaves the other half of every claim open, because this
adapter's whole surface is arguments to a process it does not implement -- only the CLI can say
whether it accepts an empty subagent prompt, reads `CLAUDE_CODE_MAX_OUTPUT_TOKENS` out of the
environment it was spawned with, or lets a model call an in-process tool under a managed name.

So these tests run the real CLI once and keep what it said. The recording machinery is the repository's
own [`fake_claude.py`][], which the SDK spawns instead of `claude`: in record mode it proxies to the
real CLI and tees the stdio protocol to a JSON cassette, and in replay mode -- the default, and what
CI runs -- it replays that cassette, so no credentials, no network, and no `claude` binary are needed.

Re-record with a `claude` binary on the PATH and a real `ANTHROPIC_API_KEY` in the environment, which
is what lets the CLI run without the recorder's own Claude Code configuration:

    uv run --env-file .env pytest tests/agent_control/claude_agent_sdk/test_live.py \
        --record-agent-control-cassettes

[`fake_claude.py`]: ../../otel_integrations/fake_claude.py
"""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Iterator
from contextlib import suppress
from getpass import getuser
from pathlib import Path
from typing import Annotated, Any, cast

import anyio
import pytest
from claude_agent_sdk import (
    AgentDefinition,
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    Message,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    tool,
)

from logfire.agent_control.claude_agent_sdk import agent_control, sdk_mcp_server
from logfire.variables.local import LocalVariableProvider

from .conftest import publish

MODEL = 'claude-haiku-4-5'
"""The cheapest current Claude model, since what is being tested is the CLI rather than the model."""

FAKE_CLAUDE = Path(__file__).parents[2] / 'otel_integrations' / 'fake_claude.py'
"""The record-and-replay stand-in for the `claude` binary, shared with the instrumentation tests."""

CASSETTES = Path(__file__).parent / 'cassettes'


@pytest.fixture
def record(request: pytest.FixtureRequest) -> bool:
    """Whether to run the real CLI and re-record, rather than replay what it said last time."""
    return bool(request.config.getoption('--record-agent-control-cassettes', default=False))


@pytest.fixture
def cli_path(
    request: pytest.FixtureRequest, record: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[str]:
    """The `cli_path` to give the options, wired to the cassette named for the test that asks for it."""
    cassette = CASSETTES / f'{request.node.name}.json'  # pyright: ignore[reportUnknownMemberType]
    fake_claude = str(FAKE_CLAUDE)
    mode = os.stat(fake_claude).st_mode
    if not mode & stat.S_IEXEC:  # pragma: no cover
        os.chmod(fake_claude, mode | stat.S_IEXEC)

    # A cassette replays the CLI's callback requests under the ids the SDK assigned while it was
    # recorded, and `logfire.instrument_claude_agent_sdk()` inserts hook matchers of its own ahead of
    # this agent's, which shifts them. That patching is process-wide and outlives the test that
    # applied it, so say what happened here rather than fail later on a hook that never ran.
    assert not getattr(ClaudeSDKClient, '_is_instrumented_by_logfire', False), (
        'The Claude Agent SDK is instrumented process-wide, and these cassettes were recorded without it.'
    )
    monkeypatch.setenv('CASSETTE_PATH', str(cassette))
    monkeypatch.setenv('CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK', '1')
    if record:  # pragma: no cover
        real_claude = shutil.which('claude')
        if real_claude is None:
            pytest.skip('No `claude` on PATH to record against.')
        if os.environ.get('ANTHROPIC_API_KEY', 'foo') == 'foo':
            # The suite pins a placeholder key for the offline tests, and the CLI cannot authenticate
            # with it. Recording deliberately does not fall back to whatever the recorder is logged
            # in as, because a real key is also what lets the session run without their config.
            pytest.skip('Recording needs a real ANTHROPIC_API_KEY in the environment.')
        CASSETTES.mkdir(exist_ok=True)
        monkeypatch.setenv('CASSETTE_MODE', 'record')
        monkeypatch.setenv('REAL_CLAUDE_PATH', real_claude)
        # An empty config directory, so what gets recorded is a session of *this* agent rather than
        # of the recorder's own Claude Code install: their subagents, their slash commands, and their
        # session hooks would otherwise be in the initialize response, and then in the repository.
        monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    else:
        if not cassette.exists():  # pragma: no cover
            pytest.fail(f'No cassette at {cassette}; record it with --record-agent-control-cassettes.')
        monkeypatch.setenv('CASSETTE_MODE', 'replay')
        monkeypatch.delenv('REAL_CLAUDE_PATH', raising=False)
    yield fake_claude
    if record:  # pragma: no cover
        _scrub(cassette, tmp_path)


def _scrub(cassette: Path, config_dir: Path) -> None:  # pragma: no cover
    """Take the recording machine out of a freshly recorded cassette.

    A session the CLI ran here carries where it ran: the account name, the directories it read and
    wrote, and the account's own rate-limit standing. None of it is what these tests assert on, and
    all of it would be committed, so the paths this test controls and anything carrying the account
    name are replaced, and the rate-limit messages dropped, before the file is kept. What is left is
    the run's own ephemera, such as the CLI's socket path, which names nobody.
    """
    recorded = json.loads(cassette.read_text())
    kept = [entry for entry in recorded['messages'] if entry['message'].get('type') != 'rate_limit_event']
    text = json.dumps({**recorded, 'messages': kept}, indent=2)
    # Whole paths, then the slug the CLI names a transcript directory after, then the account name
    # on its own, for anything the first two did not carry away with them.
    cwd, home = str(Path.cwd()), str(Path.home())
    for value, placeholder in (
        (str(config_dir), '/config'),
        (cwd, '/agent'),
        (home, '/home/user'),
        (cwd.replace('/', '-'), '-agent'),
        (getuser(), 'user'),
    ):
        text = text.replace(json.dumps(value)[1:-1], placeholder)
    cassette.write_text(text + '\n')


async def run(options: ClaudeAgentOptions, prompt: str, *, until: anyio.Event | None = None) -> list[Message]:
    """One whole session: connect, ask, and collect everything the CLI said back.

    A callback the CLI asks for -- a hook, a permission check -- is dispatched by the SDK as its own
    task, so it can still be pending when the last message arrives. `until` is waited for before the
    client is disconnected, which is the last moment such a task can run at all: a test that asserts
    on a callback passes the event that callback sets, rather than racing it.
    """
    client = ClaudeSDKClient(options=options)
    messages: list[Message] = []
    try:
        await client.connect()
        await client.query(prompt)
        async for message in client.receive_response():
            messages.append(message)
        if until is not None:
            with anyio.fail_after(10):
                await until.wait()
    finally:
        await _close(client)
        await client.disconnect()
    return messages


async def _close(client: ClaudeSDKClient) -> None:
    """Close the streams the SDK leaves open, which `filterwarnings = error` would otherwise fail on."""
    query = client._query
    if query is not None:  # pragma: no branch
        for close in (query.close, query._message_send.aclose, query._message_receive.aclose):
            with suppress(Exception):
                await close()
        client._query = None
    transport = client._transport
    stdout = getattr(transport, '_stdout_stream', None)
    if stdout is not None:  # pragma: no branch
        with suppress(Exception):
            await stdout.aclose()


def text_of(messages: list[Message]) -> str:
    """Everything the assistant said, as one string."""
    return '\n'.join(
        block.text
        for message in messages
        if isinstance(message, AssistantMessage)
        for block in message.content
        if isinstance(block, TextBlock)
    )


def tool_calls(messages: list[Message]) -> list[tuple[str, dict[str, Any]]]:
    """The name the model called each tool by, with the arguments it called it with."""
    return [
        (block.name, block.input)
        for message in messages
        if isinstance(message, AssistantMessage)
        for block in message.content
        if isinstance(block, ToolUseBlock)
    ]


def result_of(messages: list[Message]) -> ResultMessage:
    [result] = [message for message in messages if isinstance(message, ResultMessage)]
    return result


def init_of(messages: list[Message]) -> dict[str, Any]:
    """The CLI's own account of the session it just started."""
    [init] = [message for message in messages if isinstance(message, SystemMessage) and message.subtype == 'init']
    return init.data


@pytest.mark.anyio
async def test_a_published_prompt_and_effort_are_what_the_session_runs_on(
    project: LocalVariableProvider, cli_path: str
) -> None:
    """A published block reaches the model, and the CLI accepts the effort a published level sets."""
    publish(
        project,
        'agent__checkout_assistant',
        {
            'instructions': [{'id': 'system', 'instructions': 'Whatever you are asked, reply with only: BANANA'}],
            'settings': {'thinking': 'low'},
        },
    )
    options = agent_control(
        ClaudeAgentOptions(
            system_prompt='You are a concise checkout assistant.', model=MODEL, cli_path=cli_path, setting_sources=[]
        ),
        name='checkout_assistant',
        label='production',
    )
    # The code's prompt is replaced, and `thinking` sets both halves of what the CLI is told.
    assert options.system_prompt == 'Whatever you are asked, reply with only: BANANA'
    assert options.thinking == {'type': 'adaptive'}
    assert options.effort == 'low'

    messages = await run(options, 'What is 2 + 2?')

    # Only the published prompt explains this answer, and the CLI ran the session rather than
    # rejecting `--thinking adaptive --effort low`.
    assert 'BANANA' in text_of(messages)
    assert result_of(messages).is_error is False


@tool('refund_order', 'Refund an order.', {'order_id': Annotated[str, 'The order to refund.']})
async def refund_order(args: dict[str, Any]) -> dict[str, Any]:
    _REFUNDED.append(cast(str, args['order_id']))
    return {'content': [{'type': 'text', 'text': f'Refunded {args["order_id"]}.'}]}


_REFUNDED: list[str] = []
"""The orders the handler above was actually asked to refund, which is what a rename must not change."""


@pytest.mark.anyio
async def test_a_renamed_tool_is_called_under_its_managed_name_and_runs_your_code(
    project: LocalVariableProvider, cli_path: str
) -> None:
    """The model calls `mcp__shop__issue_refund`; the handler and the hook see the code's own name."""
    _REFUNDED.clear()
    seen: list[str] = []
    fired = anyio.Event()

    async def hook(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
        seen.append(cast(dict[str, Any], payload)['tool_name'])
        fired.set()
        return {}

    publish(
        project,
        'agent__checkout_assistant',
        {
            'tool_definitions': [
                {
                    'name': 'refund_order',
                    'new_name': 'issue_refund',
                    'description': 'Issue a refund for one order. Use this whenever a refund is requested.',
                    'parameters': {'order_id': {'description': "The order's id, e.g. 'A-1234'."}},
                }
            ]
        },
    )
    options = agent_control(
        ClaudeAgentOptions(
            system_prompt='You are a checkout assistant. Use your tools; do not ask for confirmation.',
            model=MODEL,
            cli_path=cli_path,
            setting_sources=[],
            mcp_servers={'shop': sdk_mcp_server('shop', tools=[refund_order])},
            # Written against the name the *code* gave the tool; the rename has to carry it along, or
            # the model would be shown a tool it is not allowed to call.
            allowed_tools=['mcp__shop__refund_order'],
            hooks={'PreToolUse': [HookMatcher(matcher='mcp__shop__refund_order', hooks=[hook])]},
        ),
        name='checkout_assistant',
        label='production',
    )
    assert options.allowed_tools == ['mcp__shop__issue_refund']

    messages = await run(options, 'Refund order A-1234, then reply DONE.', until=fired)

    # The model called the managed name, and the arguments arrived under the code's own parameter
    # name. Anything the CLI's own tools did on the way -- looking the tool up by name, here -- is
    # not what this is about, so only the in-process calls are compared.
    assert [call for call in tool_calls(messages) if call[0].startswith('mcp__')] == [
        ('mcp__shop__issue_refund', {'order_id': 'A-1234'})
    ]
    # It reached the handler your code wrote, which was never told a name.
    assert _REFUNDED == ['A-1234']
    # The hook matcher still fired, and was handed the name the code declared.
    assert seen == ['mcp__shop__refund_order']
    assert result_of(messages).is_error is False


def subagent_options(cli_path: str, prompt: str) -> ClaudeAgentOptions:
    """An agent with one subagent, which is the only thing these two tests differ on."""
    return ClaudeAgentOptions(
        system_prompt='You are a concise checkout assistant.',
        model=MODEL,
        cli_path=cli_path,
        setting_sources=[],
        agents={'reviewer': AgentDefinition(description='Reviews refunds.', prompt=prompt)},
    )


@pytest.mark.anyio
async def test_the_cli_leaves_out_a_subagent_with_no_prompt(cli_path: str) -> None:
    """The CLI behaviour the adapter refuses a removal on, pinned so the refusal keeps its reason.

    Nothing about Agent Control is exercised here. This is the fact the test below is built on: a
    subagent is declared to the CLI *by* its prompt, and one whose prompt is empty is not in the
    session's agent list at all -- so "empty the prompt and keep the subagent", which is what
    removing a block would otherwise mean, is not a state this SDK can be in.
    """
    messages = await run(subagent_options(cli_path, ''), 'Reply with only: OK')

    assert 'reviewer' not in init_of(messages)['agents']
    assert result_of(messages).is_error is False


@pytest.mark.anyio
async def test_a_subagent_whose_block_was_removed_is_still_in_the_session(
    project: LocalVariableProvider, cli_path: str
) -> None:
    """A removal the CLI cannot express is reported, and the subagent is still there."""
    publish(project, 'agent__checkout_assistant', {'instructions': [{'id': 'agent:reviewer'}]})
    with pytest.warns(UserWarning, match="removes instruction block 'agent:reviewer'"):
        options = agent_control(
            subagent_options(cli_path, 'You review refunds.'), name='checkout_assistant', label='production'
        )
    assert options.agents == {'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.')}

    messages = await run(options, 'Reply with only: OK')

    # Which is what keeps the subagent -- its description and its tool list included -- in a session
    # that a published removal would otherwise have taken it out of.
    assert 'reviewer' in init_of(messages)['agents']
    assert result_of(messages).is_error is False


@pytest.mark.anyio
async def test_a_published_max_tokens_reaches_the_cli(project: LocalVariableProvider, cli_path: str) -> None:
    """`max_tokens` is applied through the CLI's environment, and the CLI reads it from there."""
    publish(project, 'agent__checkout_assistant', {'settings': {'max_tokens': 16}})
    options = agent_control(
        ClaudeAgentOptions(
            system_prompt='You are a concise checkout assistant.', model=MODEL, cli_path=cli_path, setting_sources=[]
        ),
        name='checkout_assistant',
        label='production',
    )
    assert options.env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] == '16'

    messages = await run(options, 'Write a 200 word essay about bananas.')

    # The CLI stopped the response at exactly the published cap and named the variable it read it
    # from, which is what "this setting is editable" has to mean for a setting this SDK has no field
    # for. A CLI that ignored the environment would have answered the question.
    result = result_of(messages)
    assert result.is_error is True
    assert '16 output token maximum' in cast(str, result.result)


@pytest.mark.anyio
async def test_a_published_timeout_reaches_the_cli(project: LocalVariableProvider, cli_path: str) -> None:
    """`timeout` is applied through the CLI's environment too, and the CLI honours it as a deadline."""
    publish(project, 'agent__checkout_assistant', {'settings': {'timeout': 0.001}})
    options = agent_control(
        ClaudeAgentOptions(
            system_prompt='You are a concise checkout assistant.', model=MODEL, cli_path=cli_path, setting_sources=[]
        ),
        name='checkout_assistant',
        label='production',
    )
    # Seconds in the contract, whole milliseconds in the environment, by the core's own conversion.
    assert options.env['API_TIMEOUT_MS'] == '1'

    messages = await run(options, 'Reply with only: OK')

    # A millisecond is not enough for any request, so the CLI gave up on its own deadline rather than
    # on one nobody set -- which is the whole of what this setting being editable means here.
    result = result_of(messages)
    assert result.is_error is True
    assert 'timed out' in cast(str, result.result).lower()
