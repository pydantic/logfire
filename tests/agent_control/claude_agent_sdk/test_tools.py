"""What a published `tool_definitions` section does to the tools the model is shown."""

from __future__ import annotations

import json
from typing import Any, cast

import anyio
import pytest
from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    HookContext,
    HookInput,
    HookJSONOutput,
    HookMatcher,
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    PermissionUpdate,
    ToolPermissionContext,
    create_sdk_mcp_server,
)
from claude_agent_sdk.types import PermissionRuleValue
from inline_snapshot import snapshot

from logfire.agent_control.claude_agent_sdk import ManagedAgent, agent_control, sdk_mcp_server
from logfire.variables.local import LocalVariableProvider

from .agents import checkout_options, refund_order, search
from .conftest import call_tool, cli_arg, publish, wire_tools

RENAME: dict[str, Any] = {
    'name': 'refund_order',
    'new_name': 'issue_refund',
    'description': 'Issue a refund for an order.',
    'parameters': {'order_id': {'description': "The order's id, e.g. 'A-1234'."}},
}


def managed(project: LocalVariableProvider, overrides: list[dict[str, Any]], **options: Any) -> ClaudeAgentOptions:
    publish(project, 'agent__checkout_assistant', {'tool_definitions': overrides})
    return agent_control(checkout_options(**options), name='checkout_assistant', label='production')


def test_a_managed_definition_is_what_the_model_is_shown(project: LocalVariableProvider) -> None:
    options = managed(project, [RENAME])
    assert wire_tools(options, 'shop') == snapshot(
        [
            {
                'description': 'Issue a refund for an order.',
                'inputSchema': {
                    'properties': {'order_id': {'type': 'string', 'description': "The order's id, e.g. 'A-1234'."}},
                    'required': ['order_id'],
                    'type': 'object',
                },
                'name': 'issue_refund',
            },
            {
                'description': 'Search the catalogue.',
                'inputSchema': {'properties': {'query': {'type': 'string'}}, 'required': ['query'], 'type': 'object'},
                'name': 'search',
            },
        ]
    )


def test_an_untouched_tool_keeps_its_exact_definition(project: LocalVariableProvider) -> None:
    code = checkout_options()
    options = managed(project, [RENAME])
    assert wire_tools(options, 'shop')[1] == wire_tools(code, 'shop')[1]


def test_a_renamed_tool_still_reaches_the_code_that_implements_it(project: LocalVariableProvider) -> None:
    options = managed(project, [RENAME])
    # The model calls the managed name; the handler is the same function object and is never told one.
    assert call_tool(options, 'shop', 'issue_refund', {'order_id': 'A-1234'}) == snapshot(
        {'content': [{'text': 'refunded A-1234', 'type': 'text'}], 'isError': False}
    )


def test_a_rename_follows_through_to_permissions_and_hooks(project: LocalVariableProvider) -> None:
    async def hook(*args: Any) -> HookJSONOutput:
        return {}  # pragma: no cover

    hooks = {
        'PreToolUse': [
            HookMatcher(matcher='mcp__shop__refund_order|Bash', hooks=[hook]),
            HookMatcher(matcher='mcp__shop__.*', hooks=[hook]),
            HookMatcher(hooks=[hook]),
        ]
    }
    options = managed(
        project,
        [RENAME],
        disallowed_tools=['mcp__shop__refund_order(A-*)'],
        hooks=hooks,
    )
    assert options.allowed_tools == ['mcp__shop__issue_refund', 'Read(*.py)']
    assert options.disallowed_tools == ['mcp__shop__issue_refund(A-*)']
    assert cli_arg(options, '--allowedTools') == 'mcp__shop__issue_refund,Read(*.py)'
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['PreToolUse']
    assert [matcher.matcher for matcher in matchers] == ['mcp__shop__issue_refund|Bash', 'mcp__shop__.*', None]


