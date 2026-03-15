"""Tests for variable template rendering (Handlebars {{placeholder}} support)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.variables.config import (
    LabeledValue,
    Rollout,
    VariableConfig,
    VariablesConfig,
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


# =============================================================================
# ResolvedVariable.render() tests
# =============================================================================


class TestRenderSimpleString:
    """Test rendering string variables with Handlebars templates."""

    def test_simple_placeholder(self, config_kwargs: dict[str, Any]):
        """Simple {{placeholder}} replacement in a string variable."""
        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.var('greeting', type=str, default='default')
        resolved = var.get()
        assert resolved.value == 'Hello {{name}}!'
        rendered = resolved.render({'name': 'Alice'})
        assert rendered == 'Hello Alice!'

    def test_multiple_placeholders(self, config_kwargs: dict[str, Any]):
        """Multiple {{placeholders}} in a single string."""
        lf = _make_lf(
            _simple_config('prompt', json.dumps('Hello {{user_name}}, welcome to {{company}}!')),
            config_kwargs,
        )
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        rendered = resolved.render({'user_name': 'Bob', 'company': 'Acme'})
        assert rendered == 'Hello Bob, welcome to Acme!'

    def test_conditional_template(self, config_kwargs: dict[str, Any]):
        """Handlebars #if conditional in a string variable."""
        lf = _make_lf(
            _simple_config('prompt', json.dumps('Hello {{name}}.{{#if is_premium}} Premium member!{{/if}}')),
            config_kwargs,
        )
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()

        rendered_premium = resolved.render({'name': 'Alice', 'is_premium': True})
        assert rendered_premium == 'Hello Alice. Premium member!'

        rendered_basic = resolved.render({'name': 'Bob', 'is_premium': False})
        assert rendered_basic == 'Hello Bob.'

    def test_each_helper(self, config_kwargs: dict[str, Any]):
        """Handlebars #each iteration in a string variable."""
        lf = _make_lf(
            _simple_config(
                'prompt',
                json.dumps('Items: {{#each items}}{{this}}{{#unless @last}}, {{/unless}}{{/each}}'),
            ),
            config_kwargs,
        )
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        rendered = resolved.render({'items': ['apple', 'banana', 'cherry']})
        assert rendered == 'Items: apple, banana, cherry'

    def test_no_html_escaping(self, config_kwargs: dict[str, Any]):
        """String values should NOT be HTML-escaped (not an HTML context)."""
        lf = _make_lf(_simple_config('prompt', json.dumps('Value: {{value}}')), config_kwargs)
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        # These characters would normally be HTML-escaped by Handlebars
        rendered = resolved.render({'value': '<script>alert("xss")</script>'})
        assert rendered == 'Value: <script>alert("xss")</script>'

    def test_empty_context(self, config_kwargs: dict[str, Any]):
        """Rendering with no inputs leaves placeholders as empty strings."""
        lf = _make_lf(_simple_config('prompt', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        rendered = resolved.render()
        assert rendered == 'Hello !'

    def test_no_templates(self, config_kwargs: dict[str, Any]):
        """Rendering a value with no {{placeholders}} returns the value unchanged."""
        lf = _make_lf(_simple_config('prompt', json.dumps('Hello world!')), config_kwargs)
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        rendered = resolved.render({'name': 'unused'})
        assert rendered == 'Hello world!'


class TestRenderWithPydanticInputs:
    """Test rendering with Pydantic model inputs."""

    def test_pydantic_model_inputs(self, config_kwargs: dict[str, Any]):
        """Rendering with a Pydantic model as inputs."""

        class PromptInputs(BaseModel):
            user_name: str
            is_premium: bool = False

        lf = _make_lf(
            _simple_config('prompt', json.dumps('Welcome {{user_name}}!{{#if is_premium}} VIP{{/if}}')),
            config_kwargs,
        )
        var = lf.var('prompt', type=str, default='default', template_inputs=PromptInputs)
        resolved = var.get()
        rendered = resolved.render(PromptInputs(user_name='Alice', is_premium=True))
        assert rendered == 'Welcome Alice! VIP'

    def test_nested_model_inputs(self, config_kwargs: dict[str, Any]):
        """Rendering with nested Pydantic model fields using dot notation."""

        class Address(BaseModel):
            city: str
            country: str

        class UserInfo(BaseModel):
            name: str
            address: Address

        lf = _make_lf(
            _simple_config('prompt', json.dumps('User {{name}} from {{address.city}}, {{address.country}}')),
            config_kwargs,
        )
        var = lf.var('prompt', type=str, default='default', template_inputs=UserInfo)
        resolved = var.get()
        rendered = resolved.render(UserInfo(name='Alice', address=Address(city='London', country='UK')))
        assert rendered == 'User Alice from London, UK'


class TestRenderStructuredType:
    """Test rendering structured types (Pydantic models) where string fields contain templates."""

    def test_model_with_template_fields(self, config_kwargs: dict[str, Any]):
        """Rendering a Pydantic model where string fields contain {{placeholders}}."""

        class PromptConfig(BaseModel):
            system_prompt: str
            temperature: float
            max_tokens: int

        serialized = json.dumps(
            {
                'system_prompt': 'Hello {{user_name}}, how can I help?',
                'temperature': 0.7,
                'max_tokens': 100,
            }
        )

        lf = _make_lf(_simple_config('config', serialized), config_kwargs)
        var = lf.var(
            'config',
            type=PromptConfig,
            default=PromptConfig(system_prompt='default', temperature=0.5, max_tokens=50),
        )
        resolved = var.get()
        rendered = resolved.render({'user_name': 'Alice'})
        assert isinstance(rendered, PromptConfig)
        assert rendered.system_prompt == 'Hello Alice, how can I help?'
        assert rendered.temperature == 0.7
        assert rendered.max_tokens == 100


class TestRenderCodeDefault:
    """Test rendering when using code default values (no remote configuration)."""

    def test_render_code_default_string(self, config_kwargs: dict[str, Any]):
        """Rendering a code default string that contains templates."""
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.var('prompt', type=str, default='Hello {{name}}!')
        resolved = var.get()
        # Value is the code default
        assert resolved.value == 'Hello {{name}}!'
        # Rendering should still work
        rendered = resolved.render({'name': 'Alice'})
        assert rendered == 'Hello Alice!'


class TestRenderErrors:
    """Test error handling in render()."""

    def test_render_invalid_inputs_type(self, config_kwargs: dict[str, Any]):
        """Passing a non-dict/non-model to render() raises TypeError."""
        lf = _make_lf(_simple_config('prompt', json.dumps('Hello {{name}}')), config_kwargs)
        var = lf.var('prompt', type=str, default='default')
        resolved = var.get()
        with pytest.raises(TypeError, match='Expected a dict, Mapping, or Pydantic model'):
            resolved.render(42)


# =============================================================================
# template_inputs parameter tests
# =============================================================================


class TestTemplateInputsParam:
    """Test the template_inputs parameter on logfire.var()."""

    def test_template_inputs_schema_in_config(self, config_kwargs: dict[str, Any]):
        """template_inputs generates JSON Schema in the variable config."""

        class MyInputs(BaseModel):
            user_name: str
            count: int = 5

        lf = logfire.configure(**config_kwargs)
        var = lf.var('prompt', type=str, default='Hello {{user_name}}', template_inputs=MyInputs)
        config = var.to_config()
        assert config.template_inputs_schema is not None
        assert config.template_inputs_schema['type'] == 'object'
        assert 'user_name' in config.template_inputs_schema['properties']
        assert 'count' in config.template_inputs_schema['properties']

    def test_no_template_inputs(self, config_kwargs: dict[str, Any]):
        """Without template_inputs, schema is None."""
        lf = logfire.configure(**config_kwargs)
        var = lf.var('prompt', type=str, default='Hello')
        config = var.to_config()
        assert config.template_inputs_schema is None

    def test_template_inputs_stored_on_variable(self, config_kwargs: dict[str, Any]):
        """template_inputs_type is stored on the Variable instance."""

        class MyInputs(BaseModel):
            name: str

        lf = logfire.configure(**config_kwargs)
        var = lf.var('prompt', type=str, default='Hello', template_inputs=MyInputs)
        assert var.template_inputs_type is MyInputs


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
# Composition + rendering pipeline tests
# =============================================================================


class TestCompositionThenRendering:
    """Test the full pipeline: resolve → compose → render."""

    def test_composition_then_render(self, config_kwargs: dict[str, Any]):
        """<<references>> are expanded first, then {{placeholders}} are rendered."""
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
                            serialized_value=json.dumps('Hello {{user_name}}. <<snippet>>'),
                        ),
                    },
                    rollout=Rollout(labels={'production': 1.0}),
                    overrides=[],
                ),
            },
        )
        lf = _make_lf(variables_config, config_kwargs)
        var = lf.var('full_prompt', type=str, default='default')
        resolved = var.get()
        # After composition, <<snippet>> is expanded but {{placeholders}} remain
        assert resolved.value == 'Hello {{user_name}}. Welcome to {{company}}!'
        # After rendering, all {{placeholders}} are filled
        rendered = resolved.render({'user_name': 'Alice', 'company': 'Acme Corp'})
        assert rendered == 'Hello Alice. Welcome to Acme Corp!'


# =============================================================================
# TemplateVariable tests
# =============================================================================


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

    def test_composition_then_render(self, config_kwargs: dict[str, Any]):
        """<<refs>> expanded first, then {{}} rendered with inputs."""

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
                            serialized_value=json.dumps('Hello {{user_name}}. <<snippet>>'),
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

    def test_dict_inputs(self, config_kwargs: dict[str, Any]):
        """Passing a dict as inputs works (via Mapping path)."""
        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=dict)
        resolved = var.get({'name': 'Alice'})
        assert resolved.value == 'Hello Alice!'
