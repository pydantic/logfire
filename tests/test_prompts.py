"""Tests for managed prompts (`logfire.prompt` / `logfire.template_prompt`)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
import requests_mock as requests_mock_module
from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions, VariablesOptions
from logfire.variables import PROMPT_VARIABLE_PREFIX, prompt_variable_name
from logfire.variables._prompt import prompt_slug_from_variable_name
from logfire.variables.abstract import (
    ResolvedVariable,
    VariableAlreadyExistsError,
    VariableProvider,
    VariableWriteError,
)
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    VariableConfig,
    VariablesConfig,
)
from logfire.variables.local import LocalVariableProvider
from logfire.variables.remote import LogfireRemoteVariableProvider


def _make_remote_provider() -> LogfireRemoteVariableProvider:
    return LogfireRemoteVariableProvider(
        base_url='http://localhost:8000/',
        token='pylf_v1_local_test_token',
        options=VariablesOptions(block_before_first_resolve=False),
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
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            prompt_variable_name('has space')

    def test_uppercase_rejected(self):
        # Backend slugs are always lowercase, so an uppercased slug would silently resolve to a
        # different variable and fall back to the code default. Reject it loudly instead.
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            prompt_variable_name('SupportAgent')

    def test_underscore_rejected(self):
        # The slug uses hyphens; underscores belong only to the derived backing-variable name.
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            prompt_variable_name('support_agent')

    def test_empty_rejected(self):
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            prompt_variable_name('')


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
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            logfire.prompt('has space', default='x')

    def test_uppercase_slug_raises(self):
        with pytest.raises(ValueError, match='Invalid prompt slug'):
            logfire.prompt('SupportAgent', default='x')


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


class TestPushPrompts:
    """`variables_push()` handles prompts too, routing them through the prompts surface.

    A single push entry point covers everything declared in code — general variables go
    through the variables API, prompt-backed variables (which the variables API rejects
    writes to) are created via the prompts API.
    """

    def test_push_creates_missing_prompt_and_variable(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        prompt = lf.prompt('support-agent', default='You are helpful.', description='Support system prompt')
        var = lf.var(name='plain_var', default='default', type=str)

        result = provider.push_variables([prompt, var], yes=True)
        assert result is True

        captured = capsys.readouterr()
        assert '+ support-agent (publishes version 1 from the code default)' in captured.out
        assert 'Created prompt: support-agent' in captured.out
        assert 'plain_var' in provider._config.variables

        created = provider._config.variables['prompt__support_agent']
        assert created.json_schema is None
        assert created.description == 'Support system prompt'
        assert created.latest_version is not None
        assert created.latest_version.serialized_value == json.dumps('You are helpful.')
        # A fresh prompt serves its latest version, matching platform defaults.
        assert created.rollout.labels == {'latest': 1.0}

    def test_pushed_prompt_resolves_from_provider(self, config_kwargs: dict[str, Any]):
        """After a push, `prompt().get()` serves the pushed version, not the code default."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        prompt = lf.prompt('greeting', default='Hello from code.')
        provider.push_variables([prompt], yes=True)

        resolved = provider.get_serialized_value('prompt__greeting')
        assert resolved.value == json.dumps('Hello from code.')
        assert resolved.reason == 'resolved'

    def test_push_existing_prompt_untouched(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        provider.create_prompt(slug='support-agent', name='Support agent', template='Server version.')

        lf = logfire.configure(**config_kwargs)
        prompt = lf.prompt('support-agent', default='Different code default.')

        result = provider.push_variables([prompt], yes=True)
        assert result is False

        captured = capsys.readouterr()
        assert 'prompt(s) already exist and are left untouched (support-agent)' in captured.out
        assert 'No changes needed' in captured.out
        existing = provider._config.variables['prompt__support_agent']
        assert existing.latest_version is not None
        assert existing.latest_version.serialized_value == json.dumps('Server version.')

    def test_push_template_prompt_includes_inputs_schema(self, config_kwargs: dict[str, Any]):
        class Inputs(BaseModel):
            customer_name: str

        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        prompt = lf.template_prompt('welcome', default='Hi {{customer_name}}!', inputs_type=Inputs)

        result = provider.push_variables([prompt], yes=True)
        assert result is True

        created = provider._config.variables['prompt__welcome']
        assert created.template_inputs_schema is not None
        assert created.template_inputs_schema['properties'] == {
            'customer_name': {'title': 'Customer Name', 'type': 'string'}
        }

    def test_push_prompt_function_default_creates_without_version(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        def resolve_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'computed'  # pragma: no cover

        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        prompt = lf.prompt('dynamic', default=resolve_fn)

        result = provider.push_variables([prompt], yes=True)
        assert result is True

        captured = capsys.readouterr()
        assert '+ dynamic (no initial version — the code default is a function)' in captured.out
        created = provider._config.variables['prompt__dynamic']
        assert created.latest_version is None
        assert created.rollout.labels == {}

    def test_push_prompts_dry_run(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        prompt = lf.prompt('support-agent', default='You are helpful.')

        result = provider.push_variables([prompt], dry_run=True)
        assert result is True

        captured = capsys.readouterr()
        assert '+ support-agent' in captured.out
        assert 'Dry run mode' in captured.out
        assert provider._config.variables == {}


class TestCreatePromptPrimitive:
    def test_slug_from_variable_name_rejects_non_prompt_name(self):
        with pytest.raises(ValueError, match='is not a prompt-backed variable name'):
            prompt_slug_from_variable_name('plain_var')

    def test_base_create_prompt_warns(self):
        """The base provider's create_prompt is a warn-only default, like create_variable."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        with pytest.warns(UserWarning, match='does not persist prompt writes'):
            provider.create_prompt(slug='support-agent', name='Support agent')

    def test_local_create_prompt_duplicate_raises(self):
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        provider.create_prompt(slug='support-agent', name='Support agent', template='v1')
        with pytest.raises(VariableAlreadyExistsError, match="Prompt 'support-agent' already exists"):
            provider.create_prompt(slug='support-agent', name='Support agent', template='v2')

    def test_remote_create_prompt_full(self):
        """Remote create_prompt POSTs the prompt, publishes v1, and PUTs the inputs schema."""
        request_mocker = requests_mock_module.Mocker()
        create = request_mocker.post('http://localhost:8000/v1/prompts/', json={'slug': 'welcome'}, status_code=201)
        version = request_mocker.post(
            'http://localhost:8000/v1/prompts/welcome/versions/', json={'version': 1}, status_code=201
        )
        schema_put = request_mocker.put('http://localhost:8000/v1/variables/prompt__welcome/', json={})
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        with request_mocker:
            provider = _make_remote_provider()
            try:
                provider.create_prompt(
                    slug='welcome',
                    name='Welcome',
                    description='Welcome email prompt',
                    template='Hi {{name}}!',
                    template_inputs_schema={'type': 'object', 'properties': {'name': {'type': 'string'}}},
                )
            finally:
                provider.shutdown()
        assert create.last_request is not None
        assert create.last_request.json() == {
            'name': 'Welcome',
            'slug': 'welcome',
            'description': 'Welcome email prompt',
        }
        assert version.last_request is not None
        assert version.last_request.json() == {'template': 'Hi {{name}}!'}
        assert schema_put.last_request is not None
        assert schema_put.last_request.json() == {
            'template_inputs_schema': {'type': 'object', 'properties': {'name': {'type': 'string'}}}
        }

    def test_remote_create_prompt_minimal(self):
        """No description/template/inputs schema — only the create POST fires."""
        request_mocker = requests_mock_module.Mocker()
        create = request_mocker.post('http://localhost:8000/v1/prompts/', json={'slug': 'bare'}, status_code=201)
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        with request_mocker:
            provider = _make_remote_provider()
            try:
                provider.create_prompt(slug='bare', name='Bare')
            finally:
                provider.shutdown()
        assert create.last_request is not None
        assert create.last_request.json() == {'name': 'Bare', 'slug': 'bare'}

    def test_remote_create_prompt_conflict(self):
        request_mocker = requests_mock_module.Mocker()
        request_mocker.post('http://localhost:8000/v1/prompts/', status_code=409)
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        with request_mocker:
            provider = _make_remote_provider()
            try:
                with pytest.raises(VariableAlreadyExistsError, match="Prompt 'dup' already exists"):
                    provider.create_prompt(slug='dup', name='Dup')
            finally:
                provider.shutdown()

    def test_remote_create_prompt_http_error(self):
        request_mocker = requests_mock_module.Mocker()
        request_mocker.post('http://localhost:8000/v1/prompts/', status_code=500, text='boom')
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        with request_mocker:
            provider = _make_remote_provider()
            try:
                with pytest.raises(VariableWriteError, match='Failed to create prompt'):
                    provider.create_prompt(slug='broken', name='Broken')
            finally:
                provider.shutdown()