def test_a_description_only_change_renames_nothing(project: LocalVariableProvider) -> None:
    options = managed(project, [{'name': 'search', 'description': 'Search the shop catalogue.'}])
    assert options.allowed_tools == ['mcp__shop__refund_order', 'Read(*.py)']
    assert call_tool(options, 'shop', 'search', {'query': 'shoes'})['content'][0]['text'] == 'found shoes'
    assert [(tool['name'], tool['description']) for tool in wire_tools(options, 'shop')] == snapshot(
        [('refund_order', 'Refund an order.'), ('search', 'Search the shop catalogue.')]
    )


def test_an_override_narrowed_to_one_server_leaves_the_other_alone(project: LocalVariableProvider) -> None:
    servers = {
        'shop': sdk_mcp_server('shop', tools=[search]),
        'crm': sdk_mcp_server('crm', tools=[search]),
    }
    options = managed(
        project,
        [{'name': 'search', 'toolset': 'crm', 'description': 'Search CRM records.'}],
        mcp_servers=servers,
    )
    assert wire_tools(options, 'shop')[0]['description'] == 'Search the catalogue.'
    assert wire_tools(options, 'crm')[0]['description'] == 'Search CRM records.'


def test_a_tool_no_server_advertises_is_reported(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="patches tool 'cancel_order', which no toolset advertises"):
        options = managed(project, [{'name': 'cancel_order', 'description': 'Cancel it.'}])
    assert wire_tools(options, 'shop') == wire_tools(checkout_options(), 'shop')


def test_tools_of_a_server_the_adapter_cannot_rebuild_are_reported(project: LocalVariableProvider) -> None:
    # `create_sdk_mcp_server` keeps no reference to its definitions, so its tools are neither listed
    # in the baseline nor patchable -- and an override naming one has to say so rather than vanish.
    sealed = {'shop': create_sdk_mcp_server('shop', tools=[refund_order])}
    with pytest.warns(UserWarning, match="patches tool 'refund_order', which no toolset advertises"):
        options = managed(project, [{'name': 'refund_order', 'description': 'Issue a refund.'}], mcp_servers=sealed)
    assert wire_tools(options, 'shop')[0]['description'] == 'Refund an order.'


def test_a_rename_onto_a_name_in_use_keeps_every_tool_callable(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="renames 'refund_order' to 'search', which is already advertised"):
        options = managed(project, [{'name': 'refund_order', 'new_name': 'search'}])
    assert [tool['name'] for tool in wire_tools(options, 'shop')] == ['refund_order', 'search']


def test_a_rebuilt_server_keeps_its_place_and_its_version(project: LocalVariableProvider) -> None:
    servers = {
        'shop': sdk_mcp_server('shop', '2.0.0', [refund_order]),
        'crm': {'type': 'http', 'url': 'https://crm.example'},
    }
    options = managed(project, [RENAME], mcp_servers=servers)
    assert list(options.mcp_servers) == ['shop', 'crm']  # type: ignore[arg-type]
    assert options.mcp_servers['shop']['instance'].version == '2.0.0'  # type: ignore[index]


def test_the_adapters_bookkeeping_never_reaches_the_command_line(project: LocalVariableProvider) -> None:
    # Everything but `instance` is JSON-encoded into `--mcp-config`, so remembering a server's tools
    # on the config dict would either leak them onto the command line or fail to serialize.
    options = managed(project, [RENAME])
    mcp_config = cli_arg(options, '--mcp-config')
    assert mcp_config is not None
    assert json.loads(mcp_config) == {'mcpServers': {'shop': {'type': 'sdk', 'name': 'shop'}}}


def test_nothing_published_leaves_the_servers_the_caller_built(project: LocalVariableProvider) -> None:
    code = checkout_options()
    options = ManagedAgent('checkout_assistant', label='production').options(code)
    assert options is code


def test_a_rename_with_nothing_else_naming_the_tool_touches_nothing_else(project: LocalVariableProvider) -> None:
    options = managed(project, [RENAME], allowed_tools=[], agents=None)
    assert options.allowed_tools == []
    assert options.disallowed_tools == []
    assert options.agents is None
    assert options.hooks is None
    assert options.can_use_tool is None
    assert [tool['name'] for tool in wire_tools(options, 'shop')] == ['issue_refund', 'search']


