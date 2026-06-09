"""Tests for variable template rendering (Handlebars {{placeholder}} support)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import warnings
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

    def test_dataclass_inputs_type(self, config_kwargs: dict[str, Any]):
        """A dataclass `inputs_type` works end-to-end: schema generation and get(inputs) rendering."""
        from dataclasses import dataclass

        @dataclass
        class Inputs:
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hello {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', type=str, default='default', inputs_type=Inputs)
        # The derived template_inputs_schema reflects the dataclass fields...
        assert 'name' in var.get_template_inputs_schema()['properties']
        # ...and get(inputs) renders against a dataclass instance.
        assert var.get(Inputs(name='Alice')).value == 'Hello Alice!'

    def test_invalid_name_error(self, config_kwargs: dict[str, Any]):
        """template_var() applies the same Python identifier name validation as var()."""

        class Inputs(BaseModel):
            name: str

        lf = logfire.configure(**config_kwargs)
        with pytest.raises(ValueError, match='Invalid variable name'):
            lf.template_var('not-valid', type=str, default='x', inputs_type=Inputs)

    def test_type_inferred_from_default(self, config_kwargs: dict[str, Any]):
        """template_var() infers `type` from a non-callable default, mirroring `var()`."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('greeting', json.dumps('Hi {{name}}!')), config_kwargs)
        var = lf.template_var('greeting', default='Hi {{name}}!', inputs_type=Inputs)
        assert var.value_type is str
        assert var.get(Inputs(name='Alice')).value == 'Hi Alice!'

    def test_type_required_for_resolve_function_default(self, config_kwargs: dict[str, Any]):
        """template_var() with a callable default still requires an explicit `type=`."""

        class Inputs(BaseModel):
            name: str

        lf = logfire.configure(**config_kwargs)

        def make_default(targeting_key: str | None, attributes: Any) -> str:
            return 'Hi {{name}}!'

        with pytest.raises(TypeError, match='resolve function'):
            lf.template_var('greeting', default=make_default, inputs_type=Inputs)

    def test_type_required_for_none_default(self, config_kwargs: dict[str, Any]):
        """A None default can't infer a usable type — both factories require explicit `type=`."""

        class Inputs(BaseModel):
            name: str

        lf = logfire.configure(**config_kwargs)

        with pytest.raises(TypeError, match='default` is None'):
            lf.var('plain_none', default=None)
        with pytest.raises(TypeError, match='default` is None'):
            lf.template_var('tmpl_none', default=None, inputs_type=Inputs)
        # Providing an explicit type makes a nullable variable work.
        ok = lf.var('plain_optional', type=int | None, default=None)  # pyright: ignore[reportArgumentType]
        assert ok.value_type == (int | None)

    def test_remote_render_error_records_exception(self, config_kwargs: dict[str, Any]):
        """Invalid remote templates fall back, warn, and record the render exception."""

        class Inputs(BaseModel):
            name: str

        lf = _make_lf(_simple_config('prompt', json.dumps('Hello {{#if name}}')), config_kwargs)
        var = lf.template_var('prompt', type=str, default='fallback', inputs_type=Inputs)

        with pytest.warns(RuntimeWarning, match='template rendering failed'):
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


