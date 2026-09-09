"""What the adapter tells Logfire the agent does today."""

from __future__ import annotations

import json

import pytest
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, create_sdk_mcp_server
from inline_snapshot import snapshot

from logfire.agent_control.claude_agent_sdk import ManagedAgent, sdk_mcp_server
from logfire.agent_control.claude_agent_sdk._control import baseline
from logfire.variables.local import LocalVariableProvider

from .agents import checkout_options, refund_order


def test_the_baseline_describes_every_seam_the_agent_has() -> None:
    assert baseline(checkout_options()).model_dump(exclude_none=True) == snapshot(
        {
            'instructions': [
                {'id': 'system', 'instructions': 'You are a concise checkout assistant.', 'dynamic': False},
                {'id': 'agent:reviewer', 'instructions': 'You review refunds.', 'dynamic': False},
            ],
            'model': 'anthropic:claude-fable-5-1',
            'settings': {'thinking': 'high'},
            'tool_definitions': [
                {
                    'name': 'refund_order',
                    'description': 'Refund an order.',
                    'parameters': {'order_id': {'description': 'The order to refund.'}},
                    'toolset': 'shop',
                },
                {
                    'name': 'search',
                    'description': 'Search the catalogue.',
                    'parameters': {'query': {}},
                    'toolset': 'shop',
                },
            ],
        }
    )


def test_a_preset_prompt_is_listed_without_its_text() -> None:
    options = ClaudeAgentOptions(
        system_prompt={'type': 'preset', 'preset': 'claude_code', 'append': 'Be terse.'},
        agents={'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.')},
    )
    assert baseline(options).model_dump(exclude_none=True) == snapshot(
        {
            'instructions': [
                {'id': 'preset:claude_code', 'dynamic': True},
                {'id': 'append', 'instructions': 'Be terse.', 'dynamic': False},
                {'id': 'agent:reviewer', 'instructions': 'You review refunds.', 'dynamic': False},
            ]
        }
    )


def test_a_file_prompt_is_listed_without_its_text() -> None:
    options = ClaudeAgentOptions(system_prompt={'type': 'file', 'path': '/prompts/checkout.md'})
    assert baseline(options).model_dump(exclude_none=True) == snapshot(
        {'instructions': [{'id': 'system:file', 'dynamic': True}]}
    )


def test_an_agent_with_nothing_stated_describes_nothing() -> None:
    assert baseline(ClaudeAgentOptions()).model_dump(exclude_none=True) == snapshot({})


def test_tools_of_a_server_built_the_sdks_own_way_are_not_listed() -> None:
    # `create_sdk_mcp_server` keeps no reference to the definitions it was given, so there is nothing
    # to describe and nothing a published override could rewrite.
    options = ClaudeAgentOptions(mcp_servers={'shop': create_sdk_mcp_server('shop', tools=[refund_order])})
    assert baseline(options).tool_definitions is None


def test_external_and_file_backed_mcp_servers_are_not_listed() -> None:
    external = baseline(ClaudeAgentOptions(mcp_servers={'crm': {'type': 'http', 'url': 'https://crm.example'}}))
    assert external.tool_definitions is None
    assert baseline(ClaudeAgentOptions(mcp_servers='/etc/mcp.json')).tool_definitions is None


def test_the_baseline_is_what_the_variable_is_created_with(project: LocalVariableProvider) -> None:
    options = checkout_options()
    managed = ManagedAgent('checkout_assistant')
    with managed.session(options) as applied:
        assert applied is options  # Nothing published: the agent runs exactly as written.
    assert managed._publish_thread is not None  # pyright: ignore[reportPrivateUsage]
    managed._publish_thread.join()  # pyright: ignore[reportPrivateUsage]

    config = project.get_variable_config('agent__checkout_assistant')
    assert config is not None
    assert config.example == json.dumps(baseline(options).model_dump(exclude_none=True), indent=2)


def test_environment_settings_the_cli_reads_are_described() -> None:
    options = ClaudeAgentOptions(
        env={'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '4096', 'API_TIMEOUT_MS': '30000', 'ANTHROPIC_BASE_URL': 'x'},
        thinking={'type': 'disabled'},
    )
    assert baseline(options).model_dump(exclude_none=True) == snapshot(
        {'settings': {'max_tokens': 4096, 'timeout': 30.0, 'thinking': False}}
    )


def test_an_unreadable_environment_setting_is_simply_not_described() -> None:
    options = ClaudeAgentOptions(env={'CLAUDE_CODE_MAX_OUTPUT_TOKENS': 'lots'})
    assert baseline(options).settings is None


def test_a_thinking_budget_is_described_as_the_part_the_contract_can_say() -> None:
    options = ClaudeAgentOptions(thinking={'type': 'enabled', 'budget_tokens': 8000})
    settings = baseline(options).settings
    assert settings is not None and settings.thinking is True


def test_an_effort_level_the_contract_cannot_name_is_left_out_rather_than_approximated() -> None:
    # `'max'` is not `'xhigh'`, and the baseline is the one artifact the Logfire editor presents as
    # the truth about the code, so the level is omitted and reported rather than rounded to a name.
    with pytest.warns(UserWarning, match="thinking='max', which the Agent Control contract cannot describe"):
        assert baseline(ClaudeAgentOptions(effort='max')).settings is None


def test_a_server_built_by_this_adapter_after_a_rebuild_is_still_described() -> None:
    # `sdk_mcp_server` is what the adapter rebuilds patched servers with, so its registration has to
    # survive being called on tools it produced itself.
    rebuilt = sdk_mcp_server('shop', '2.0.0', [refund_order])
    definitions = baseline(ClaudeAgentOptions(mcp_servers={'shop': rebuilt})).tool_definitions
    assert definitions is not None and [tool.name for tool in definitions] == ['refund_order']