def test_a_rename_reaches_every_subagents_own_tool_lists(project: LocalVariableProvider) -> None:
    agents = {
        'reviewer': AgentDefinition(
            description='Reviews refunds.',
            prompt='You review refunds.',
            tools=['mcp__shop__refund_order', 'Read'],
            disallowedTools=['mcp__shop__refund_order(A-*)'],
        )
    }
    options = managed(project, [RENAME], agents=agents)
    # A subagent's `tools` list is a permission rule like any other: left alone, the rename would
    # take a tool the subagent was explicitly allowed straight out of its reach.
    assert options.agents == snapshot(
        {
            'reviewer': AgentDefinition(
                description='Reviews refunds.',
                prompt='You review refunds.',
                tools=['mcp__shop__issue_refund', 'Read'],
                disallowedTools=['mcp__shop__issue_refund(A-*)'],
            )
        }
    )


def test_a_subagent_that_names_no_renamed_tool_is_the_object_the_caller_built(
    project: LocalVariableProvider,
) -> None:
    options = managed(project, [RENAME])
    assert options.agents == checkout_options().agents


def test_a_rename_reaches_the_tool_that_asks_for_permission(project: LocalVariableProvider) -> None:
    options = managed(project, [RENAME], permission_prompt_tool_name='mcp__shop__refund_order')
    assert options.permission_prompt_tool_name == 'mcp__shop__issue_refund'


def test_a_permission_tool_that_was_not_renamed_is_left_as_written(project: LocalVariableProvider) -> None:
    options = managed(project, [RENAME], permission_prompt_tool_name='mcp__approvals__ask')
    assert options.permission_prompt_tool_name == 'mcp__approvals__ask'


def test_two_servers_may_each_advertise_the_same_name(project: LocalVariableProvider) -> None:
    # The model calls an in-process tool `mcp__<server>__<tool>`, so a name is only taken inside its
    # own server: renaming the shop's `search` to `refund_order` does not collide with the CRM's.
    servers = {'shop': sdk_mcp_server('shop', tools=[search]), 'crm': sdk_mcp_server('crm', tools=[refund_order])}
    options = managed(
        project,
        [{'name': 'search', 'toolset': 'shop', 'new_name': 'refund_order'}],
        mcp_servers=servers,
        allowed_tools=['mcp__shop__search'],
    )
    assert [tool['name'] for tool in wire_tools(options, 'shop')] == ['refund_order']
    assert [tool['name'] for tool in wire_tools(options, 'crm')] == ['refund_order']
    assert options.allowed_tools == ['mcp__shop__refund_order']


def test_a_permission_callback_is_asked_about_the_tool_your_code_declared(project: LocalVariableProvider) -> None:
    asked: list[str] = []
    suggested: list[str] = []

    async def can_use_tool(name: str, _input: dict[str, Any], context: ToolPermissionContext) -> PermissionResult:
        asked.append(name)
        suggested.extend(rule.tool_name for update in context.suggestions for rule in update.rules or [])
        return PermissionResultAllow(
            updated_permissions=[
                PermissionUpdate(type='addRules', rules=[PermissionRuleValue(tool_name=name)], behavior='allow'),
                PermissionUpdate(type='setMode', mode='acceptEdits'),
            ]
        )

    options = managed(project, [RENAME], can_use_tool=can_use_tool)
    assert options.can_use_tool is not None
    suggestions = [
        PermissionUpdate(
            type='addRules', rules=[PermissionRuleValue(tool_name='mcp__shop__issue_refund')], behavior='allow'
        ),
        # An update that names no tool -- a mode change -- has nothing to translate either way.
        PermissionUpdate(type='setMode', mode='acceptEdits'),
    ]
    result = anyio.run(
        options.can_use_tool,
        'mcp__shop__issue_refund',
        {'order_id': 'A-1234'},
        ToolPermissionContext(suggestions=suggestions),
    )
    # The callback branches on the name your code gave the tool, in the argument and in the rules the
    # CLI suggested; what it asks for back is in the names the CLI knows.
    assert asked == ['mcp__shop__refund_order']
    assert suggested == ['mcp__shop__refund_order']
    assert isinstance(result, PermissionResultAllow)
    assert result.updated_permissions is not None
    assert [rule.tool_name for update in result.updated_permissions for rule in update.rules or []] == [
        'mcp__shop__issue_refund'
    ]


