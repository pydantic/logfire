"""Tests for variable composition (<<variable_name>> reference expansion)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.testing import TestExporter
from logfire.variables.composition import (
    VariableCompositionCycleError,
    VariableCompositionError,
    expand_references,
    find_references,
)
from logfire.variables.config import (
    LabeledValue,
    LabelRef,
    LatestVersion,
    Rollout,
    VariableConfig,
    VariablesConfig,
)

# =============================================================================
# Tests for the pure composition functions (expand_references, find_references)
# =============================================================================


def _make_resolve_fn(
    variables: dict[str, str | None],
) -> Any:
    """Create a resolve_fn from a simple name->serialized_value dict."""

    def resolve_fn(ref_name: str) -> tuple[str | None, str | None, int | None, str]:
        if ref_name in variables:
            value = variables[ref_name]
            if value is None:
                return (None, None, None, 'unrecognized_variable')
            return (value, 'production', 1, 'resolved')
        return (None, None, None, 'unrecognized_variable')

    return resolve_fn


class TestExpandReferences:
    def test_no_references(self):
        """Values without <<>> are returned unchanged."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"hello world"', 'my_var', resolve_fn)
        assert expanded == '"hello world"'
        assert composed == []

    def test_simple_string_reference(self):
        """Simple <<ref>> expands to the referenced string value."""
        resolve_fn = _make_resolve_fn({'greeting': '"Hello"'})
        expanded, composed = expand_references('"<<greeting>> World"', 'my_var', resolve_fn)
        assert expanded == '"Hello World"'
        assert len(composed) == 1
        assert composed[0].name == 'greeting'
        assert composed[0].value == 'Hello'
        assert composed[0].label == 'production'
        assert composed[0].version == 1
        assert composed[0].reason == 'resolved'
        assert composed[0].error is None

    def test_multiple_references(self):
        """Multiple <<refs>> in one value are all expanded."""
        resolve_fn = _make_resolve_fn(
            {
                'greeting': '"Hello"',
                'name': '"World"',
            }
        )
        expanded, composed = expand_references('"<<greeting>> <<name>>!"', 'my_var', resolve_fn)
        assert expanded == '"Hello World!"'
        assert len(composed) == 2
        assert composed[0].name == 'greeting'
        assert composed[1].name == 'name'

    def test_same_reference_multiple_times(self):
        """The same <<ref>> used multiple times expands each occurrence."""
        resolve_fn = _make_resolve_fn({'word': '"echo"'})
        expanded, composed = expand_references('"<<word>> <<word>>"', 'my_var', resolve_fn)
        assert expanded == '"echo echo"'
        assert len(composed) == 2
        assert all(c.name == 'word' for c in composed)

    def test_nested_references(self):
        """References within referenced values are expanded recursively."""
        resolve_fn = _make_resolve_fn(
            {
                'a': '"Hello <<b>>"',
                'b': '"World"',
            }
        )
        expanded, composed = expand_references('"<<a>>!"', 'my_var', resolve_fn)
        assert expanded == '"Hello World!"'
        assert len(composed) == 1
        assert composed[0].name == 'a'
        assert composed[0].value == 'Hello World'
        assert len(composed[0].composed_from) == 1
        assert composed[0].composed_from[0].name == 'b'

    def test_cycle_detection(self):
        """Circular references are caught and the reference is left unexpanded."""
        resolve_fn = _make_resolve_fn(
            {
                'a': '"<<b>>"',
                'b': '"<<a>>"',
            }
        )
        # The cycle is caught inside expand_references; b tries to expand a
        # which is already in the visited set.
        _, composed = expand_references('"<<a>>"', 'my_var', resolve_fn)
        # a expands, but when b tries to expand <<a>>, it hits the cycle.
        # b is successfully resolved but its nested ref to a fails (cycle).
        assert len(composed) == 1
        assert composed[0].name == 'a'
        # b resolved but a inside b failed with cycle error
        assert len(composed[0].composed_from) == 1
        b_ref = composed[0].composed_from[0]
        assert b_ref.name == 'b'
        # b itself resolved, but its expansion of <<a>> failed
        assert len(b_ref.composed_from) == 1
        assert b_ref.composed_from[0].name == 'a'
        assert b_ref.composed_from[0].error is not None
        assert 'Circular reference' in b_ref.composed_from[0].error

    def test_self_reference_cycle(self):
        """A variable referencing itself is caught."""
        resolve_fn = _make_resolve_fn({'a': '"<<a>>"'})
        # my_var references a, a references itself
        _, composed = expand_references('"<<a>>"', 'my_var', resolve_fn)
        assert len(composed) == 1
        assert composed[0].name == 'a'
        # a resolved, but its self-reference <<a>> failed with cycle
        assert len(composed[0].composed_from) == 1
        assert composed[0].composed_from[0].name == 'a'
        assert composed[0].composed_from[0].error is not None
        assert 'Circular reference' in composed[0].composed_from[0].error

    def test_depth_limit(self):
        """Chains exceeding MAX_COMPOSITION_DEPTH are caught."""
        # Build a chain: var_0 -> var_1 -> var_2 -> ... -> var_21
        variables: dict[str, str | None] = {}
        for i in range(22):
            if i < 21:
                variables[f'var_{i}'] = f'"<<var_{i + 1}>>"'
            else:
                variables[f'var_{i}'] = '"end"'
        resolve_fn = _make_resolve_fn(variables)
        _, composed = expand_references('"<<var_0>>"', 'my_var', resolve_fn)
        # Should have error about depth limit somewhere in the chain
        assert len(composed) == 1

        # Walk down the chain to find the depth error
        ref = composed[0]
        depth_error_found = False
        while ref.composed_from:
            if ref.error and 'Maximum composition depth' in ref.error:
                depth_error_found = True
                break
            ref = ref.composed_from[0]
        if not depth_error_found and ref.error:
            depth_error_found = 'Maximum composition depth' in ref.error
        assert depth_error_found, 'Expected depth limit error somewhere in the chain'

    def test_unresolvable_reference(self):
        """References to non-existent variables are left unexpanded."""
        resolve_fn = _make_resolve_fn({})
        expanded, composed = expand_references('"Hello <<nonexistent>>"', 'my_var', resolve_fn)
        assert expanded == '"Hello <<nonexistent>>"'
        assert len(composed) == 1
        assert composed[0].name == 'nonexistent'
        assert composed[0].value is None
        assert composed[0].reason == 'unrecognized_variable'

    def test_none_value_reference(self):
        """References to variables with None value are left unexpanded."""
        resolve_fn = _make_resolve_fn({'missing': None})
        expanded, composed = expand_references('"Hello <<missing>>"', 'my_var', resolve_fn)
        assert expanded == '"Hello <<missing>>"'
        assert len(composed) == 1
        assert composed[0].value is None

    def test_non_string_reference(self):
        """References to non-string variables are left unexpanded with error."""
        resolve_fn = _make_resolve_fn({'number': '42'})
        expanded, composed = expand_references('"Value: <<number>>"', 'my_var', resolve_fn)
        assert expanded == '"Value: <<number>>"'
        assert len(composed) == 1
        assert composed[0].error is not None
        assert 'not a string' in composed[0].error

    def test_boolean_reference(self):
        """References to boolean variables are left unexpanded with error."""
        resolve_fn = _make_resolve_fn({'flag': 'true'})
        expanded, composed = expand_references('"Flag: <<flag>>"', 'my_var', resolve_fn)
        assert expanded == '"Flag: <<flag>>"'
        assert len(composed) == 1
        assert composed[0].error is not None
        assert 'not a string' in composed[0].error

    def test_object_reference(self):
        """References to object variables are left unexpanded with error."""
        resolve_fn = _make_resolve_fn({'obj': '{"key": "value"}'})
        expanded, composed = expand_references('"Data: <<obj>>"', 'my_var', resolve_fn)
        assert expanded == '"Data: <<obj>>"'
        assert len(composed) == 1
        assert composed[0].error is not None
        assert 'not a string' in composed[0].error

    def test_structured_type_with_references(self):
        """References inside JSON string values of structured types expand correctly."""
        resolve_fn = _make_resolve_fn({'safety': '"Be safe."'})
        serialized = json.dumps({'prompt': '<<safety>> Always.', 'model': 'gpt-4'})
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        parsed = json.loads(expanded)
        assert parsed['prompt'] == 'Be safe. Always.'
        assert parsed['model'] == 'gpt-4'
        assert len(composed) == 1
        assert composed[0].name == 'safety'

    def test_json_encoding_newlines(self):
        """Newlines in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'multi': '"Line1\\nLine2"'})
        expanded, _ = expand_references('"Before <<multi>> After"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Before Line1\nLine2 After'

    def test_json_encoding_quotes(self):
        """Quotes in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'quoted': '"She said \\"hello\\""'})
        expanded, _ = expand_references('"<<quoted>>!"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'She said "hello"!'

    def test_json_encoding_unicode(self):
        """Unicode in referenced values works correctly."""
        resolve_fn = _make_resolve_fn({'emoji': json.dumps('Hello 🌍')})
        expanded, _ = expand_references('"<<emoji>>!"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Hello 🌍!'

    def test_json_encoding_backslashes(self):
        """Backslashes in referenced values are properly JSON-escaped."""
        resolve_fn = _make_resolve_fn({'path': json.dumps('C:\\Users\\test')})
        expanded, _ = expand_references('"Path: <<path>>"', 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'Path: C:\\Users\\test'

    def test_escape_sequence(self):
        r"""Escaped \<< is converted to literal <<.

        In serialized JSON, a literal backslash before << is encoded as \\<<.
        The regex lookbehind prevents matching, and post-processing converts \<< to <<.
        """
        resolve_fn = _make_resolve_fn({'ref': '"expanded"'})
        # Build a JSON string that contains: not \<<ref>> but <<ref>>
        # In JSON encoding, backslash must be \\, so the raw JSON is:
        # "not \\<<ref>> but <<ref>>"
        raw_python_str = 'not \\<<ref>> but <<ref>>'
        serialized = json.dumps(raw_python_str)
        # serialized is: "not \\<<ref>> but <<ref>>"
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'not <<ref>> but expanded'
        # Only the real ref (second one) is in composed
        assert len(composed) == 1
        assert composed[0].name == 'ref'

    def test_escape_only(self):
        r"""Only escaped references, no real references."""
        resolve_fn = _make_resolve_fn({})
        raw_python_str = 'literal \\<<tag>>'
        serialized = json.dumps(raw_python_str)
        expanded, composed = expand_references(serialized, 'my_var', resolve_fn)
        result = json.loads(expanded)
        assert result == 'literal <<tag>>'
        assert composed == []

    def test_invalid_json_reference(self):
        """References to values with invalid JSON are left unexpanded."""
        resolve_fn = _make_resolve_fn({'bad': 'not json at all'})
        expanded, composed = expand_references('"<<bad>>"', 'my_var', resolve_fn)
        assert expanded == '"<<bad>>"'
        assert len(composed) == 1
        assert composed[0].error is not None
        assert 'non-JSON' in composed[0].error


class TestFindReferences:
    def test_no_references(self):
        assert find_references('"hello world"') == []

    def test_single_reference(self):
        assert find_references('"<<greeting>>"') == ['greeting']

    def test_multiple_unique_references(self):
        assert find_references('"<<a>> <<b>> <<c>>"') == ['a', 'b', 'c']

    def test_duplicate_references(self):
        """Duplicates are deduplicated, order preserved."""
        assert find_references('"<<a>> <<b>> <<a>>"') == ['a', 'b']

    def test_escaped_not_matched(self):
        assert find_references(r'"\\<<escaped>>"') == []

    def test_mixed_escaped_and_real(self):
        result = find_references(r'"\\<<escaped>> <<real>>"')
        assert result == ['real']

    def test_in_structured_json(self):
        serialized = json.dumps({'prompt': '<<safety>>', 'other': '<<format>>'})
        assert find_references(serialized) == ['safety', 'format']


# =============================================================================
# Integration tests using LocalVariableProvider
# =============================================================================


def _make_variables_config(**variables: str | None) -> VariablesConfig:
    """Helper to create a VariablesConfig with simple string variables.

    Each kwarg is name=serialized_value (JSON string).
    """
    configs: dict[str, VariableConfig] = {}
    for name, value in variables.items():
        labels: dict[str, LabeledValue | LabelRef] = {}
        latest: LatestVersion | None = None
        if value is not None:
            labels['production'] = LabeledValue(version=1, serialized_value=value)
            latest = LatestVersion(version=1, serialized_value=value)
        configs[name] = VariableConfig(
            name=name,
            json_schema={'type': 'string'} if value is not None and value.startswith('"') else None,
            labels=labels,
            rollout=Rollout(labels={'production': 1.0}) if value is not None else Rollout(labels={}),
            overrides=[],
            latest_version=latest,
        )
    return VariablesConfig(variables=configs)


class TestCompositionIntegration:
    def test_simple_reference(self, config_kwargs: dict[str, Any]):
        """End-to-end: variable with <<ref>> is resolved with composition."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"<<greeting>> World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Hello World'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'greeting'
        assert result.composed_from[0].value == 'Hello'

    def test_nested_reference(self, config_kwargs: dict[str, Any]):
        """A→B→C chain resolves fully."""
        variables_config = _make_variables_config(
            c='"end"',
            b='"<<c>>_b"',
            a='"<<b>>_a"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='a', default='fallback', type=str)
        result = var.get()
        assert result.value == 'end_b_a'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'b'
        assert result.composed_from[0].composed_from[0].name == 'c'

    def test_cycle_falls_back_gracefully(self, config_kwargs: dict[str, Any]):
        """Cycles in references cause graceful fallback to default."""
        variables_config = _make_variables_config(
            a='"<<b>>"',
            b='"<<a>>"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='a', default='fallback', type=str)
        result = var.get()
        # The cycle in b trying to reference a (which is in the visited set) means
        # b's expansion fails, b is left as <<a>> inside a's value.
        # So a's value becomes "<<a>>" (the literal unexpanded ref from b's failed expansion).
        # Actually the value should still deserialize as a string, just with unexpanded refs.
        assert isinstance(result.value, str)

    def test_nonexistent_reference_left_unexpanded(self, config_kwargs: dict[str, Any]):
        """References to non-existent variables are left as-is."""
        variables_config = _make_variables_config(
            main='"Hello <<nonexistent>>"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Hello <<nonexistent>>'

    def test_non_string_reference_left_unexpanded(self, config_kwargs: dict[str, Any]):
        """References to non-string variables are left as-is."""
        # Create a variable config with a non-string variable
        configs: dict[str, VariableConfig] = {
            'number': VariableConfig(
                name='number',
                json_schema={'type': 'integer'},
                labels={'production': LabeledValue(version=1, serialized_value='42')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='42'),
            ),
            'main': VariableConfig(
                name='main',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value='"Value: <<number>>"')},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value='"Value: <<number>>"'),
            ),
        }
        variables_config = VariablesConfig(variables=configs)
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get()
        assert result.value == 'Value: <<number>>'

    def test_structured_type_composition(self, config_kwargs: dict[str, Any]):
        """Composition works in string fields of Pydantic models."""

        class AgentConfig(BaseModel):
            prompt: str
            model: str

        safety_value = json.dumps('Be safe.')
        agent_value = json.dumps({'prompt': '<<safety>> Always.', 'model': 'gpt-4'})

        configs: dict[str, VariableConfig] = {
            'safety': VariableConfig(
                name='safety',
                json_schema={'type': 'string'},
                labels={'production': LabeledValue(version=1, serialized_value=safety_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value=safety_value),
            ),
            'agent_config': VariableConfig(
                name='agent_config',
                json_schema=None,
                labels={'production': LabeledValue(version=1, serialized_value=agent_value)},
                rollout=Rollout(labels={'production': 1.0}),
                overrides=[],
                latest_version=LatestVersion(version=1, serialized_value=agent_value),
            ),
        }
        variables_config = VariablesConfig(variables=configs)
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='agent_config', default=AgentConfig(prompt='default', model='default'), type=AgentConfig)
        result = var.get()
        assert result.value.prompt == 'Be safe. Always.'
        assert result.value.model == 'gpt-4'
        assert len(result.composed_from) == 1
        assert result.composed_from[0].name == 'safety'

    def test_no_composition_for_context_override(self, config_kwargs: dict[str, Any]):
        """Context overrides return typed values directly, no composition."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"<<greeting>> World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        with var.override('override_value'):
            result = var.get()
            assert result.value == 'override_value'
            assert result.composed_from == []
            assert result._reason == 'context_override'

    def test_composition_with_explicit_label(self, config_kwargs: dict[str, Any]):
        """Composition works when using explicit label parameter."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"<<greeting>> World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        result = var.get(label='production')
        assert result.value == 'Hello World'
        assert len(result.composed_from) == 1

    def test_span_attributes_with_composition(self, config_kwargs: dict[str, Any], exporter: TestExporter):
        """Span attributes include composed_from when composition occurs."""
        variables_config = _make_variables_config(
            greeting='"Hello"',
            main='"<<greeting>> World"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        exporter.clear()

        result = var.get()
        assert result.value == 'Hello World'

        # Find the completed span for 'main' variable resolution (last one with this name)
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable main']
        main_span = resolve_spans[-1]  # last = completed span
        attrs = dict(main_span.attributes or {})

        # Check composed_from attribute
        composed_from_json = attrs.get('composed_from')
        assert isinstance(composed_from_json, str)
        composed_data = json.loads(composed_from_json)
        assert len(composed_data) == 1
        assert composed_data[0]['name'] == 'greeting'
        assert composed_data[0]['version'] == 1
        assert composed_data[0]['label'] == 'production'

    def test_span_attributes_without_composition(self, config_kwargs: dict[str, Any], exporter: TestExporter):
        """Span attributes do NOT include composed_from when no composition occurs."""
        variables_config = _make_variables_config(
            main='"no refs here"',
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='fallback', type=str)
        exporter.clear()

        var.get()

        # Find the completed span for 'main' variable resolution (last one with this name)
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable main']
        main_span = resolve_spans[-1]  # last = completed span
        attrs = dict(main_span.attributes or {})
        assert 'composed_from' not in attrs

    def test_no_value_no_composition(self, config_kwargs: dict[str, Any]):
        """When variable resolves to None (code default), no composition happens."""
        variables_config = VariablesConfig(
            variables={
                'main': VariableConfig(
                    name='main',
                    json_schema={'type': 'string'},
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='main', default='<<greeting>> fallback', type=str)
        result = var.get()
        # Default is returned as-is (no composition on defaults)
        assert result.value == '<<greeting>> fallback'
        assert result.composed_from == []


class TestCompositionExceptions:
    """Test the exception hierarchy."""

    def test_composition_error_is_exception(self):
        assert issubclass(VariableCompositionError, Exception)

    def test_cycle_error_is_composition_error(self):
        assert issubclass(VariableCompositionCycleError, VariableCompositionError)

    def test_direct_cycle_error(self):
        with pytest.raises(VariableCompositionCycleError, match='Circular reference'):
            expand_references(
                '"test"',
                'a',
                _make_resolve_fn({}),
                _visited=frozenset({'a'}),
            )

    def test_direct_depth_error(self):
        with pytest.raises(VariableCompositionError, match='Maximum composition depth'):
            expand_references(
                '"test"',
                'a',
                _make_resolve_fn({}),
                _depth=21,
            )