class TestRenderSerializedString:
    """Cover the input-shape branches of `render_serialized_string`."""

    def test_inputs_none_returns_empty_context(self):
        """`inputs=None` is treated as an empty context."""
        from logfire.variables.abstract import render_serialized_string

        # No placeholders to render, but the call exercises `_inputs_to_context(None)`.
        assert render_serialized_string('"hello"', None) == '"hello"'

    def test_inputs_mapping(self):
        """A plain dict input goes through the Mapping branch of `_inputs_to_context`."""
        from logfire.variables.abstract import render_serialized_string

        result = render_serialized_string('"Hello {{name}}!"', {'name': 'Alice'})
        assert json.loads(result) == 'Hello Alice!'

    def test_inputs_invalid_type_raises(self):
        """An input that serializes to a non-mapping raises TypeError."""
        from logfire.variables.abstract import render_serialized_string

        with pytest.raises(TypeError, match='mapping is required for a template context'):
            render_serialized_string('"x"', 42)

    def test_inputs_unserializable_raises(self):
        """An input that pydantic can't serialize at all raises a guiding TypeError."""
        from logfire.variables.abstract import render_serialized_string

        with pytest.raises(TypeError, match='Could not serialize render inputs'):
            render_serialized_string('"x"', object())

    def test_inputs_dataclass(self):
        """A dataclass input is serialized to a context via pydantic (arbitrary inputs_type)."""
        from dataclasses import dataclass

        from logfire.variables.abstract import render_serialized_string

        @dataclass
        class Inputs:
            name: str

        result = render_serialized_string('"Hello {{name}}!"', Inputs(name='Alice'))
        assert json.loads(result) == 'Hello Alice!'

    def test_nested_dict_input_is_walked(self):
        """Nested dict values in inputs are walked by `_wrap_safe_value`."""
        from logfire.variables.abstract import render_serialized_string

        result = render_serialized_string(
            json.dumps('Hi {{user.name}} from {{user.city}}'),
            {'user': {'name': 'Alice', 'city': 'London'}},
        )
        assert json.loads(result) == 'Hi Alice from London'

    def test_list_input_is_walked(self):
        """List values in inputs are walked by `_wrap_safe_value`."""
        from logfire.variables.abstract import render_serialized_string

        result = render_serialized_string(
            json.dumps('First: {{items.[0]}}, Second: {{items.[1]}}'),
            {'items': ['apple', 'banana']},
        )
        assert json.loads(result) == 'First: apple, Second: banana'

    def test_list_value_is_walked(self):
        """List values inside the rendered value are walked by `_render_json_value`."""
        from logfire.variables.abstract import render_serialized_string

        result = render_serialized_string(
            json.dumps({'tags': ['Hello {{name}}', 'static']}),
            {'name': 'Alice'},
        )
        assert json.loads(result) == {'tags': ['Hello Alice', 'static']}


class TestTemplateVariableOverrideRender:
    """Cover render failures on `TemplateVariable.override(...)`."""

    def test_override_render_failure_falls_back(self, config_kwargs: dict[str, Any]):
        """A TemplateVariable override that renders to an invalid value records the exception."""
        from typing import Annotated

        from pydantic import StringConstraints, ValidationError

        class Config(BaseModel):
            code: Annotated[str, StringConstraints(pattern=r'^[A-Z]+$')]

        class Inputs(BaseModel):
            code: str

        lf = logfire.configure(**config_kwargs)
        var = lf.template_var(
            'config',
            type=Config,
            default=Config(code='OK'),
            inputs_type=Inputs,
        )

        # `model_construct` bypasses the constructor's validation so the override can hold
        # the unrendered template — `templated_config` is itself a *valid* template; it's
        # only the rendered result (`abc123`) that violates the pattern constraint.
        # Exercises the outer error handler's code-default fallback for inputs that
        # produce a constraint-violating render.
        templated_config = Config.model_construct(code='{{code}}')
        invalid_inputs = Inputs(code='abc123')
        with var.override(templated_config):
            with pytest.warns(RuntimeWarning, match='value failed validation'):
                resolved = var.get(invalid_inputs)

        assert resolved.value == Config(code='OK')  # falls back to the code default
        assert resolved.reason == 'validation_error'
        assert isinstance(resolved.exception, ValidationError)