def test_a_permission_callback_asked_about_another_tool_sees_it_unchanged(project: LocalVariableProvider) -> None:
    async def can_use_tool(name: str, _input: dict[str, Any], _context: ToolPermissionContext) -> PermissionResult:
        return PermissionResultDeny(message=f'no {name}')

    options = managed(project, [RENAME], can_use_tool=can_use_tool)
    assert options.can_use_tool is not None
    no_input: dict[str, Any] = {}
    result = anyio.run(options.can_use_tool, 'Bash', no_input, ToolPermissionContext())
    assert result == PermissionResultDeny(message='no Bash')


def test_a_hook_is_told_the_tool_your_code_declared(project: LocalVariableProvider) -> None:
    seen: list[str] = []

    async def hook(payload: HookInput, _tool_use_id: str | None, _context: HookContext) -> HookJSONOutput:
        seen.append(cast(dict[str, Any], payload)['tool_name'])
        return {}

    options = managed(
        project, [RENAME], hooks={'PreToolUse': [HookMatcher(matcher='mcp__shop__refund_order', hooks=[hook])]}
    )
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['PreToolUse']
    payload: dict[str, Any] = {
        'hook_event_name': 'PreToolUse',
        'session_id': 's',
        'transcript_path': '/t',
        'cwd': '/c',
        'tool_name': 'mcp__shop__issue_refund',
        'tool_input': {'order_id': 'A-1234'},
        'tool_use_id': 'call-1',
    }
    assert anyio.run(matchers[0].hooks[0], cast(HookInput, payload), 'call-1', HookContext(signal=None)) == {}
    assert seen == ['mcp__shop__refund_order']


def test_a_hook_about_anything_else_is_handed_what_the_cli_sent(project: LocalVariableProvider) -> None:
    seen: list[dict[str, Any]] = []

    async def hook(payload: HookInput, _tool_use_id: str | None, _context: HookContext) -> HookJSONOutput:
        seen.append(cast(dict[str, Any], payload))
        return {}

    options = managed(project, [RENAME], hooks={'Stop': [HookMatcher(hooks=[hook])]})
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['Stop']
    payload: dict[str, Any] = {
        'hook_event_name': 'Stop',
        'session_id': 's',
        'transcript_path': '/t',
        'cwd': '/c',
        'stop_hook_active': False,
    }
    anyio.run(matchers[0].hooks[0], cast(HookInput, payload), None, HookContext(signal=None))
    assert seen == [payload]


def test_a_hook_matcher_a_rename_breaks_is_reported(project: LocalVariableProvider) -> None:
    async def hook(*args: Any) -> HookJSONOutput:
        return {}  # pragma: no cover

    hooks = {'PreToolUse': [HookMatcher(matcher='mcp__shop__refund.*', hooks=[hook])]}
    with pytest.warns(UserWarning, match='PreToolUse hook matcher'):
        options = managed(project, [RENAME], hooks=hooks)
    # Rewriting a regular expression would be editing one on a guess, so it is left as written.
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['PreToolUse']
    assert matchers[0].matcher == 'mcp__shop__refund.*'


@pytest.mark.parametrize('matcher', ['mcp__shop__.*', 'mcp__crm__refund.*', 'mcp__shop__[', None])
def test_a_hook_matcher_a_rename_does_not_break_is_left_alone(
    project: LocalVariableProvider, matcher: str | None
) -> None:
    async def hook(*args: Any) -> HookJSONOutput:
        return {}  # pragma: no cover

    # Still matching, never matching, and unparseable are all cases a rename did not change.
    options = managed(project, [RENAME], hooks={'PreToolUse': [HookMatcher(matcher=matcher, hooks=[hook])]})
    matchers = cast(dict[str, list[HookMatcher]], options.hooks)['PreToolUse']
    assert matchers[0].matcher == matcher
