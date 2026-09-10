"""Wiring the adapter to a real session: what reaches the CLI, and what happens when Logfire cannot."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import anyio
import pytest
from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookCallback,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
)
from claude_agent_sdk._internal.transport import Transport
from inline_snapshot import snapshot

import logfire
from logfire.agent_control.claude_agent_sdk import ManagedAgent, agent_control
from logfire.testing import CaptureLogfire
from logfire.variables import Variable
from logfire.variables.local import LocalVariableProvider

from .agents import checkout_options
from .conftest import call_tool, cli_arg, publish, wire_tools, withdraw


class CaptureTransport(Transport):
    """A stand-in for the `claude` subprocess: it records what the SDK sends and answers control requests.

    The SDK talks to the CLI over stdio and nothing else, so replacing the transport is enough to
    drive a real `ClaudeSDKClient` through a real connect, initialize, and model switch offline.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._send, self._receive = anyio.create_memory_object_stream[dict[str, Any]](100)

    async def connect(self) -> None:
        pass

    async def write(self, data: str) -> None:
        message: dict[str, Any] = json.loads(data)
        self.sent.append(message)
        if message.get('type') == 'control_request':
            await self._send.send(
                {
                    'type': 'control_response',
                    'response': {'subtype': 'success', 'request_id': message['request_id'], 'response': {}},
                }
            )

    async def read_messages(self) -> AsyncIterator[dict[str, Any]]:
        async for message in self._receive:
            yield message

    async def close(self) -> None:
        await self._send.aclose()
        await self._receive.aclose()

    def is_ready(self) -> bool:
        return True

    async def end_input(self) -> None:
        pass

    def requests(self, subtype: str) -> list[dict[str, Any]]:
        return [
            message['request']
            for message in self.sent
            if message.get('type') == 'control_request' and message['request']['subtype'] == subtype
        ]


def test_the_agent_has_to_be_named() -> None:
    with pytest.raises(ValueError, match='has nothing a variable key can be made of'):
        agent_control(checkout_options(), name='  ')


def test_a_managed_agent_says_what_it_manages() -> None:
    assert repr(ManagedAgent('checkout-assistant', label='canary')) == snapshot(
        "ManagedAgent(name='checkout-assistant', label='canary')"
    )


def test_every_section_reaches_the_command_line_at_once(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout_assistant',
        {
            'instructions': [{'id': 'system', 'instructions': 'You are a refund specialist.'}],
            'model': 'anthropic:claude-opus-4-5',
            'settings': {'thinking': 'medium', 'max_tokens': 2048},
            'tool_definitions': [{'name': 'refund_order', 'new_name': 'issue_refund'}],
        },
    )
    options = agent_control(checkout_options(), name='checkout_assistant', label='production')
    assert cli_arg(options, '--system-prompt') == 'You are a refund specialist.'
    assert cli_arg(options, '--model') == 'claude-opus-4-5'
    assert cli_arg(options, '--effort') == 'medium'
    assert cli_arg(options, '--allowedTools') == 'mcp__shop__issue_refund,Read(*.py)'
    assert options.env['CLAUDE_CODE_MAX_OUTPUT_TOKENS'] == '2048'


def test_what_the_caller_passes_afterwards_beats_what_was_published(project: LocalVariableProvider) -> None:
    from dataclasses import replace

    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'})
    options = agent_control(checkout_options(), name='checkout_assistant', label='production')
    # The adapter returns options; anything a caller changes after the call is the last word.
    assert replace(options, model='claude-haiku-4-5').model == 'claude-haiku-4-5'


def test_the_options_the_caller_built_are_never_mutated(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'})
    code = checkout_options()
    managed = agent_control(code, name='checkout_assistant', label='production')
    assert managed is not code
    assert code.model == 'claude-fable-5-1'


def test_a_config_that_reaches_nothing_can_fail_the_call_instead(project: LocalVariableProvider) -> None:
    publish(
        project, 'agent__checkout_assistant', {'instructions': [{'id': 'agent:auditor', 'instructions': 'You audit.'}]}
    )
    with pytest.raises(ValueError, match="addresses instruction block 'agent:auditor'"):
        agent_control(checkout_options(), name='checkout_assistant', label='production', on_unmatched='error')


def test_a_config_that_reaches_nothing_can_be_left_unsaid(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'settings': {'temperature': 0.4}})
    # `filterwarnings = ['error']` makes this fail if anything is warned.
    assert (
        agent_control(checkout_options(), name='checkout_assistant', label='production', on_unmatched='ignore')
        is not None
    )


