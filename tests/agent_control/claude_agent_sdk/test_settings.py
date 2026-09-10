"""What a published `model` and `settings` section do to the process the SDK spawns."""

from __future__ import annotations

from typing import Any

import pytest
from claude_agent_sdk import ClaudeAgentOptions

from logfire.agent_control.claude_agent_sdk import agent_control
from logfire.variables.local import LocalVariableProvider

from .agents import checkout_options
from .conftest import cli_arg, cli_args, publish


def managed(project: LocalVariableProvider, value: dict[str, Any], **options: Any) -> ClaudeAgentOptions:
    publish(project, 'agent__checkout_assistant', value)
    return agent_control(checkout_options(**options), name='checkout_assistant', label='production')


def test_an_anthropic_model_is_lowered_to_the_bare_id(project: LocalVariableProvider) -> None:
    options = managed(project, {'model': 'anthropic:claude-opus-4-5'})
    assert options.model == 'claude-opus-4-5'
    assert cli_arg(options, '--model') == 'claude-opus-4-5'


def test_an_alias_is_a_model_like_any_other(project: LocalVariableProvider) -> None:
    assert managed(project, {'model': 'anthropic:sonnet'}).model == 'sonnet'


def test_a_provider_with_no_model_after_it_is_refused(project: LocalVariableProvider) -> None:
    # A prefix and nothing after it would start the session with no model at all, rather than with
    # the one the code names.
    with pytest.warns(UserWarning, match="selects model 'anthropic:', which names a provider and no model"):
        options = managed(project, {'model': 'anthropic:'})
    assert options.model == 'claude-fable-5-1'


def test_a_model_with_no_provider_is_passed_through(project: LocalVariableProvider) -> None:
    assert managed(project, {'model': 'claude-fable-5-1-20260901'}).model == 'claude-fable-5-1-20260901'


def test_another_providers_model_is_refused(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="selects model 'bedrock:claude-fable-5-1', but the Claude Agent SDK"):
        options = managed(project, {'model': 'bedrock:claude-fable-5-1'})
    assert options.model == 'claude-fable-5-1'  # The code's own model, untouched.


@pytest.mark.parametrize(
    ('thinking', 'expected_thinking', 'expected_effort'),
    [
        (False, 'disabled', None),
        (True, 'adaptive', None),
        ('minimal', 'adaptive', 'low'),
        ('low', 'adaptive', 'low'),
        ('xhigh', 'adaptive', 'xhigh'),
    ],
)
def test_thinking_sets_both_halves_of_what_the_cli_is_told(
    project: LocalVariableProvider, thinking: bool | str, expected_thinking: str, expected_effort: str | None
) -> None:
    options = managed(project, {'settings': {'thinking': thinking}})
    assert cli_arg(options, '--thinking') == expected_thinking
    assert cli_arg(options, '--effort') == expected_effort


def test_output_and_timeout_settings_reach_the_cli_environment(project: LocalVariableProvider) -> None:
    options = managed(project, {'settings': {'max_tokens': 4096, 'timeout': 12.5}}, env={'ANTHROPIC_LOG': 'debug'})
    assert options.env == {
        'ANTHROPIC_LOG': 'debug',
        'CLAUDE_CODE_MAX_OUTPUT_TOKENS': '4096',
        'API_TIMEOUT_MS': '12500',
    }


def test_the_callers_environment_is_never_mutated(project: LocalVariableProvider) -> None:
    env = {'ANTHROPIC_LOG': 'debug'}
    managed(project, {'settings': {'max_tokens': 4096}}, env=env)
    assert env == {'ANTHROPIC_LOG': 'debug'}


def test_settings_this_framework_has_no_knob_for_are_reported(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="sets 'temperature', which this agent framework has no equivalent"):
        options = managed(project, {'settings': {'temperature': 0.4, 'thinking': 'low'}})
    # The one it can apply still applies.
    assert cli_arg(options, '--effort') == 'low'
    assert '--temperature' not in cli_args(options)


def test_a_settings_section_that_changes_nothing_leaves_the_environment_alone(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="sets 'seed', which this agent framework has no equivalent"):
        options = managed(project, {'settings': {'seed': 7}}, env={'ANTHROPIC_LOG': 'debug'})
    assert options.env == {'ANTHROPIC_LOG': 'debug'}
    assert cli_arg(options, '--effort') == 'high'  # Still the code's own effort.


def test_settings_the_contract_itself_does_not_know_are_reported(project: LocalVariableProvider) -> None:
    with pytest.warns(UserWarning, match="sets 'service_tier', which this version of the Agent Control"):
        managed(project, {'settings': {'service_tier': 'flex'}})
