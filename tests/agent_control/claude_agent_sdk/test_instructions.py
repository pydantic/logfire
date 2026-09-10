"""What a published `instructions` section does to the prompts a session starts with."""

from __future__ import annotations

from dataclasses import replace

import pytest
from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions

from logfire.agent_control.claude_agent_sdk import agent_control
from logfire.variables.local import LocalVariableProvider

from .agents import checkout_options
from .conftest import cli_arg, publish


def managed(project: LocalVariableProvider, instructions: object, **overrides: object) -> ClaudeAgentOptions:
    publish(project, 'agent__checkout_assistant', {'instructions': instructions})
    return agent_control(checkout_options(**overrides), name='checkout_assistant', label='production')


def test_the_agents_own_prompt_is_rewritten(project: LocalVariableProvider) -> None:
    options = managed(project, [{'id': 'system', 'instructions': 'You are a refund specialist.'}])
    assert options.system_prompt == 'You are a refund specialist.'
    assert cli_arg(options, '--system-prompt') == 'You are a refund specialist.'


def test_dropping_the_prompt_leaves_the_clis_own(project: LocalVariableProvider) -> None:
    options = managed(project, [{'id': 'system'}])
    # `''` is exactly what the SDK sends for `system_prompt=None`: no custom prompt at all.
    assert options.system_prompt == ''
    assert cli_arg(options, '--system-prompt') == ''


def test_an_added_block_lands_after_the_agents_own_prompt(project: LocalVariableProvider) -> None:
    options = managed(project, ['Escalate anything over $500 to a human.'])
    assert cli_arg(options, '--system-prompt') == (
        'You are a concise checkout assistant.\n\nEscalate anything over $500 to a human.'
    )


def test_an_added_block_becomes_the_prompt_when_there_is_none(project: LocalVariableProvider) -> None:
    options = managed(project, 'Escalate anything over $500 to a human.', system_prompt=None)
    assert cli_arg(options, '--system-prompt') == 'Escalate anything over $500 to a human.'


def test_a_presets_append_is_rewritten_and_added_to(project: LocalVariableProvider) -> None:
    preset = {'type': 'preset', 'preset': 'claude_code', 'append': 'Be terse.', 'exclude_dynamic_sections': True}
    options = managed(
        project,
        [{'id': 'append', 'instructions': 'Be very terse.'}, 'Escalate anything over $500 to a human.'],
        system_prompt=preset,
    )
    assert options.system_prompt == {
        'type': 'preset',
        'preset': 'claude_code',
        'exclude_dynamic_sections': True,
        'append': 'Be very terse.\n\nEscalate anything over $500 to a human.',
    }
    assert cli_arg(options, '--append-system-prompt') == ('Be very terse.\n\nEscalate anything over $500 to a human.')


def test_dropping_the_append_sends_the_preset_alone(project: LocalVariableProvider) -> None:
    preset = {'type': 'preset', 'preset': 'claude_code', 'append': 'Be terse.'}
    options = managed(project, [{'id': 'append'}], system_prompt=preset)
    assert options.system_prompt == {'type': 'preset', 'preset': 'claude_code'}
    assert cli_arg(options, '--append-system-prompt') is None


def test_a_preset_without_an_append_can_be_given_one(project: LocalVariableProvider) -> None:
    preset = {'type': 'preset', 'preset': 'claude_code'}
    options = managed(project, 'Escalate anything over $500 to a human.', system_prompt=preset)
    assert cli_arg(options, '--append-system-prompt') == 'Escalate anything over $500 to a human.'


def test_claude_codes_own_prompt_cannot_be_addressed(project: LocalVariableProvider) -> None:
    preset = {'type': 'preset', 'preset': 'claude_code', 'append': 'Be terse.'}
    with pytest.warns(UserWarning, match="addresses instruction block 'preset:claude_code', which the agent"):
        options = managed(project, [{'id': 'preset:claude_code', 'instructions': 'Nice try.'}], system_prompt=preset)
    assert options.system_prompt == preset


def test_a_prompt_read_from_a_file_cannot_be_addressed(project: LocalVariableProvider) -> None:
    file = {'type': 'file', 'path': '/prompts/checkout.md'}
    with pytest.warns(UserWarning, match="addresses instruction block 'system:file', which the agent recomputes"):
        options = managed(project, [{'id': 'system:file', 'instructions': 'Nice try.'}], system_prompt=file)
    assert options.system_prompt == file


def test_a_prompt_read_from_a_file_has_nowhere_to_add_to(project: LocalVariableProvider) -> None:
    file = {'type': 'file', 'path': '/prompts/checkout.md'}
    with pytest.warns(UserWarning, match="reads its system prompt from the file '/prompts/checkout.md'"):
        options = managed(project, 'Escalate anything over $500 to a human.', system_prompt=file)
    assert options.system_prompt == file


def test_a_subagents_prompt_is_rewritten(project: LocalVariableProvider) -> None:
    options = managed(project, [{'id': 'agent:reviewer', 'instructions': 'You review refunds carefully.'}])
    assert options.agents == {
        'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds carefully.')
    }


def test_a_subagents_prompt_cannot_be_removed(project: LocalVariableProvider) -> None:
    # Removing a block removes text. A subagent is not text: the CLI declares one *by* its prompt and
    # leaves a subagent whose prompt is empty out of the session, so applying the removal would take
    # away the subagent, its description, and its tools -- see `test_live.py`, which pins both halves.
    with pytest.warns(UserWarning, match="removes instruction block 'agent:reviewer', but the `claude` CLI drops"):
        options = managed(project, [{'id': 'agent:reviewer'}])
    assert options.agents == {'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.')}


def test_a_subagent_the_agent_does_not_have_is_reported(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="addresses instruction block 'agent:auditor', which this request"):
        options = managed(project, [{'id': 'agent:auditor', 'instructions': 'You audit.'}])
    assert options.agents == {'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.')}


def test_one_subagent_of_several_is_rewritten_alone(project: LocalVariableProvider) -> None:
    agents = {
        'reviewer': AgentDefinition(description='Reviews refunds.', prompt='You review refunds.'),
        'auditor': AgentDefinition(description='Audits refunds.', prompt='You audit refunds.'),
    }
    options = managed(project, [{'id': 'agent:reviewer', 'instructions': 'You review refunds twice.'}], agents=agents)
    assert options.agents == {
        'reviewer': replace(agents['reviewer'], prompt='You review refunds twice.'),
        'auditor': agents['auditor'],
    }


def test_an_agent_with_no_prompt_of_its_own_is_left_that_way(project: LocalVariableProvider) -> None:
    publish(project, 'agent__checkout_assistant', {'model': 'anthropic:claude-opus-4-5'})
    options = agent_control(ClaudeAgentOptions(), name='checkout_assistant', label='production')
    assert options.system_prompt is None
    assert options.agents is None
    assert cli_arg(options, '--system-prompt') == ''