def test_no_logfire_project_runs_the_agent_on_its_code() -> None:
    code = checkout_options()
    assert agent_control(code, name='checkout_assistant') is code


def test_an_unreachable_logfire_runs_the_agent_on_its_code(
    project: LocalVariableProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError('the variables API is down')

    monkeypatch.setattr(Variable, 'get', boom)
    code = checkout_options()
    with pytest.warns(UserWarning, match='the variables API is down'):
        assert agent_control(code, name='checkout_assistant') is code


def test_the_baseline_is_not_published_when_it_must_not_be(project: LocalVariableProvider) -> None:
    managed = ManagedAgent('checkout_assistant', publish_baseline=False)
    managed.options(checkout_options())
    assert managed._publish_thread is None  # pyright: ignore[reportPrivateUsage]
    assert project.get_variable_config('agent__checkout_assistant') is None


def test_a_session_carries_the_version_that_produced_it(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'}, label='canary')
    managed = ManagedAgent('checkout_assistant', label='canary')
    with managed.session(checkout_options()) as options:
        assert options.model == 'claude-opus-4-5'
        logfire.info('the session')
    [session] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'the session']
    assert session['attributes']['logfire.variables.agent__checkout_assistant'] == 'canary'
    assert session['attributes']['logfire.variables.agent__checkout_assistant.version'] == '1'


def test_a_managed_subagent_prompt_reaches_the_session(project: LocalVariableProvider) -> None:
    publish(
        project,
        'agent__checkout_assistant',
        {'instructions': [{'id': 'agent:reviewer', 'instructions': 'You review refunds carefully.'}]},
    )
    options = agent_control(checkout_options(), name='checkout_assistant', label='production')

    async def connect() -> list[dict[str, Any]]:
        transport = CaptureTransport()
        client = ClaudeSDKClient(options=options, transport=transport)
        await client.connect()
        await client.query('Refund my last order.')
        await transport.end_input()
        await client.disconnect()
        assert transport.is_ready()
        return transport.requests('initialize')

    # Subagents travel in the `initialize` control request rather than on the command line, so this
    # is the only place a managed subagent prompt can be seen going out.
    [initialize] = anyio.run(connect)
    assert initialize['agents']['reviewer']['prompt'] == 'You review refunds carefully.'


def test_a_model_published_mid_session_reaches_a_connected_client(project: LocalVariableProvider) -> None:
    options = checkout_options()
    managed = ManagedAgent('checkout_assistant', label='production')

    async def run() -> list[dict[str, Any]]:
        transport = CaptureTransport()
        client = ClaudeSDKClient(options=options, transport=transport)
        await client.connect()
        assert await managed.refresh_model(client, options) == 'claude-fable-5-1'
        publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'})
        assert await managed.refresh_model(client, options) == 'claude-opus-4-5'
        await client.disconnect()
        return transport.requests('set_model')

    assert [request['model'] for request in anyio.run(run)] == ['claude-fable-5-1', 'claude-opus-4-5']


def test_refreshing_to_a_model_this_sdk_cannot_run_keeps_the_code_model(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'bedrock:claude-fable-5-1'})
    options = checkout_options()
    managed = ManagedAgent('checkout_assistant', label='production')

    async def run() -> str | None:
        transport = CaptureTransport()
        client = ClaudeSDKClient(options=options, transport=transport)
        await client.connect()
        try:
            return await managed.refresh_model(client, options)
        finally:
            await client.disconnect()

    with pytest.warns(UserWarning, match="selects model 'bedrock:claude-fable-5-1'"):
        assert anyio.run(run) == 'claude-fable-5-1'


def test_refreshing_without_a_project_keeps_the_code_model() -> None:
    options = ClaudeAgentOptions()
    managed = ManagedAgent('checkout_assistant')

    async def run() -> str | None:
        transport = CaptureTransport()
        client = ClaudeSDKClient(options=options, transport=transport)
        await client.connect()
        try:
            return await managed.refresh_model(client, options)
        finally:
            await client.disconnect()

    assert anyio.run(run) is None


