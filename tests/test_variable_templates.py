"""Tests for variable template rendering (Handlebars {{placeholder}} support)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import builtins
import json
import os
import subprocess
import sys
import textwrap
from importlib.util import find_spec
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.variables import _handlebars
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

HAS_PYDANTIC_HANDLEBARS = find_spec('pydantic_handlebars') is not None
requires_handlebars = pytest.mark.skipif(
    not HAS_PYDANTIC_HANDLEBARS,
    reason='pydantic-handlebars requires Python 3.10+',
)


def _make_lf(variables_config: VariablesConfig, config_kwargs: dict[str, Any]) -> logfire.Logfire:
    """Create a Logfire instance with LocalVariablesOptions for testing."""
    config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
    return logfire.configure(**config_kwargs)


def _simple_config(name: str, serialized_value: str) -> VariablesConfig:
    """Create a minimal VariablesConfig with one variable and one label."""
    return VariablesConfig(
        variables={
            name: VariableConfig(
                name=name,
                labels={'production': LabeledValue(version=1, serialized_value=serialized_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
            ),
        },
    )


def test_import_logfire_without_pydantic_handlebars():
    """pydantic-handlebars is optional unless a Handlebars feature is used."""
    root = Path(__file__).parents[1]
    env = os.environ.copy()
    env['PYTHONPATH'] = f'{root}{os.pathsep}{env.get("PYTHONPATH", "")}'
    code = textwrap.dedent(
        """
        import builtins

        real_import = builtins.__import__

        def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'pydantic_handlebars' or name.startswith('pydantic_handlebars.'):
                raise ImportError('blocked pydantic_handlebars')
            return real_import(name, globals, locals, fromlist, level)

        builtins.__import__ = blocked_import

        import logfire
        from logfire.variables.abstract import render_serialized_string

        assert logfire.var
        assert logfire.var('plain_var', type=str, default='Hello')

        try:
            logfire.template_var('template_var', type=str, default='Hello {{name}}', inputs_type=dict)
        except ImportError as exc:
            assert 'pydantic-handlebars' in str(exc)
        else:
            raise AssertionError('template_var should require pydantic-handlebars')

        try:
            render_serialized_string('"Hello {{name}}"', {'name': 'Alice'})
        except ImportError as exc:
            assert 'pydantic-handlebars' in str(exc)
        else:
            raise AssertionError('rendering should require pydantic-handlebars')
        """
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@requires_handlebars
def test_handlebars_import_helpers_are_memoized(monkeypatch: pytest.MonkeyPatch):
    """Successful pydantic-handlebars imports are cached after the first lookup."""
    renderer = _handlebars.get_handlebars_renderer()
    schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}}
    _handlebars.check_template_compatibility(['Hello {{name}}'], schema)

    real_import = builtins.__import__

    def blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == 'pydantic_handlebars' or name.startswith('pydantic_handlebars.'):
            raise AssertionError('pydantic_handlebars should be cached')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', blocked_import)

    assert _handlebars.get_handlebars_renderer() == renderer
    _handlebars.check_template_compatibility(['Hello {{name}}'], schema)


# =============================================================================
# VariableConfig.template_inputs_schema tests
# =============================================================================


class TestVariableConfigTemplateInputs:
    """Test template_inputs_schema on VariableConfig."""

    def test_round_trip_serialization(self):
        """template_inputs_schema survives serialization/deserialization."""
        schema = {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name']}
        config = VariableConfig(
            name='test_var',
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
            template_inputs_schema=schema,
        )
        data = config.model_dump()
        restored = VariableConfig.model_validate(data)
        assert restored.template_inputs_schema == schema

    def test_none_by_default(self):
        """template_inputs_schema defaults to None."""
        config = VariableConfig(
            name='test_var',
            labels={},
            rollout=Rollout(labels={}),
            overrides=[],
        )
        assert config.template_inputs_schema is None


# =============================================================================
# TemplateVariable tests
# =============================================================================


@requires_handlebars
class TestTemplateVariable:
    """Test TemplateVariable[T, InputsT] — single-step get(inputs) rendering."""

    def test_basic_rendering(self, config_kwargs: dict[str, Any]):
        """get(inputs) returns rendered value directly."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=Inputs)
        resolved = var.get(Inputs(name='Alice'))
        assert resolved.value == 'Hello Alice!'

    def test_invalid_name_error(self, config_kwargs: dict[str, Any]):
        """template_var() applies the same Python identifier name validation as var()."""

        class Inputs(BaseModel):
            name: str

        lf = logfire.configure(**config_kwargs)
        with pytest.raises(ValueError, match='Invalid variable name'):
            lf.template_var('not-valid', type=str, default='x', inputs_type=Inputs)

    def test_remote_render_error_records_exception(self, config_kwargs: dict[str, Any]):
        """Invalid remote templates fall back, warn, and record the render exception."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('prompt', json.dumps('Hello {{#if name}}')), config_kwargs)
        var = lf.template_var('prompt', type=str, default='fallback', inputs_type=Inputs)

        with pytest.warns(RuntimeWarning, match='composition failed'):
            resolved = var.get(Inputs(name='Alice'))

        assert resolved.value == 'fallback'
        assert resolved.exception is not None
        assert resolved.reason == 'other_error'

    def test_composition_then_render(self, config_kwargs: dict[str, Any]):
        """@{refs}@ expanded first, then {{}} rendered with inputs."""

        class Inputs(BaseModel):
            user_name: str
            company: str

        variables_config = VariablesConfig(
            variables={
                'snippet': VariableConfig(
                    name='snippet',
                    labels={
                        'production': LabeledValue(version=1, serialized_value=json.dumps('Welcome to {{company}}!')),
                    },
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
                'full_prompt': VariableConfig(
                    name='full_prompt',
                    labels={
                        'production': LabeledValue(
                            version=1,
                            serialized_value=json.dumps('Hello {{user_name}}. @{snippet}@'),
                        ),
                    },
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        lf = _make_lf(variables_config, config_kwargs)
        var = lf.template_var('full_prompt', type=str, default='default', inputs_type=Inputs)
        resolved = var.get(Inputs(user_name='Alice', company='Acme Corp'))
        # Both composition AND rendering done in one step
        assert resolved.value == 'Hello Alice. Welcome to Acme Corp!'

    def test_structured_type(self, config_kwargs: dict[str, Any]):
        """Pydantic model with template fields renders correctly."""

        class PromptConfig(BaseModel):
            system_prompt: str
            temperature: float
            max_tokens: int

        class Inputs(BaseModel):
            user_name: str

        serialized = json.dumps(
            {
                'system_prompt': 'Hello {{user_name}}, how can I help?',
                'temperature': 0.7,
                'max_tokens': 100,
            }
        )

        lf = _make_lf(_simple_config('config', serialized), config_kwargs)
        var = lf.template_var(
            'config',
            type=PromptConfig,
            default=PromptConfig(system_prompt='default', temperature=0.5, max_tokens=50),
            inputs_type=Inputs,
        )
        resolved = var.get(Inputs(user_name='Alice'))
        assert isinstance(resolved.value, PromptConfig)
        assert resolved.value.system_prompt == 'Hello Alice, how can I help?'
        assert resolved.value.temperature == 0.7
        assert resolved.value.max_tokens == 100

    def test_default_rendering(self, config_kwargs: dict[str, Any]):
        """Code default with {{}} templates is rendered."""

        class Inputs(BaseModel):
            name: str

        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.template_var('prompt', type=str, default='Hello {{name}}!', inputs_type=Inputs)
        resolved = var.get(Inputs(name='Alice'))
        # The default value should be rendered with the inputs
        assert resolved.value == 'Hello Alice!'

    def test_override_renders_template(self, config_kwargs: dict[str, Any]):
        """override() overrides the template, which still gets rendered with inputs."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=Inputs)
        with var.override('Overridden {{name}}!'):
            resolved = var.get(Inputs(name='Alice'))
            # Override value is treated as a template and rendered
            assert resolved.value == 'Overridden Alice!'

    def test_override_literal_string(self, config_kwargs: dict[str, Any]):
        """override() with a literal string (no placeholders) works as a plain override."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=Inputs)
        with var.override('exact override value'):
            resolved = var.get(Inputs(name='Alice'))
            # No placeholders, so rendering is a no-op — value returned as-is
            assert resolved.value == 'exact override value'

    def test_pydantic_model_inputs(self, config_kwargs: dict[str, Any]):
        """InputsT as Pydantic BaseModel works correctly."""

        class MyInputs(BaseModel):
            user_name: str
            is_premium: bool = False

        lf = _make_lf(
            _simple_config('prompt', json.dumps('Welcome {{user_name}}!{{#if is_premium}} VIP{{/if}}')),
            config_kwargs,
        )
        var = lf.template_var('prompt', type=str, default='default', inputs_type=MyInputs)

        resolved = var.get(MyInputs(user_name='Alice', is_premium=True))
        assert resolved.value == 'Welcome Alice! VIP'

        resolved2 = var.get(MyInputs(user_name='Bob'))
        assert resolved2.value == 'Welcome Bob!'

    def test_registration(self, config_kwargs: dict[str, Any]):
        """template_var() registers in _variables."""

        class Inputs(BaseModel):
            x: str

        lf = logfire.configure(**config_kwargs)
        lf.template_var('tv1', type=str, default='x', inputs_type=Inputs)
        assert 'tv1' in {v.name for v in lf.variables_get()}

    def test_duplicate_name_error(self, config_kwargs: dict[str, Any]):
        """Same name as existing var raises ValueError."""

        class Inputs(BaseModel):
            x: str

        lf = logfire.configure(**config_kwargs)
        lf.var('myvar', type=str, default='x')
        with pytest.raises(ValueError, match="A variable with name 'myvar' has already been registered"):
            lf.template_var('myvar', type=str, default='x', inputs_type=Inputs)

    def test_context_manager(self, config_kwargs: dict[str, Any]):
        """with template_var.get(inputs) as resolved: sets baggage."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('prompt', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('prompt', type=str, default='default', inputs_type=Inputs)
        with var.get(Inputs(name='Alice')) as resolved:
            assert resolved.value == 'Hello Alice!'
            baggage = logfire.get_baggage()
            assert baggage.get('logfire.variables.prompt') == 'production'

    def test_no_templates_passthrough(self, config_kwargs: dict[str, Any]):
        """Value with no {{}} returns as-is after rendering."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hello world!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=Inputs)
        resolved = var.get(Inputs(name='unused'))
        assert resolved.value == 'Hello world!'

    def test_template_inputs_schema_in_config(self, config_kwargs: dict[str, Any]):
        """template_var() generates JSON Schema in the variable config."""

        class MyInputs(BaseModel):
            user_name: str
            count: int = 5

        lf = logfire.configure(**config_kwargs)
        var = lf.template_var('prompt', type=str, default='Hello {{user_name}}', inputs_type=MyInputs)
        config = var.to_config()
        assert config.template_inputs_schema is not None
        assert config.template_inputs_schema['type'] == 'object'
        assert 'user_name' in config.template_inputs_schema['properties']
        assert 'count' in config.template_inputs_schema['properties']