class TestTemplateMismatchPolicy:
    """Render-time `{{field}}` mismatch policy covering all three values + precedence."""

    def _setup(
        self,
        *,
        default: str,
        config_kwargs: dict[str, Any],
        instance_policy: Any = None,
        variable_policy: Any = None,
    ):
        from pydantic import BaseModel as _BaseModel

        class Inputs(_BaseModel):
            user_name: str

        local_opts_kwargs: dict[str, Any] = {'config': VariablesConfig(variables={})}
        if instance_policy is not None:
            local_opts_kwargs['template_mismatch_policy'] = instance_policy
        config_kwargs['variables'] = LocalVariablesOptions(**local_opts_kwargs)
        lf = logfire.configure(**config_kwargs)
        kwargs: dict[str, Any] = {'type': str, 'default': default, 'inputs_type': Inputs}
        if variable_policy is not None:
            kwargs['template_mismatch_policy'] = variable_policy
        var = lf.template_var('prompt', **kwargs)
        return var, Inputs

    def test_default_policy_is_warn(self, config_kwargs: dict[str, Any]):
        var, Inputs = self._setup(default='Hi {{user_name}} {{missing}}', config_kwargs=config_kwargs)
        with pytest.warns(RuntimeWarning, match="references 'missing'"):
            resolved = var.get(Inputs(user_name='Alice'))
        assert resolved.value == 'Hi Alice '

    def test_warn_policy_is_filter_independent(self, config_kwargs: dict[str, Any]):
        """Under `-W error`, the 'warn' policy still renders-and-warns instead of being swallowed.

        Regression: a raw `warnings.warn` would escalate under filterwarnings=error and be caught by
        the resolve fallback, silently turning 'warn' into a code-default fallback (reason='other_error').
        The filter-independent emitter keeps the rendered result regardless of the warning filter.
        """
        var, Inputs = self._setup(default='Hi {{user_name}} {{missing}}', config_kwargs=config_kwargs)
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            resolved = var.get(Inputs(user_name='Alice'))
        # The bug produced reason='other_error' with the unrendered code default; the fix renders.
        assert resolved.reason != 'other_error'
        assert resolved.value == 'Hi Alice '

    def test_no_warning_when_inputs_satisfied(self, config_kwargs: dict[str, Any]):
        var, Inputs = self._setup(default='Hi {{user_name}}!', config_kwargs=config_kwargs)
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            resolved = var.get(Inputs(user_name='Alice'))
        assert resolved.value == 'Hi Alice!'

    def test_per_variable_error_raises(self, config_kwargs: dict[str, Any]):
        from logfire.variables.variable import TemplateInputsMismatchError

        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            variable_policy='error',
        )
        with pytest.raises(TemplateInputsMismatchError, match="references 'missing'"):
            var.get(Inputs(user_name='Alice'))

    def test_per_variable_ignore_renders_silently(self, config_kwargs: dict[str, Any]):
        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            variable_policy='ignore',
        )
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            resolved = var.get(Inputs(user_name='Alice'))
        assert resolved.value == 'Hi '

    def test_instance_level_error(self, config_kwargs: dict[str, Any]):
        from logfire.variables.variable import TemplateInputsMismatchError

        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            instance_policy='error',
        )
        with pytest.raises(TemplateInputsMismatchError):
            var.get(Inputs(user_name='Alice'))

    def test_variable_level_relaxes_instance_error(self, config_kwargs: dict[str, Any]):
        """Variable-level wins, even when relaxing — instance 'error' + variable 'ignore' → ignore."""
        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            instance_policy='error',
            variable_policy='ignore',
        )
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            resolved = var.get(Inputs(user_name='Alice'))
        assert resolved.value == 'Hi '

    def test_variable_level_escalates_instance_warn(self, config_kwargs: dict[str, Any]):
        """Instance 'warn' + variable 'error' → error."""
        from logfire.variables.variable import TemplateInputsMismatchError

        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            instance_policy='warn',
            variable_policy='error',
        )
        with pytest.raises(TemplateInputsMismatchError):
            var.get(Inputs(user_name='Alice'))

    def test_variable_level_relaxes_instance_warn_to_ignore(self, config_kwargs: dict[str, Any]):
        """Instance 'warn' + variable 'ignore' → ignore (no warning)."""
        var, Inputs = self._setup(
            default='Hi {{missing}}',
            config_kwargs=config_kwargs,
            instance_policy='warn',
            variable_policy='ignore',
        )
        with warnings.catch_warnings():
            warnings.simplefilter('error', RuntimeWarning)
            var.get(Inputs(user_name='Alice'))