async def _noop_hook(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
    return {}  # pragma: no cover


def _hooks(hook: HookCallback = _noop_hook) -> dict[str, list[HookMatcher]]:
    return {'PreToolUse': [HookMatcher(hooks=[hook])]}


def _pre_tool_use(tool_name: str) -> HookInput:
    payload: dict[str, Any] = {
        'hook_event_name': 'PreToolUse',
        'session_id': 's',
        'transcript_path': '/t',
        'cwd': '/c',
        'tool_name': tool_name,
        'tool_input': {'order_id': 'A-1234'},
        'tool_use_id': 'call-1',
    }
    return cast(HookInput, payload)


def _run_hook(options: ClaudeAgentOptions, tool_name: str) -> None:
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['PreToolUse']
    anyio.run(matchers[0].hooks[0], _pre_tool_use(tool_name), 'call-1', HookContext(signal=None))


def test_a_hook_carries_the_version_that_configured_the_session(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    async def hook(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
        logfire.info('the hook')
        return {}

    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'}, label='canary')
    options = agent_control(checkout_options(hooks=_hooks(hook)), name='checkout_assistant', label='canary')
    # The session is started by the caller, long after this returned, so the resolution is re-entered
    # at the one seam left: the callbacks the applied options carry.
    _run_hook(options, 'Read')
    [span] = [span for span in capfire.exporter.exported_spans_as_dict() if span['name'] == 'the hook']
    assert span['attributes']['logfire.variables.agent__checkout_assistant'] == 'canary'
    assert span['attributes']['logfire.variables.agent__checkout_assistant.version'] == '1'


def test_two_sessions_with_different_configs_never_see_each_others(
    project: LocalVariableProvider, capfire: CaptureLogfire
) -> None:
    seen: list[str] = []

    async def hook(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
        seen.append(cast(dict[str, Any], payload)['tool_name'])
        logfire.info('the hook')
        return {}

    publish(
        project,
        'agent__checkout_assistant',
        {'tool_definitions': [{'name': 'refund_order', 'new_name': 'issue_refund'}]},
        label='production',
    )
    publish(
        project,
        'agent__checkout_assistant',
        {'tool_definitions': [{'name': 'refund_order', 'new_name': 'send_refund'}]},
        label='canary',
    )
    code = checkout_options(hooks=_hooks(hook))
    live = ManagedAgent('checkout_assistant', label='production')
    trial = ManagedAgent('checkout_assistant', label='canary')

    # Interleaved on purpose: nothing about one session may be reachable from the other, and the
    # adapter keeps no per-instance state a second run could overwrite.
    with live.session(code) as live_options, trial.session(code) as trial_options:
        assert [tool['name'] for tool in wire_tools(live_options, 'shop')] == ['issue_refund', 'search']
        assert [tool['name'] for tool in wire_tools(trial_options, 'shop')] == ['send_refund', 'search']
        _run_hook(trial_options, 'mcp__shop__send_refund')
        _run_hook(live_options, 'mcp__shop__issue_refund')

    assert seen == ['mcp__shop__refund_order', 'mcp__shop__refund_order']
    labels = [
        span['attributes']['logfire.variables.agent__checkout_assistant']
        for span in capfire.exporter.exported_spans_as_dict()
        if span['name'] == 'the hook'
    ]
    assert labels == ['canary', 'production']


def test_a_rename_published_changed_and_withdrawn_over_a_tool_loop(project: LocalVariableProvider) -> None:
    seen: list[str] = []

    async def hook(payload: HookInput, tool_use_id: str | None, context: HookContext) -> HookJSONOutput:
        seen.append(cast(dict[str, Any], payload)['tool_name'])
        return {}

    def session(advertised: str) -> None:
        """One session's worth of what a rename touches: the tool list, a hook, and the handler."""
        options = agent_control(checkout_options(hooks=_hooks(hook)), name='checkout_assistant', label='production')
        assert [tool['name'] for tool in wire_tools(options, 'shop')] == [advertised, 'search']
        assert options.allowed_tools == [f'mcp__shop__{advertised}', 'Read(*.py)']
        _run_hook(options, f'mcp__shop__{advertised}')
        assert call_tool(options, 'shop', advertised, {'order_id': 'A-1234'})['content'][0]['text'] == 'refunded A-1234'

    publish(project, 'agent__checkout_assistant', {'tool_definitions': [{'name': 'refund_order', 'new_name': 'a'}]})
    session('a')
    publish(project, 'agent__checkout_assistant', {'tool_definitions': [{'name': 'refund_order', 'new_name': 'b'}]})
    session('b')
    withdraw(project, 'agent__checkout_assistant')
    session('refund_order')
    # Every session's hook was told the name the code declared, whatever the model was calling it.
    assert seen == ['mcp__shop__refund_order', 'mcp__shop__refund_order', 'mcp__shop__refund_order']


def test_an_agent_can_be_all_config_and_no_code(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'instructions': 'You are a checkout assistant.'})
    options = agent_control(name='checkout_assistant', label='production')
    assert cli_arg(options, '--system-prompt') == 'You are a checkout assistant.'
