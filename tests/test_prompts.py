"""Tests for managed prompts (`logfire.prompt` / `logfire.template_prompt`)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.variables import PROMPT_VARIABLE_PREFIX, prompt_variable_name
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    VariableConfig,
    VariablesConfig,
)


def _make_lf(variables_config: VariablesConfig, config_kwargs: dict[str, Any]) -> logfire.Logfire:
    config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
    return logfire.configure(**config_kwargs)


def _prompt_config(variable_name: str, serialized_value: str) -> VariablesConfig:
    """A minimal config for one prompt-backed variable with a `production` label."""
    return VariablesConfig(
        variables={
            variable_name: VariableConfig(
                name=variable_name,
                labels={'production': LabeledValue(version=1, serialized_value=serialized_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
        },
    )


class TestPromptVariableName:
    def test_prefix_constant(self):
        assert PROMPT_VARIABLE_PREFIX == 'prompt__'

    def test_prepends_prefix(self):
        assert prompt_variable_name('support') == 'prompt__support'

    def test_normalizes_hyphens(self):
        assert prompt_variable_name('support-agent') == 'prompt__support_agent'

    def test_warns_and_strips_accidental_prefix(self):
        with pytest.warns(UserWarning, match='added automatically'):
            assert prompt_variable_name('prompt__support-agent') == 'prompt__support_agent'

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError, match='invalid variable name'):
            prompt_variable_name('has space')


class TestPrompt:
    def test_declares_backing_variable(self):
        support = logfire.prompt('support-agent', default='Be helpful.')
        assert support.name == 'prompt__support_agent'
        # The declared variable is the same object as the registered one.
        assert logfire.variables_get() == [support]

    def test_resolves_code_default(self):
        p = logfire.prompt('greeting', default='Hello there.')
        resolved = p.get()
        assert resolved.value == 'Hello there.'
        assert resolved.reason == 'code_default'

    def test_resolves_remote_value(self, config_kwargs: dict[str, Any]):
        lf = _make_lf(_prompt_config('prompt__support_agent', json.dumps('Remote prompt text.')), config_kwargs)
        p = lf.prompt('support-agent', default='Code default.')
        resolved = p.get(label='production')
        assert resolved.value == 'Remote prompt text.'
        assert resolved.label == 'production'
        assert resolved.version == 1

    def test_resolve_function_default(self):
        def make_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'Computed default.'

        p = logfire.prompt('dynamic', default=make_default)
        assert p.get().value == 'Computed default.'

    def test_duplicate_name_raises(self):
        logfire.prompt('dup', default='a')
        with pytest.raises(ValueError, match='already been registered'):
            logfire.prompt('dup', default='b')

    def test_accidental_prefix_warns(self):
        with pytest.warns(UserWarning, match='added automatically'):
            p = logfire.prompt('prompt__warned', default='x')
        assert p.name == 'prompt__warned'

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError, match='invalid variable name'):
            logfire.prompt('has space', default='x')


class TestTemplatePrompt:
    def test_renders_template_default(self):
        class Inputs(BaseModel):
            customer_name: str

        p = logfire.template_prompt('support-agent', default='Helping {{customer_name}}.', inputs_type=Inputs)
        assert p.name == 'prompt__support_agent'
        resolved = p.get(Inputs(customer_name='Alice'))
        assert resolved.value == 'Helping Alice.'

    def test_renders_remote_template(self, config_kwargs: dict[str, Any]):
        class Inputs(BaseModel):
            customer_name: str

        lf = _make_lf(_prompt_config('prompt__support_agent', json.dumps('Hi {{customer_name}}!')), config_kwargs)
        p = lf.template_prompt('support-agent', default='default', inputs_type=Inputs)
        resolved = p.get(Inputs(customer_name='Alice'), label='production')
        assert resolved.value == 'Hi Alice!'
        assert resolved.label == 'production'

    def test_normalizes_name(self):
        class Inputs(BaseModel):
            name: str

        p = logfire.template_prompt('my-prompt', default='Hi {{name}}', inputs_type=Inputs)
        assert p.name == 'prompt__my_prompt'

    def test_accidental_prefix_warns(self):
        class Inputs(BaseModel):
            name: str

        with pytest.warns(UserWarning, match='added automatically'):
            p = logfire.template_prompt('prompt__warned', default='Hi {{name}}', inputs_type=Inputs)
        assert p.name == 'prompt__warned'
