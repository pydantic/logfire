"""Tests for managed variables."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import os
import time
import unittest.mock
import warnings
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import pytest
import requests_mock as requests_mock_module
from pydantic import BaseModel, ValidationError
from requests import Session

import logfire
from logfire._internal.config import LocalVariablesOptions, VariablesOptions
from logfire.testing import TestExporter
from logfire.variables.abstract import NoOpVariableProvider, ResolvedVariable, VariableProvider
from logfire.variables.config import (
    KeyIsNotPresent,
    KeyIsPresent,
    LabeledValue,
    LabelRef,
    Rollout,
    RolloutOverride,
    ValueDoesNotEqual,
    ValueDoesNotMatchRegex,
    ValueEquals,
    ValueIsIn,
    ValueIsNotIn,
    ValueMatchesRegex,
    VariableConfig,
    VariablesConfig,
)
from logfire.variables.local import LocalVariableProvider
from logfire.variables.remote import LogfireRemoteVariableProvider
from logfire.variables.variable import is_resolve_function

# =============================================================================
# Test Condition Classes
# =============================================================================


class TestValueEquals:
    def test_matches_when_equal(self):
        condition = ValueEquals(attribute='plan', value='enterprise')
        assert condition.matches({'plan': 'enterprise'}) is True

    def test_no_match_when_different(self):
        condition = ValueEquals(attribute='plan', value='enterprise')
        assert condition.matches({'plan': 'free'}) is False

    def test_no_match_when_missing(self):
        condition = ValueEquals(attribute='plan', value='enterprise')
        assert condition.matches({}) is False

    def test_kind_discriminator(self):
        condition = ValueEquals(attribute='plan', value='enterprise')
        assert condition.kind == 'value-equals'


class TestValueDoesNotEqual:
    def test_matches_when_different(self):
        condition = ValueDoesNotEqual(attribute='plan', value='enterprise')
        assert condition.matches({'plan': 'free'}) is True

    def test_no_match_when_equal(self):
        condition = ValueDoesNotEqual(attribute='plan', value='enterprise')
        assert condition.matches({'plan': 'enterprise'}) is False

    def test_matches_when_missing(self):
        # When missing, uses object() sentinel which won't equal any value
        condition = ValueDoesNotEqual(attribute='plan', value='enterprise')
        assert condition.matches({}) is True

    def test_kind_discriminator(self):
        condition = ValueDoesNotEqual(attribute='plan', value='enterprise')
        assert condition.kind == 'value-does-not-equal'


class TestValueIsIn:
    def test_matches_when_in_list(self):
        condition = ValueIsIn(attribute='country', values=['US', 'UK', 'CA'])
        assert condition.matches({'country': 'US'}) is True

    def test_no_match_when_not_in_list(self):
        condition = ValueIsIn(attribute='country', values=['US', 'UK', 'CA'])
        assert condition.matches({'country': 'DE'}) is False

    def test_no_match_when_missing(self):
        condition = ValueIsIn(attribute='country', values=['US', 'UK', 'CA'])
        assert condition.matches({}) is False

    def test_kind_discriminator(self):
        condition = ValueIsIn(attribute='country', values=['US', 'UK'])
        assert condition.kind == 'value-is-in'


class TestValueIsNotIn:
    def test_matches_when_not_in_list(self):
        condition = ValueIsNotIn(attribute='country', values=['blocked', 'restricted'])
        assert condition.matches({'country': 'US'}) is True

    def test_no_match_when_in_list(self):
        condition = ValueIsNotIn(attribute='country', values=['blocked', 'restricted'])
        assert condition.matches({'country': 'blocked'}) is False

    def test_matches_when_missing(self):
        # When missing, uses object() sentinel which won't be in the list
        condition = ValueIsNotIn(attribute='country', values=['blocked', 'restricted'])
        assert condition.matches({}) is True

    def test_kind_discriminator(self):
        condition = ValueIsNotIn(attribute='country', values=['blocked'])
        assert condition.kind == 'value-is-not-in'


class TestValueMatchesRegex:
    def test_matches_regex(self):
        condition = ValueMatchesRegex(attribute='email', pattern=r'@example\.com$')
        assert condition.matches({'email': 'user@example.com'}) is True

    def test_no_match_regex(self):
        condition = ValueMatchesRegex(attribute='email', pattern=r'@example\.com$')
        assert condition.matches({'email': 'user@other.com'}) is False

    def test_no_match_when_missing(self):
        condition = ValueMatchesRegex(attribute='email', pattern=r'@example\.com$')
        assert condition.matches({}) is False

    def test_no_match_when_not_string(self):
        condition = ValueMatchesRegex(attribute='email', pattern=r'@example\.com$')
        assert condition.matches({'email': 123}) is False

    def test_kind_discriminator(self):
        condition = ValueMatchesRegex(attribute='email', pattern=r'.*')
        assert condition.kind == 'value-matches-regex'


class TestValueDoesNotMatchRegex:
    def test_matches_when_no_match(self):
        """Condition matches (returns True) when the value does NOT match the regex pattern."""
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'@blocked\.com$')
        # user@other.com does NOT match @blocked.com$, so condition returns True
        assert condition.matches({'email': 'user@other.com'}) is True

    def test_no_match_when_pattern_matches(self):
        """Condition does not match (returns False) when the value DOES match the regex pattern."""
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'@blocked\.com$')
        # user@blocked.com DOES match @blocked.com$, so condition returns False
        assert condition.matches({'email': 'user@blocked.com'}) is False

    def test_match_when_missing(self):
        """Missing attributes cannot match the pattern, so they satisfy 'does not match'."""
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'.*')
        assert condition.matches({}) is True

    def test_match_when_not_string(self):
        """Non-string values cannot match the pattern, so they satisfy 'does not match'."""
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'.*')
        assert condition.matches({'email': 123}) is True

    def test_kind_discriminator(self):
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'.*')
        assert condition.kind == 'value-does-not-match-regex'


class TestKeyIsPresent:
    def test_matches_when_present(self):
        condition = KeyIsPresent(attribute='custom_prompt')
        assert condition.matches({'custom_prompt': 'value'}) is True

    def test_matches_when_present_with_none(self):
        condition = KeyIsPresent(attribute='custom_prompt')
        assert condition.matches({'custom_prompt': None}) is True

    def test_no_match_when_missing(self):
        condition = KeyIsPresent(attribute='custom_prompt')
        assert condition.matches({}) is False

    def test_kind_discriminator(self):
        condition = KeyIsPresent(attribute='key')
        assert condition.kind == 'key-is-present'


class TestKeyIsNotPresent:
    def test_matches_when_missing(self):
        condition = KeyIsNotPresent(attribute='deprecated_flag')
        assert condition.matches({}) is True

    def test_no_match_when_present(self):
        condition = KeyIsNotPresent(attribute='deprecated_flag')
        assert condition.matches({'deprecated_flag': True}) is False

    def test_kind_discriminator(self):
        condition = KeyIsNotPresent(attribute='key')
        assert condition.kind == 'key-is-not-present'


# =============================================================================
# Test Rollout
# =============================================================================


class TestRollout:
    def test_select_label_deterministic_with_seed(self):
        rollout = Rollout(labels={'v1': 0.5, 'v2': 0.5})
        # With a seed, the result should be deterministic
        result1 = rollout.select_label('user123')
        result2 = rollout.select_label('user123')
        assert result1 == result2

    def test_select_label_different_seeds_can_differ(self):
        rollout = Rollout(labels={'v1': 0.5, 'v2': 0.5})
        # Different seeds may produce different results
        results = {rollout.select_label(f'user{i}') for i in range(100)}
        # With 50/50 split, we should see both labels
        assert results == {'v1', 'v2'}

    def test_select_label_can_return_none(self):
        rollout = Rollout(labels={'v1': 0.3})  # 70% chance of None
        results = {rollout.select_label(f'user{i}') for i in range(100)}
        # Should include None in results
        assert None in results
        assert 'v1' in results

    def test_select_label_full_probability(self):
        rollout = Rollout(labels={'v1': 1.0})
        for i in range(10):
            assert rollout.select_label(f'user{i}') == 'v1'

    def test_select_label_without_seed(self):
        rollout = Rollout(labels={'v1': 0.5, 'v2': 0.5})
        # Without seed, still works but isn't deterministic
        result = rollout.select_label(None)
        assert result in {'v1', 'v2'}

    def test_validation_sum_exceeds_one(self):
        # Note: Validation only runs when using TypeAdapter (not direct instantiation)
        with pytest.raises(ValidationError, match='Label proportions must not sum to more than 1'):
            VariableConfig.model_validate({'rollout': {'labels': {'v1': 0.6, 'v2': 0.6}}})


# =============================================================================
# Test RolloutOverride
# =============================================================================


class TestRolloutOverride:
    def test_single_condition_override_applies_when_matched(self):
        """Test that override applies when single condition matches."""
        config = VariableConfig(
            name='test_var',
            labels={
                'default': LabeledValue(version=1, serialized_value='"default_value"'),
                'premium': LabeledValue(version=1, serialized_value='"premium_value"'),
            },
            rollout=Rollout(labels={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(labels={'premium': 1.0}),
                ),
            ],
        )

        # Without matching attribute, default rollout applies
        label = config.resolve_label(targeting_key='user1')
        assert label == 'default'

        # With matching attribute, override applies
        label = config.resolve_label(targeting_key='user1', attributes={'plan': 'enterprise'})
        assert label == 'premium'

        # With non-matching attribute, default rollout applies
        label = config.resolve_label(targeting_key='user1', attributes={'plan': 'free'})
        assert label == 'default'

    def test_multiple_conditions_require_all_to_match(self):
        """Test that all conditions must match for an override to apply (AND logic)."""
        config = VariableConfig(
            name='test_var',
            labels={
                'default': LabeledValue(version=1, serialized_value='"default_value"'),
                'premium': LabeledValue(version=1, serialized_value='"premium_value"'),
            },
            rollout=Rollout(labels={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[
                        ValueEquals(attribute='plan', value='enterprise'),
                        ValueIsIn(attribute='country', values=['US', 'UK']),
                    ],
                    rollout=Rollout(labels={'premium': 1.0}),
                ),
            ],
        )

        # Both conditions match -> override applies
        label = config.resolve_label(
            targeting_key='user1',
            attributes={'plan': 'enterprise', 'country': 'US'},
        )
        assert label == 'premium'

        # Only first condition matches -> override does not apply
        label = config.resolve_label(
            targeting_key='user1',
            attributes={'plan': 'enterprise', 'country': 'DE'},
        )
        assert label == 'default'

        # Only second condition matches -> override does not apply
        label = config.resolve_label(
            targeting_key='user1',
            attributes={'plan': 'free', 'country': 'UK'},
        )
        assert label == 'default'

        # Neither condition matches -> override does not apply
        label = config.resolve_label(
            targeting_key='user1',
            attributes={'plan': 'free', 'country': 'DE'},
        )
        assert label == 'default'

        # No attributes -> override does not apply
        label = config.resolve_label(targeting_key='user1')
        assert label == 'default'


# =============================================================================
# Test VariableConfig
# =============================================================================


class TestVariableConfig:
    @pytest.fixture
    def simple_config(self) -> VariableConfig:
        return VariableConfig(
            name='test_var',
            labels={
                'default': LabeledValue(version=1, serialized_value='"default value"'),
                'experimental': LabeledValue(version=1, serialized_value='"experimental value"'),
            },
            rollout=Rollout(labels={'default': 0.8, 'experimental': 0.2}),
            overrides=[],
        )

    @pytest.fixture
    def config_with_overrides(self) -> VariableConfig:
        return VariableConfig(
            name='test_var',
            labels={
                'default': LabeledValue(version=1, serialized_value='"default value"'),
                'premium': LabeledValue(version=1, serialized_value='"premium value"'),
            },
            rollout=Rollout(labels={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(labels={'premium': 1.0}),
                ),
            ],
        )

    def test_resolve_label_basic(self, simple_config: VariableConfig):
        # Deterministic selection with targeting_key
        label = simple_config.resolve_label(targeting_key='user123')
        assert label in {'default', 'experimental'}

    def test_resolve_label_with_override(self, config_with_overrides: VariableConfig):
        # Without matching attributes, uses default rollout
        label = config_with_overrides.resolve_label(targeting_key='user1')
        assert label == 'default'

        # With matching attributes, uses override rollout
        label = config_with_overrides.resolve_label(
            targeting_key='user1',
            attributes={'plan': 'enterprise'},
        )
        assert label == 'premium'

    def test_resolve_label_can_return_none(self):
        config = VariableConfig(
            name='test_var',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 0.5}),  # 50% chance of None
            overrides=[],
        )
        # Try many times to get None
        results = [config.resolve_label(targeting_key=f'user{i}') for i in range(100)]
        assert None in results

    def test_validation_invalid_label_key(self):
        with pytest.raises(ValidationError, match="Label 'correct_key' present in `rollout.labels` is not present"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'labels': {
                        'wrong_key': {'version': 1, 'serialized_value': '"value"'},
                    },
                    'rollout': {'labels': {'correct_key': 1.0}},
                    'overrides': [],
                }
            )

    def test_validation_rollout_references_missing_label(self):
        with pytest.raises(ValidationError, match="Label 'missing' present in `rollout.labels` is not present"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'labels': {
                        'v1': {'version': 1, 'serialized_value': '"value"'},
                    },
                    'rollout': {'labels': {'missing': 1.0}},
                    'overrides': [],
                }
            )

    def test_validation_override_references_missing_label(self):
        with pytest.raises(ValidationError, match="Label 'missing' present in `overrides"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'labels': {
                        'v1': {'version': 1, 'serialized_value': '"value"'},
                    },
                    'rollout': {'labels': {'v1': 1.0}},
                    'overrides': [
                        {
                            'conditions': [],
                            'rollout': {'labels': {'missing': 1.0}},
                        }
                    ],
                }
            )


# =============================================================================
# Test VariablesConfig
# =============================================================================


class TestVariablesConfig:
    def test_basic_config(self):
        config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        assert 'my_var' in config.variables

    def test_validation_invalid_variable_key(self):
        with pytest.raises(ValidationError, match='invalid lookup key'):
            VariablesConfig.model_validate(
                {
                    'variables': {
                        'wrong_key': {
                            'name': 'correct_name',
                            'labels': {'v1': {'version': 1, 'serialized_value': '"value"'}},
                            'rollout': {'labels': {'v1': 1.0}},
                            'overrides': [],
                        }
                    }
                }
            )

    def test_validate_python(self):
        config = VariablesConfig.model_validate(
            {
                'variables': {
                    'my_var': {
                        'name': 'my_var',
                        'labels': {'v1': {'version': 1, 'serialized_value': '"value"'}},
                        'rollout': {'labels': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            }
        )
        assert isinstance(config, VariablesConfig)
        assert 'my_var' in config.variables

    def test_get_validation_errors_no_errors(self, config_kwargs: dict[str, Any]):
        """Test that get_validation_errors returns empty dict when all labels are valid."""
        lf = logfire.configure(**config_kwargs)
        config = VariablesConfig(
            variables={
                'valid_var': VariableConfig(
                    name='valid_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"valid_string"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        var = lf.var(name='valid_var', default='default', type=str)
        errors = config.get_validation_errors([var])
        assert errors == {}

    def test_get_validation_errors_missing_config(self, config_kwargs: dict[str, Any]):
        """Test that get_validation_errors reports missing variable configs."""
        lf = logfire.configure(**config_kwargs)
        config = VariablesConfig(variables={})
        var = lf.var(name='missing_var', default='default', type=str)
        errors = config.get_validation_errors([var])
        assert 'missing_var' in errors
        assert None in errors['missing_var']
        assert 'No config for variable' in str(errors['missing_var'][None])

    def test_get_validation_errors_invalid_type(self, config_kwargs: dict[str, Any]):
        """Test that get_validation_errors reports type validation errors."""
        lf = logfire.configure(**config_kwargs)
        config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        var = lf.var(name='my_var', default=0, type=int)
        errors = config.get_validation_errors([var])
        assert 'my_var' in errors
        assert 'v1' in errors['my_var']

    def test_from_variables(self, config_kwargs: dict[str, Any]):
        """Test that from_variables creates minimal configs from Variable instances."""
        lf = logfire.configure(**config_kwargs)
        var1 = lf.var(name='str_var', default='hello', type=str, description='A string variable')
        var2 = lf.var(name='int_var', default=42, type=int)

        config = VariablesConfig.from_variables([var1, var2])

        # Check that configs were created for both variables
        assert 'str_var' in config.variables
        assert 'int_var' in config.variables

        # Check that the configs have the right structure
        str_config = config.variables['str_var']
        assert str_config.name == 'str_var'
        assert str_config.description == 'A string variable'
        assert str_config.labels == {}  # No labels created
        assert str_config.rollout.labels == {}  # Empty rollout
        assert str_config.json_schema is not None
        assert str_config.example == '"hello"'  # Default value as example

        int_config = config.variables['int_var']
        assert int_config.name == 'int_var'
        assert int_config.example == '42'

    def test_from_variables_with_function_default(self, config_kwargs: dict[str, Any]):
        """Test that from_variables handles function defaults (no example)."""
        lf = logfire.configure(**config_kwargs)

        def resolve_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'computed'  # pragma: no cover

        var = lf.var(name='fn_var', default=resolve_default, type=str)

        config = VariablesConfig.from_variables([var])

        fn_config = config.variables['fn_var']
        assert fn_config.example is None  # No example for function defaults

    def test_merge_basic(self):
        """Test that merge combines two configs with other taking precedence."""
        config1 = VariablesConfig(
            variables={
                'var_a': VariableConfig(
                    name='var_a',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value_a1"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value_b1"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        config2 = VariablesConfig(
            variables={
                'var_b': VariableConfig(
                    name='var_b',
                    labels={'v2': LabeledValue(version=1, serialized_value='"value_b2"')},
                    rollout=Rollout(labels={'v2': 1.0}),
                    overrides=[],
                ),
                'var_c': VariableConfig(
                    name='var_c',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value_c1"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )

        merged = config1.merge(config2)

        # Should have all three variables
        assert len(merged.variables) == 3
        assert 'var_a' in merged.variables
        assert 'var_b' in merged.variables
        assert 'var_c' in merged.variables

        # var_b should be from config2 (overwritten)
        assert 'v2' in merged.variables['var_b'].labels
        assert 'v1' not in merged.variables['var_b'].labels


# =============================================================================
# Test NoOpVariableProvider
# =============================================================================


class TestNoOpVariableProvider:
    def test_returns_none(self):
        provider = NoOpVariableProvider()
        result = provider.get_serialized_value('any_variable')
        assert result.value is None
        assert result._reason == 'no_provider'

    def test_with_targeting_key_and_attributes(self):
        provider = NoOpVariableProvider()
        result = provider.get_serialized_value(
            'any_variable',
            targeting_key='user123',
            attributes={'plan': 'enterprise'},
        )
        assert result.value is None

    def test_refresh_does_nothing(self):
        provider = NoOpVariableProvider()
        provider.refresh()  # Should not raise
        provider.refresh(force=True)  # Should not raise

    def test_shutdown_does_nothing(self):
        provider = NoOpVariableProvider()
        provider.shutdown()  # Should not raise


# =============================================================================
# Test ResolvedVariable
# =============================================================================


class TestResolvedVariable:
    def test_basic_details(self):
        details = ResolvedVariable(name='test_var', value='test', _reason='resolved')
        assert details.name == 'test_var'
        assert details.value == 'test'
        assert details.label is None
        assert details.exception is None

    def test_with_label(self):
        details = ResolvedVariable(name='test_var', value='test', label='v1', _reason='resolved')
        assert details.label == 'v1'

    def test_with_exception(self):
        error = ValueError('test error')
        details = ResolvedVariable(name='test_var', value='default', exception=error, _reason='validation_error')
        assert details.exception is error

    def test_context_manager_sets_baggage(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='context_test_var', default='default', type=str)
        details = var.get()

        # Before entering context, check that baggage is not set
        baggage_before = logfire.get_baggage()
        assert 'logfire.variables.context_test_var' not in baggage_before

        # Inside context, baggage should be set
        with details:
            baggage_inside = logfire.get_baggage()
            assert 'logfire.variables.context_test_var' in baggage_inside
            # Value should be '<code_default>' since no label was selected (no config)
            assert baggage_inside['logfire.variables.context_test_var'] == '<code_default>'

        # After exiting context, baggage should be unset
        baggage_after = logfire.get_baggage()
        assert 'logfire.variables.context_test_var' not in baggage_after

    def test_context_manager_sets_label_in_baggage(self, config_kwargs: dict[str, Any]):
        variables_config = VariablesConfig(
            variables={
                'cm_var': VariableConfig(
                    name='cm_var',
                    labels={
                        'my_label': LabeledValue(version=1, serialized_value='"labeled_value"'),
                    },
                    rollout=Rollout(labels={'my_label': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='cm_var', default='default', type=str)
        details = var.get()

        assert details.label == 'my_label'

        with details:
            baggage = logfire.get_baggage()
            assert baggage['logfire.variables.cm_var'] == 'my_label'

    def test_context_manager_returns_self(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='cm_return_test', default='default', type=str)
        details = var.get()

        with details as entered_details:
            assert entered_details is details

    def test_context_manager_nested(self, config_kwargs: dict[str, Any]):
        variables_config = VariablesConfig(
            variables={
                'var_a': VariableConfig(
                    name='var_a',
                    labels={'a1': LabeledValue(version=1, serialized_value='"value_a"')},
                    rollout=Rollout(labels={'a1': 1.0}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    labels={'b1': LabeledValue(version=1, serialized_value='"value_b"')},
                    rollout=Rollout(labels={'b1': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default_a', type=str)
        var_b = lf.var(name='var_b', default='default_b', type=str)

        details_a = var_a.get()
        details_b = var_b.get()

        with details_a:
            baggage = logfire.get_baggage()
            assert 'logfire.variables.var_a' in baggage
            assert 'logfire.variables.var_b' not in baggage

            with details_b:
                baggage = logfire.get_baggage()
                assert 'logfire.variables.var_a' in baggage
                assert 'logfire.variables.var_b' in baggage

            baggage = logfire.get_baggage()
            assert 'logfire.variables.var_a' in baggage
            assert 'logfire.variables.var_b' not in baggage

    def test_context_manager_with_exception(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='exc_test_var', default='default', type=str)
        details = var.get()

        # Ensure the context manager properly cleans up even when an exception is raised
        try:
            with details:
                baggage = logfire.get_baggage()
                assert 'logfire.variables.exc_test_var' in baggage
                raise ValueError('test exception')
        except ValueError:
            pass

        # Baggage should be cleaned up
        baggage = logfire.get_baggage()
        assert 'logfire.variables.exc_test_var' not in baggage


# =============================================================================
# Test LocalVariableProvider
# =============================================================================


class TestLocalVariableProvider:
    @pytest.fixture
    def simple_config(self) -> VariablesConfig:
        return VariablesConfig(
            variables={
                'test_var': VariableConfig(
                    name='test_var',
                    labels={
                        'default': LabeledValue(version=1, serialized_value='"default_value"'),
                        'premium': LabeledValue(version=1, serialized_value='"premium_value"'),
                    },
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='plan', value='enterprise')],
                            rollout=Rollout(labels={'premium': 1.0}),
                        ),
                    ],
                ),
            }
        )

    def test_get_serialized_value_basic(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(simple_config)
        result = provider.get_serialized_value('test_var')
        assert result.value == '"default_value"'
        assert result.label == 'default'
        assert result._reason == 'resolved'

    def test_get_serialized_value_with_override(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(simple_config)
        result = provider.get_serialized_value(
            'test_var',
            attributes={'plan': 'enterprise'},
        )
        assert result.value == '"premium_value"'
        assert result.label == 'premium'

    def test_get_serialized_value_unrecognized(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(simple_config)
        result = provider.get_serialized_value('unknown_var')
        assert result.value is None
        assert result._reason == 'unrecognized_variable'

    def test_rollout_returns_none(self):
        config = VariablesConfig(
            variables={
                'partial_var': VariableConfig(
                    name='partial_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 0.0}),  # 0% chance
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(config)
        result = provider.get_serialized_value('partial_var')
        assert result.value is None
        assert result._reason == 'resolved'


# =============================================================================
# Test LogfireRemoteVariableProvider (using requests-mock)
# =============================================================================


REMOTE_BASE_URL = 'http://localhost:8000/'
REMOTE_TOKEN = 'pylf_v1_local_test_token'


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestLogfireRemoteVariableProvider:
    def test_get_serialized_value_basic(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'test_var': {
                        'name': 'test_var',
                        'labels': {
                            'default': {
                                'version': 1,
                                'serialized_value': '"remote_value"',
                                'description': None,
                            }
                        },
                        'rollout': {'labels': {'default': 1.0}},
                        'overrides': [],
                        'json_schema': {'type': 'string'},
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                result = provider.get_serialized_value('test_var')
                assert result.value == '"remote_value"'
                assert result.label == 'default'
            finally:
                provider.shutdown()

    def test_get_serialized_value_missing_config_no_block(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # Without blocking, config might not be fetched yet
                result = provider.get_serialized_value('test_var')
                # Should return missing_config if not fetched
                assert result._reason in ('missing_config', 'resolved', 'unrecognized_variable')
            finally:
                provider.shutdown()

    def test_unrecognized_variable(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'other_var': {
                        'name': 'other_var',
                        'labels': {
                            'default': {
                                'version': 1,
                                'serialized_value': '"value"',
                            }
                        },
                        'rollout': {'labels': {'default': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                result = provider.get_serialized_value('nonexistent_var')
                assert result.value is None
                assert result._reason == 'unrecognized_variable'
            finally:
                provider.shutdown()

    def test_shutdown_idempotent(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            provider.shutdown()
            provider.shutdown()  # Should not raise

    def test_shutdown_passes_timeout_to_thread_joins(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            # Replace threads with mocks so we can inspect join() calls
            mock_worker = unittest.mock.MagicMock()
            mock_sse = unittest.mock.MagicMock()
            provider._worker_thread = mock_worker
            provider._sse_thread = mock_sse

            provider.shutdown(timeout_millis=10000)

            # 70% of 10000ms = 7000ms = 7.0s for worker
            mock_worker.join.assert_called_once_with(timeout=7.0)
            # 30% of 10000ms = 3000ms = 3.0s for SSE
            mock_sse.join.assert_called_once_with(timeout=3.0)

    def test_refresh_with_force(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                provider.refresh(force=True)
                result = provider.get_serialized_value('test_var')
                assert result._reason == 'unrecognized_variable'
            finally:
                provider.shutdown()

    def test_rollout_returns_none_label(self) -> None:
        """Test case where rollout returns None (no label selected)."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'partial_var': {
                        'name': 'partial_var',
                        'labels': {
                            'v1': {
                                'version': 1,
                                'serialized_value': '"value"',
                            }
                        },
                        # 0% rollout means no label is ever selected
                        'rollout': {'labels': {'v1': 0.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                result = provider.get_serialized_value('partial_var')
                assert result.value is None
                assert result._reason == 'resolved'
            finally:
                provider.shutdown()


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestLogfireRemoteVariableProviderTimeout:
    def test_refresh_passes_timeout_default(self) -> None:
        """refresh() should pass the default timeout=(10, 10) to Session.get."""
        request_mocker = requests_mock_module.Mocker()
        adapter = request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                provider.refresh(force=True)
                assert adapter.call_count == 1
                assert adapter.last_request is not None
                # Verify the timeout was passed by checking the provider's stored value
                assert provider._timeout == (10, 10)
            finally:
                provider.shutdown()

    def test_refresh_passes_custom_timeout(self) -> None:
        """refresh() should pass a custom timeout to Session.get."""
        request_mocker = requests_mock_module.Mocker()
        adapter = request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                    timeout=(5, 15),
                ),
            )
            try:
                provider.refresh(force=True)
                assert adapter.call_count == 1
                assert provider._timeout == (5, 15)
            finally:
                provider.shutdown()

    def test_refresh_timeout_passed_to_session_get(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that the timeout kwarg is actually forwarded to Session.get."""
        captured_kwargs: dict[str, Any] = {}
        original_get = Session.get

        def patched_get(self: Any, url: Any, **kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return original_get(self, url, **kwargs)

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                    timeout=(3, 7),
                ),
            )
            try:
                monkeypatch.setattr(Session, 'get', patched_get)
                provider.refresh(force=True)
                assert captured_kwargs['timeout'] == (3, 7)
            finally:
                provider.shutdown()

    def test_blocking_first_resolve_uses_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The first-resolve blocking path should also use the timeout."""
        captured_kwargs: dict[str, Any] = {}
        original_get = Session.get

        def patched_get(self: Any, url: Any, **kwargs: Any) -> Any:
            captured_kwargs.update(kwargs)
            return original_get(self, url, **kwargs)

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                    timeout=(2, 5),
                ),
            )
            try:
                monkeypatch.setattr(Session, 'get', patched_get)
                # get_serialized_value triggers blocking refresh on first call
                provider.get_serialized_value('some_var')
                assert captured_kwargs['timeout'] == (2, 5)
            finally:
                provider.shutdown()


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestLogfireRemoteVariableProviderErrors:
    def test_handles_unexpected_response(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            status_code=500,
            json={'error': 'Internal Server Error'},
        )
        with warnings.catch_warnings(), request_mocker:
            warnings.simplefilter('ignore', RuntimeWarning)
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # The mock returns an error, so config should not be set
                result = provider.get_serialized_value('test_var')
                assert result._reason == 'missing_config'
            finally:
                provider.shutdown()

    def test_handles_validation_error(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'invalid_field': 'this is not valid VariablesConfig data'},
        )
        with warnings.catch_warnings(), request_mocker:
            warnings.simplefilter('ignore', RuntimeWarning)
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # The mock returns invalid data, so validation error happens
                result = provider.get_serialized_value('test_var')
                assert result._reason == 'missing_config'
            finally:
                provider.shutdown()


# =============================================================================
# Test LogfireRemoteVariableProvider start() method
# =============================================================================


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestLogfireRemoteVariableProviderStart:
    """Tests for the start() method of LogfireRemoteVariableProvider."""

    def test_start_called_twice_is_noop(self) -> None:
        """Calling start() twice should be a no-op (early return)."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # First start
                provider.start(None)
                assert provider._started is True
                worker_thread = provider._worker_thread

                # Second start should be a no-op
                provider.start(None)
                assert provider._worker_thread is worker_thread  # Same thread
            finally:
                provider.shutdown()

    def test_start_with_logfire_instance(self, config_kwargs: dict[str, Any]) -> None:
        """start() with a logfire instance should set up error logging via logfire."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # Create a logfire instance
                lf = logfire.configure(**config_kwargs)

                # Start with the logfire instance
                provider.start(lf)

                # Verify logfire instance is set
                assert provider._logfire is not None
                assert provider._started is True
            finally:
                provider.shutdown()

    def test_error_logged_via_logfire_when_instrumented(self, config_kwargs: dict[str, Any]) -> None:
        """When started with a logfire instance, _log_error should call logfire.error()."""
        from unittest.mock import MagicMock

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                # Create a logfire instance and start the provider
                lf = logfire.configure(**config_kwargs)
                provider.start(lf)

                # Mock the logfire error method
                mock_error = MagicMock()
                provider._logfire.error = mock_error  # type: ignore

                # Directly call _log_error to test the logfire.error path
                test_exc = ValueError('Test error')
                provider._log_error('Test message', test_exc)

                # Verify logfire.error was called
                mock_error.assert_called_once()
                call_args = mock_error.call_args
                assert call_args[0][0] == '{message}: {error}'
                assert call_args[1]['message'] == 'Test message'
                assert call_args[1]['error'] == 'Test error'
                assert call_args[1]['_exc_info'] is test_exc
            finally:
                provider.shutdown()

    def test_refresh_skips_when_recently_fetched(self) -> None:
        """refresh() should skip if we've fetched recently and force=False."""
        request_mocker = requests_mock_module.Mocker()
        adapter = request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),  # Long polling interval
                ),
            )
            try:
                assert adapter.call_count == 0
                provider.start(None)
                # Starting should result in a call in a background thread, so we need to wait for it
                start_time = time.time()
                while adapter.call_count < 1:
                    if time.time() - start_time > 5:  # pragma: no cover
                        raise AssertionError(f'Timed out waiting for call_count to reach 1, got {adapter.call_count}')
                    # Need the below or it can be flaky
                    time.sleep(0.01)  # pragma: no cover
                assert adapter.call_count == 1

                # First refresh should make a request
                provider.refresh(force=True)
                assert adapter.call_count == 2

                # Second refresh without force should skip (recently fetched)
                provider.refresh(force=False)
                assert adapter.call_count == 2  # No additional request

                # Third refresh with force should make a request
                provider.refresh(force=True)
                assert adapter.call_count == 3
            finally:
                provider.shutdown()


# =============================================================================
# Test API Key Support
# =============================================================================


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestApiKeySupport:
    def test_api_key_in_config(self) -> None:
        """Test that api_key can be specified in VariablesOptions."""
        api_key = 'test_api_key_12345'
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'test_var': {
                        'name': 'test_var',
                        'labels': {
                            'default': {
                                'version': 1,
                                'serialized_value': '"api_key_value"',
                                'description': None,
                            }
                        },
                        'rollout': {'labels': {'default': 1.0}},
                        'overrides': [],
                        'json_schema': {'type': 'string'},
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url='http://localhost:8000/',
                token=api_key,
                options=VariablesOptions(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                    api_key=api_key,
                ),
            )
            try:
                result = provider.get_serialized_value('test_var')
                assert result.value == '"api_key_value"'
                assert result.label == 'default'
                # Verify that the api_key was used in the request header
                assert request_mocker.last_request is not None
                assert request_mocker.last_request.headers['Authorization'] == f'bearer {api_key}'
            finally:
                provider.shutdown()

    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that api_key can be loaded from LOGFIRE_API_KEY environment variable."""
        from logfire._internal.config_params import ParamManager

        api_key = 'env_api_key_67890'
        monkeypatch.setenv('LOGFIRE_API_KEY', api_key)

        param_manager = ParamManager.create()
        loaded_key = param_manager.load_param('api_key')
        assert loaded_key == api_key


# =============================================================================
# Test Variable
# =============================================================================


class TestVariable:
    @pytest.fixture
    def variables_config(self) -> VariablesConfig:
        return VariablesConfig(
            variables={
                'string_var': VariableConfig(
                    name='string_var',
                    labels={
                        'default': LabeledValue(version=1, serialized_value='"hello"'),
                        'alt': LabeledValue(version=1, serialized_value='"world"'),
                    },
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='use_alt', value=True)],
                            rollout=Rollout(labels={'alt': 1.0}),
                        ),
                    ],
                ),
                'int_var': VariableConfig(
                    name='int_var',
                    labels={'default': LabeledValue(version=1, serialized_value='42')},
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[],
                ),
                'model_var': VariableConfig(
                    name='model_var',
                    labels={
                        'default': LabeledValue(
                            version=1,
                            serialized_value='{"name": "test", "value": 123}',
                        )
                    },
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[],
                ),
                'invalid_var': VariableConfig(
                    name='invalid_var',
                    labels={'default': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[],
                ),
            }
        )

    def test_get_string_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        details = var.get()
        assert details.value == 'hello'

    def test_get_int_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='int_var', default=0, type=int)
        details = var.get()
        assert details.value == 42

    def test_get_model_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        class MyModel(BaseModel):
            name: str
            value: int

        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='model_var', default=MyModel(name='default', value=0), type=MyModel)
        details = var.get()
        assert details.value.name == 'test'
        assert details.value.value == 123

    def test_get_with_attributes(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        # Without override condition
        assert var.get().value == 'hello'

        # With override condition
        assert var.get(attributes={'use_alt': True}).value == 'world'

    def test_get_details(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        details = var.get()
        assert details.value == 'hello'
        assert details.label == 'default'
        assert details.exception is None

    def test_get_details_with_validation_error(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='invalid_var', default=999, type=int)
        details = var.get()
        # Falls back to default when validation fails
        assert details.value == 999
        assert details.exception is not None
        assert details._reason == 'validation_error'

    def test_get_uses_default_when_no_config(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='unconfigured', default='my_default', type=str)
        value = var.get().value
        assert value == 'my_default'

    def test_override_context_manager(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        assert var.get().value == 'hello'

        with var.override('overridden'):
            assert var.get().value == 'overridden'

        assert var.get().value == 'hello'

    def test_override_nested(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        with var.override('outer'):
            assert var.get().value == 'outer'
            with var.override('inner'):
                assert var.get().value == 'inner'
            assert var.get().value == 'outer'

    def test_override_with_function(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        def resolve_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            if attributes and attributes.get('mode') == 'creative':
                return 'creative_value'
            return 'default_fn_value'

        with var.override(resolve_fn):
            assert var.get().value == 'default_fn_value'
            assert var.get(attributes={'mode': 'creative'}).value == 'creative_value'

    def test_default_as_function(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        def resolve_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            if targeting_key:
                return f'default_for_{targeting_key}'
            return 'generic_default'

        var = lf.var(name='with_fn_default', default=resolve_default, type=str)
        assert var.get().value == 'generic_default'
        assert var.get(targeting_key='user123').value == 'default_for_user123'

    def test_refresh_sync(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        var.refresh_sync()  # Should not raise

    @pytest.mark.anyio
    async def test_refresh_async(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        await var.refresh()  # Should not raise

    def test_get_creates_span_when_instrumented(
        self, config_kwargs: dict[str, Any], variables_config: VariablesConfig, exporter: TestExporter
    ):
        """Test that var.get() creates a span when instrument=True."""
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        exporter.clear()  # Clear any spans from configure

        details = var.get()

        # Verify the variable was resolved correctly
        assert details.value == 'hello'
        assert details.label == 'default'

        # Verify a "Resolve variable string_var" span was created
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable string_var']
        assert len(resolve_spans) >= 1
        span = resolve_spans[-1]  # Get the most recent one
        # Verify span attributes
        attrs = dict(span.attributes or {})
        assert attrs.get('name') == 'string_var'
        # Value is JSON serialized for OTel-safe span attributes
        assert attrs.get('value') == '"hello"'
        assert attrs.get('label') == 'default'

    def test_get_records_exception_on_span_when_validation_error(
        self, config_kwargs: dict[str, Any], variables_config: VariablesConfig, exporter: TestExporter
    ):
        """Test that validation errors are recorded on the span when instrument=True."""
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='invalid_var', default=999, type=int)
        exporter.clear()  # Clear any spans from configure

        details = var.get()

        # Verify fallback to default
        assert details.value == 999
        assert details.exception is not None

        # Verify the span was created and has the exception recorded
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable invalid_var']
        assert len(resolve_spans) >= 1
        span = resolve_spans[-1]  # Get the most recent one
        # Check that an exception event was recorded
        events = span.events or []
        exception_events = [e for e in events if e.name == 'exception']
        assert len(exception_events) == 1

    def test_get_no_span_when_not_instrumented(
        self, config_kwargs: dict[str, Any], variables_config: VariablesConfig, exporter: TestExporter
    ):
        """Test that var.get() does NOT create a span when instrument=False."""
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=False)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        exporter.clear()  # Clear any spans from configure

        details = var.get()

        # Verify the variable was resolved correctly
        assert details.value == 'hello'
        assert details.label == 'default'

        # Verify NO "Resolve variable" span was created
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name.startswith('Resolve variable')]
        assert len(resolve_spans) == 0


# =============================================================================
# Test targeting_context
# =============================================================================


class TestTargetingContext:
    """Tests for the targeting_context context manager."""

    @pytest.fixture
    def rollout_config(self) -> VariablesConfig:
        """Config with deterministic rollout based on targeting_key."""
        return VariablesConfig(
            variables={
                'var_a': VariableConfig(
                    name='var_a',
                    labels={
                        'v1': LabeledValue(version=1, serialized_value='"value_1"'),
                        'v2': LabeledValue(version=1, serialized_value='"value_2"'),
                    },
                    # 50/50 split - targeting_key determines which label
                    rollout=Rollout(labels={'v1': 0.5, 'v2': 0.5}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    labels={
                        'v1': LabeledValue(version=1, serialized_value='"b_value_1"'),
                        'v2': LabeledValue(version=1, serialized_value='"b_value_2"'),
                    },
                    rollout=Rollout(labels={'v1': 0.5, 'v2': 0.5}),
                    overrides=[],
                ),
            }
        )

    def test_targeting_context_default_for_all_variables(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """targeting_context without variables sets targeting for all variables."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)
        var_b = lf.var(name='var_b', default='default', type=str)

        # Without targeting_context, each call may get different results (trace-based or random)
        # With targeting_context, both variables use the same targeting_key
        with targeting_context('user123'):
            result_a = var_a.get()
            result_b = var_b.get()

        # Verify targeting_key was used (results should be consistent for same key)
        with targeting_context('user123'):
            assert var_a.get().value == result_a.value
            assert var_b.get().value == result_b.value

    def test_targeting_context_for_specific_variables(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """targeting_context with variables list only affects those variables."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)

        # Set targeting only for var_a
        with targeting_context('user123', variables=[var_a]):
            # var_a should use the targeting_key
            result_a_1 = var_a.get()
            result_a_2 = var_a.get()
            # Should be consistent
            assert result_a_1.value == result_a_2.value

    def test_targeting_context_nested_specific_wins_over_default(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """Variable-specific targeting wins over default, regardless of nesting order."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)
        var_b = lf.var(name='var_b', default='default', type=str)

        # Get expected results for each targeting_key
        with targeting_context('user_default'):
            expected_b_default = var_b.get().value
        with targeting_context('org456'):
            expected_specific = var_a.get().value

        # Nested: default first, then specific
        with targeting_context('user_default'):
            with targeting_context('org456', variables=[var_a]):
                # var_a uses specific targeting (org456)
                assert var_a.get().value == expected_specific
                # var_b uses default targeting (user_default)
                assert var_b.get().value == expected_b_default

    def test_targeting_context_reverse_nesting_order(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """Specific targeting wins even when set before default in nesting."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)
        var_b = lf.var(name='var_b', default='default', type=str)

        # Get expected results
        with targeting_context('org456'):
            expected_specific = var_a.get().value
        with targeting_context('user_default'):
            expected_default = var_b.get().value

        # Reverse nesting: specific first, then default
        with targeting_context('org456', variables=[var_a]):
            with targeting_context('user_default'):
                # var_a still uses specific targeting (org456)
                assert var_a.get().value == expected_specific
                # var_b uses default targeting (user_default)
                assert var_b.get().value == expected_default

    def test_targeting_context_call_site_wins(self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig):
        """Call-site targeting_key overrides contextvar targeting."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)

        # Get expected result for call-site key
        result_for_explicit = var_a.get(targeting_key='explicit_key').value

        with targeting_context('context_key'):
            # Call-site targeting_key should win
            assert var_a.get(targeting_key='explicit_key').value == result_for_explicit

    def test_targeting_context_multiple_specific_variables(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """Multiple variables can have specific targeting set."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)
        var_b = lf.var(name='var_b', default='default', type=str)

        # Get expected results
        with targeting_context('key_for_both'):
            expected_a = var_a.get().value
            expected_b = var_b.get().value

        # Set same targeting for both variables explicitly
        with targeting_context('key_for_both', variables=[var_a, var_b]):
            assert var_a.get().value == expected_a
            assert var_b.get().value == expected_b

    def test_targeting_context_different_keys_for_different_variables(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """Different variables can have different targeting keys."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)

        var_a = lf.var(name='var_a', default='default', type=str)
        var_b = lf.var(name='var_b', default='default', type=str)

        # Get expected results
        with targeting_context('key_a'):
            expected_a = var_a.get().value
        with targeting_context('key_b'):
            expected_b = var_b.get().value

        # Nest specific contexts for different variables
        with targeting_context('key_a', variables=[var_a]):
            with targeting_context('key_b', variables=[var_b]):
                assert var_a.get().value == expected_a
                assert var_b.get().value == expected_b

    def test_targeting_context_resets_after_exit(self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig):
        """Targeting context is properly reset after exiting the context manager."""
        from logfire.variables.variable import _get_contextvar_targeting_key, targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        logfire.configure(**config_kwargs)

        # No context set initially
        assert _get_contextvar_targeting_key('var_a') is None

        with targeting_context('user123'):
            assert _get_contextvar_targeting_key('var_a') == 'user123'

        # Context is reset after exit
        assert _get_contextvar_targeting_key('var_a') is None

    def test_targeting_context_specific_resets_after_exit(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """Variable-specific targeting is properly reset after exiting."""
        from logfire.variables.variable import _get_contextvar_targeting_key, targeting_context

        config_kwargs['variables'] = LocalVariablesOptions(config=rollout_config)
        lf = logfire.configure(**config_kwargs)
        var_a = lf.var(name='var_a', default='default', type=str)

        with targeting_context('default_key'):
            assert _get_contextvar_targeting_key('var_a') == 'default_key'

            with targeting_context('specific_key', variables=[var_a]):
                assert _get_contextvar_targeting_key('var_a') == 'specific_key'
                # Other variables still get default
                assert _get_contextvar_targeting_key('var_b') == 'default_key'

            # After exiting specific context, var_a goes back to default
            assert _get_contextvar_targeting_key('var_a') == 'default_key'

        # After exiting all contexts
        assert _get_contextvar_targeting_key('var_a') is None


# =============================================================================
# Test Variable with Baggage and Resource Attributes
# =============================================================================


class TestVariableContextEnrichment:
    @pytest.fixture
    def config_with_targeting(self) -> VariablesConfig:
        return VariablesConfig(
            variables={
                'targeted_var': VariableConfig(
                    name='targeted_var',
                    labels={
                        'default': LabeledValue(version=1, serialized_value='"default"'),
                        'premium': LabeledValue(version=1, serialized_value='"premium"'),
                    },
                    rollout=Rollout(labels={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='plan', value='enterprise')],
                            rollout=Rollout(labels={'premium': 1.0}),
                        ),
                    ],
                ),
            }
        )

    def test_baggage_included_in_resolution(
        self, config_kwargs: dict[str, Any], config_with_targeting: VariablesConfig
    ):
        config_kwargs['variables'] = LocalVariablesOptions(
            config=config_with_targeting,
            include_baggage_in_context=True,
        )
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='targeted_var', default='fallback', type=str)

        # Without baggage
        assert var.get().value == 'default'

        # With baggage
        with logfire.set_baggage(plan='enterprise'):
            assert var.get().value == 'premium'

    def test_baggage_can_be_disabled(self, config_kwargs: dict[str, Any], config_with_targeting: VariablesConfig):
        config_kwargs['variables'] = LocalVariablesOptions(
            config=config_with_targeting,
            include_baggage_in_context=False,
        )
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='targeted_var', default='fallback', type=str)

        # With baggage but disabled
        with logfire.set_baggage(plan='enterprise'):
            # Should NOT match override since baggage is disabled
            assert var.get().value == 'default'

    def test_resource_attributes_can_be_disabled(
        self, config_kwargs: dict[str, Any], config_with_targeting: VariablesConfig
    ):
        config_kwargs['variables'] = LocalVariablesOptions(
            config=config_with_targeting,
            include_resource_attributes_in_context=False,
        )
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='targeted_var', default='fallback', type=str)
        # Just verify it works with this setting
        assert var.get().value == 'default'


# =============================================================================
# Test is_resolve_function
# =============================================================================


class TestIsResolveFunction:
    def test_valid_resolve_function(self):
        def valid_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'value'  # pragma: no cover

        assert is_resolve_function(valid_fn) is True

    def test_different_param_names(self):
        """A callable with 2 positional params should be detected regardless of parameter names."""

        def fn_with_different_names(key: str | None, attrs: Mapping[str, Any] | None) -> str:
            return 'value'  # pragma: no cover

        assert is_resolve_function(fn_with_different_names) is True

    def test_wrong_param_count(self):
        def wrong_count(targeting_key: str | None) -> str:
            return 'value'  # pragma: no cover

        assert is_resolve_function(wrong_count) is False

    def test_not_callable(self):
        assert is_resolve_function('not a function') is False
        assert is_resolve_function(42) is False


# =============================================================================
# Test __init__.py lazy imports
# =============================================================================


class TestLazyImports:
    def test_all_exports_accessible(self):
        from logfire import variables

        # All items in __all__ should be accessible
        for name in variables.__all__:
            assert hasattr(variables, name)
            getattr(variables, name)  # Should not raise

    def test_attribute_error_for_unknown(self):
        from logfire import variables

        with pytest.raises(AttributeError, match="has no attribute 'NonExistent'"):
            variables.NonExistent


# =============================================================================
# Test Integration with logfire.var()
# =============================================================================


class TestLogfireVarIntegration:
    def test_var_with_implicit_type(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = LocalVariablesOptions(
            config=VariablesConfig(
                variables={
                    'default_var': VariableConfig(
                        name='default_var',
                        labels={'v1': LabeledValue(version=1, serialized_value='"string_value"')},
                        rollout=Rollout(labels={'v1': 1.0}),
                        overrides=[],
                    ),
                }
            )
        )
        lf = logfire.configure(**config_kwargs)

        # not specifying type of default uses the type of the default
        var = lf.var(name='default_var', default='default')
        assert var.get().value == 'string_value'

    def test_exception_handling_in_get_details(self, config_kwargs: dict[str, Any]):
        # Create a provider that raises an exception
        class FailingProvider(VariableProvider):
            def get_serialized_value(
                self,
                variable_name: str,
                targeting_key: str | None = None,
                attributes: Mapping[str, Any] | None = None,
            ) -> ResolvedVariable[str | None]:
                raise RuntimeError('Provider failed!')

        lf = logfire.configure(variables=FailingProvider())

        var = lf.var(name='failing_var', default='fallback', type=str)
        details = var.get()
        assert details.value == 'fallback'
        assert details._reason == 'other_error'
        assert isinstance(details.exception, RuntimeError)

    def test_variables_build_config(self, config_kwargs: dict[str, Any]):
        """Test that variables_build_config on a Logfire instance delegates to VariablesConfig.from_variables."""
        lf = logfire.configure(**config_kwargs)

        var1 = lf.var(name='build_test_a', default=42, type=int)
        var2 = lf.var(name='build_test_b', default='hello', type=str)

        config = lf.variables_build_config(variables=[var1, var2])

        assert set(config.variables.keys()) == {'build_test_a', 'build_test_b'}
        assert config.variables['build_test_a'].example == '42'
        assert config.variables['build_test_b'].example == '"hello"'
        assert config.variables['build_test_a'].json_schema == {'type': 'integer'}
        assert config.variables['build_test_b'].json_schema == {'type': 'string'}


# =============================================================================
# Test LocalVariableProvider Write Operations
# =============================================================================


class TestLocalVariableProviderWriteOperations:
    @pytest.fixture
    def empty_config(self) -> VariablesConfig:
        return VariablesConfig(variables={})

    @pytest.fixture
    def config_with_var(self) -> VariablesConfig:
        return VariablesConfig(
            variables={
                'existing_var': VariableConfig(
                    name='existing_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )

    def test_get_variable_config_existing(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        result = provider.get_variable_config('existing_var')
        assert result is not None
        assert result.name == 'existing_var'

    def test_get_variable_config_missing(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        result = provider.get_variable_config('nonexistent')
        assert result is None

    def test_get_all_variables_config(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        result = provider.get_all_variables_config()
        assert 'existing_var' in result.variables

    def test_create_variable_success(self, empty_config: VariablesConfig):
        provider = LocalVariableProvider(empty_config)
        new_config = VariableConfig(
            name='new_var',
            labels={'v1': LabeledValue(version=1, serialized_value='"new_value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        result = provider.create_variable(new_config)
        assert result.name == 'new_var'
        assert 'new_var' in provider._config.variables

    def test_create_variable_already_exists(self, config_with_var: VariablesConfig):
        from logfire.variables.abstract import VariableAlreadyExistsError

        provider = LocalVariableProvider(config_with_var)
        duplicate_config = VariableConfig(
            name='existing_var',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        with pytest.raises(VariableAlreadyExistsError, match="Variable 'existing_var' already exists"):
            provider.create_variable(duplicate_config)

    def test_update_variable_success(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        updated_config = VariableConfig(
            name='existing_var',
            labels={'v2': LabeledValue(version=1, serialized_value='"updated_value"')},
            rollout=Rollout(labels={'v2': 1.0}),
            overrides=[],
        )
        result = provider.update_variable('existing_var', updated_config)
        v2 = result.labels['v2']
        assert isinstance(v2, LabeledValue)
        assert v2.serialized_value == '"updated_value"'

    def test_update_variable_not_found(self, empty_config: VariablesConfig):
        from logfire.variables.abstract import VariableNotFoundError

        provider = LocalVariableProvider(empty_config)
        new_config = VariableConfig(
            name='nonexistent',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        with pytest.raises(VariableNotFoundError, match="Variable 'nonexistent' not found"):
            provider.update_variable('nonexistent', new_config)

    def test_delete_variable_success(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        provider.delete_variable('existing_var')
        assert 'existing_var' not in provider._config.variables

    def test_delete_variable_not_found(self, empty_config: VariablesConfig):
        from logfire.variables.abstract import VariableNotFoundError

        provider = LocalVariableProvider(empty_config)
        with pytest.raises(VariableNotFoundError, match="Variable 'nonexistent' not found"):
            provider.delete_variable('nonexistent')


# =============================================================================
# Test LogfireRemoteVariableProvider Write Operations
# =============================================================================


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestLogfireRemoteVariableProviderWriteOperations:
    def test_get_variable_config_existing(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'my_var': {
                        'name': 'my_var',
                        'labels': {'v1': {'version': 1, 'serialized_value': '"value"'}},
                        'rollout': {'labels': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
            )
            try:
                provider.refresh(force=True)
                result = provider.get_variable_config('my_var')
                assert result is not None
                assert result.name == 'my_var'
            finally:
                provider.shutdown()

    def test_get_variable_config_missing_when_no_config(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        # First call to get variables returns empty, so _config stays None
        request_mocker.get('http://localhost:8000/v1/variables/', status_code=500)
        with warnings.catch_warnings(), request_mocker:
            warnings.simplefilter('ignore', RuntimeWarning)
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
            )
            try:
                result = provider.get_variable_config('my_var')
                assert result is None
            finally:
                provider.shutdown()

    def test_get_all_variables_config_when_none(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', status_code=500)
        with warnings.catch_warnings(), request_mocker:
            warnings.simplefilter('ignore', RuntimeWarning)
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
            )
            try:
                result = provider.get_all_variables_config()
                assert result.variables == {}
            finally:
                provider.shutdown()

    def test_get_all_variables_config_with_data(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'my_var': {
                        'name': 'my_var',
                        'labels': {'v1': {'version': 1, 'serialized_value': '"value"'}},
                        'rollout': {'labels': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
            )
            try:
                provider.refresh(force=True)
                result = provider.get_all_variables_config()
                assert 'my_var' in result.variables
            finally:
                provider.shutdown()

    def test_create_variable_success(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'new_var'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    description='Test variable',
                    json_schema={'type': 'string'},
                )
                result = provider.create_variable(config)
                assert result.name == 'new_var'
            finally:
                provider.shutdown()

    def test_create_variable_with_aliases_and_example(self) -> None:
        """Test creating a variable with aliases and example fields."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        post_adapter = request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'new_var'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    description='Test variable',
                    json_schema={'type': 'string'},
                    aliases=['old_name', 'legacy_name'],
                    example='"example_value"',
                )
                result = provider.create_variable(config)
                assert result.name == 'new_var'

                # Verify the request body included aliases and example
                assert post_adapter.last_request is not None
                request_body = post_adapter.last_request.json()
                assert request_body['aliases'] == ['old_name', 'legacy_name']
                assert request_body['example'] == '"example_value"'
            finally:
                provider.shutdown()

    def test_create_variable_already_exists(self) -> None:
        from logfire.variables.abstract import VariableAlreadyExistsError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variables/', status_code=409, json={'error': 'Conflict'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='existing_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                )
                with pytest.raises(VariableAlreadyExistsError, match="Variable 'existing_var' already exists"):
                    provider.create_variable(config)
            finally:
                provider.shutdown()

    def test_create_variable_api_error(self) -> None:
        from logfire.variables.abstract import VariableWriteError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variables/', status_code=500, json={'error': 'Server error'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                )
                with pytest.raises(VariableWriteError, match='Failed to create variable'):
                    provider.create_variable(config)
            finally:
                provider.shutdown()

    def test_update_variable_success(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.put('http://localhost:8000/v1/variables/my_var/', json={'name': 'my_var'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='my_var',
                    labels={'v2': LabeledValue(version=1, serialized_value='"updated"')},
                    rollout=Rollout(labels={'v2': 1.0}),
                    overrides=[],
                )
                result = provider.update_variable('my_var', config)
                assert result.name == 'my_var'
            finally:
                provider.shutdown()

    def test_update_variable_not_found(self) -> None:
        from logfire.variables.abstract import VariableNotFoundError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.put('http://localhost:8000/v1/variables/nonexistent/', status_code=404)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='nonexistent',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                )
                with pytest.raises(VariableNotFoundError, match="Variable 'nonexistent' not found"):
                    provider.update_variable('nonexistent', config)
            finally:
                provider.shutdown()

    def test_update_variable_api_error(self) -> None:
        from logfire.variables.abstract import VariableWriteError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.put('http://localhost:8000/v1/variables/my_var/', status_code=500)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                )
                with pytest.raises(VariableWriteError, match='Failed to update variable'):
                    provider.update_variable('my_var', config)
            finally:
                provider.shutdown()

    def test_delete_variable_success(self) -> None:
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.delete('http://localhost:8000/v1/variables/my_var/', status_code=204)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                provider.delete_variable('my_var')  # Should not raise
            finally:
                provider.shutdown()

    def test_delete_variable_not_found(self) -> None:
        from logfire.variables.abstract import VariableNotFoundError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.delete('http://localhost:8000/v1/variables/nonexistent/', status_code=404)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                with pytest.raises(VariableNotFoundError, match="Variable 'nonexistent' not found"):
                    provider.delete_variable('nonexistent')
            finally:
                provider.shutdown()

    def test_delete_variable_api_error(self) -> None:
        from logfire.variables.abstract import VariableWriteError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.delete('http://localhost:8000/v1/variables/my_var/', status_code=500)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                with pytest.raises(VariableWriteError, match='Failed to delete variable'):
                    provider.delete_variable('my_var')
            finally:
                provider.shutdown()

    def test_config_to_api_body_with_overrides(self) -> None:
        """Test _config_to_api_body with various condition types."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'test_var'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                ValueEquals(attribute='attr1', value='val1'),
                                ValueIsIn(attribute='attr2', values=['a', 'b']),
                                ValueMatchesRegex(attribute='attr3', pattern=r'test.*'),
                            ],
                            rollout=Rollout(labels={'v1': 1.0}),
                        )
                    ],
                    description='Test description',
                    json_schema={'type': 'string'},
                )
                provider.create_variable(config)

                # Find the POST request
                post_request = None
                for req in request_mocker.request_history:  # pragma: no branch
                    if req.method == 'POST':  # pragma: no branch
                        post_request = req
                        break

                assert post_request is not None
                body = post_request.json()
                assert body['name'] == 'test_var'
                assert body['description'] == 'Test description'
                assert body['json_schema'] == {'type': 'string'}
                assert 'overrides' in body
                assert len(body['overrides']) == 1
            finally:
                provider.shutdown()

    def test_config_to_api_body_with_key_conditions(self) -> None:
        """Test _config_to_api_body with KeyIsPresent/KeyIsNotPresent conditions."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'test_var'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                KeyIsPresent(attribute='must_exist'),
                                KeyIsNotPresent(attribute='must_not_exist'),
                            ],
                            rollout=Rollout(labels={'v1': 1.0}),
                        )
                    ],
                )
                provider.create_variable(config)

                # Find the POST request
                post_request = None
                for req in request_mocker.request_history:  # pragma: no branch
                    if req.method == 'POST':  # pragma: no branch
                        post_request = req
                        break

                assert post_request is not None
                body = post_request.json()
                assert 'overrides' in body
                # Check that key conditions are serialized correctly (no value/values/pattern)
                conditions = body['overrides'][0]['conditions']
                assert len(conditions) == 2
                assert conditions[0]['kind'] == 'key-is-present'
                assert conditions[1]['kind'] == 'key-is-not-present'
            finally:
                provider.shutdown()


# =============================================================================
# Test VariablesConfig Alias Cycle Detection
# =============================================================================


class TestVariablesConfigAliases:
    def test_alias_resolution_success(self):
        """Test that aliases resolve correctly when defined on VariableConfig."""
        config = VariablesConfig(
            variables={
                'new_name': VariableConfig(
                    name='new_name',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    aliases=['old_name'],  # Aliases are now defined on each variable
                ),
            },
        )
        # Access via alias
        result = config.resolve_serialized_value('old_name')
        assert result.value == '"value"'
        assert result._reason == 'resolved'

    def test_multiple_aliases(self):
        """Test that multiple aliases resolve correctly."""
        config = VariablesConfig(
            variables={
                'actual_name': VariableConfig(
                    name='actual_name',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    aliases=['alias1', 'alias2', 'alias3'],
                ),
            },
        )
        # Access via any alias
        for alias in ['alias1', 'alias2', 'alias3']:
            result = config.resolve_serialized_value(alias)
            assert result.value == '"value"'
            assert result._reason == 'resolved'

    def test_nonexistent_variable_returns_unrecognized(self):
        """Test that nonexistent variable returns unrecognized."""
        config = VariablesConfig(
            variables={
                'real_var': VariableConfig(
                    name='real_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            },
        )
        result = config.resolve_serialized_value('nonexistent')
        assert result.value is None
        assert result._reason == 'unrecognized_variable'

    def test_direct_name_takes_precedence(self):
        """Test that direct variable name takes precedence over alias lookup."""
        config = VariablesConfig(
            variables={
                'var_name': VariableConfig(
                    name='var_name',
                    labels={'v1': LabeledValue(version=1, serialized_value='"direct"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    aliases=['some_alias'],
                ),
            },
        )
        # Direct name access
        result = config.resolve_serialized_value('var_name')
        assert result.value == '"direct"'


# =============================================================================
# Test Base VariableProvider Write Methods (warnings)
# =============================================================================


class TestBaseVariableProviderWriteMethods:
    def test_get_variable_config_returns_none(self):
        """Test default implementation returns None."""
        provider = NoOpVariableProvider()
        assert provider.get_variable_config('any') is None

    def test_get_all_variables_config_returns_empty(self):
        """Test default implementation returns empty config."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        result = provider.get_all_variables_config()
        assert result.variables == {}

    def test_create_variable_warns(self):
        """Test default create_variable emits warning."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        config = VariableConfig(
            name='test',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        with pytest.warns(UserWarning, match='does not persist variable writes'):
            result = provider.create_variable(config)
        assert result.name == 'test'

    def test_update_variable_warns(self):
        """Test default update_variable emits warning."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        config = VariableConfig(
            name='test',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        with pytest.warns(UserWarning, match='does not persist variable writes'):
            result = provider.update_variable('test', config)
        assert result.name == 'test'

    def test_delete_variable_warns(self):
        """Test default delete_variable emits warning."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        with pytest.warns(UserWarning, match='does not persist variable writes'):
            provider.delete_variable('test')

    def test_batch_update_delegates(self):
        """Test batch_update calls individual methods."""

        class TrackingProvider(VariableProvider):
            def __init__(self):
                self.created: list[str] = []
                self.updated: list[str] = []
                self.deleted: list[str] = []
                self.configs: dict[str, VariableConfig] = {}

            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_variable_config(self, name: str) -> VariableConfig | None:
                return self.configs.get(name)

            def create_variable(self, config: VariableConfig) -> VariableConfig:
                self.created.append(config.name)
                self.configs[config.name] = config
                return config

            def update_variable(self, name: str, config: VariableConfig) -> VariableConfig:
                self.updated.append(name)
                self.configs[name] = config
                return config

            def delete_variable(self, name: str) -> None:
                self.deleted.append(name)
                self.configs.pop(name, None)

        provider = TrackingProvider()
        # Pre-create an existing var
        provider.configs['existing'] = VariableConfig(
            name='existing',
            labels={'v1': LabeledValue(version=1, serialized_value='"old"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )

        updates: dict[str, VariableConfig | None] = {
            'new_var': VariableConfig(
                name='new_var',
                labels={'v1': LabeledValue(version=1, serialized_value='"new"')},
                rollout=Rollout(labels={'v1': 1.0}),
                overrides=[],
            ),
            'existing': VariableConfig(
                name='existing',
                labels={'v2': LabeledValue(version=1, serialized_value='"updated"')},
                rollout=Rollout(labels={'v2': 1.0}),
                overrides=[],
            ),
            'to_delete': None,
        }
        # Add to_delete to configs first
        provider.configs['to_delete'] = VariableConfig(
            name='to_delete',
            labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )

        provider.batch_update(updates)

        assert 'new_var' in provider.created
        assert 'existing' in provider.updated
        assert 'to_delete' in provider.deleted


# =============================================================================
# Test NoOpVariableProvider push/validate
# =============================================================================


class TestNoOpVariableProviderPushValidate:
    def test_push_variables_prints_message(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        provider = NoOpVariableProvider()
        var = lf.var(name='test', default='default', type=str)
        result = provider.push_variables([var])
        assert result is False
        captured = capsys.readouterr()
        assert 'No variable provider configured' in captured.out

    def test_validate_variables_returns_empty_report(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        provider = NoOpVariableProvider()
        var = lf.var(name='test', default='default', type=str)
        result = provider.validate_variables([var])
        # NoOpVariableProvider returns an empty report (is_valid=True, no variables checked)
        assert result.is_valid
        assert result.variables_checked == 0
        assert result.errors == []
        assert result.variables_not_on_server == []


# =============================================================================
# Test push_variables Method
# =============================================================================


class TestPushVariables:
    def test_push_variables_empty_list(self, capsys: pytest.CaptureFixture[str]):
        """Test push_variables with empty variables list."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        result = provider.push_variables([])
        assert result is False
        captured = capsys.readouterr()
        assert 'No variables to push' in captured.out

    def test_push_variables_no_changes(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        """Test push_variables when server is up to date."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'string'},
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default='default', type=str)
        result = provider.push_variables([var])
        assert result is False
        captured = capsys.readouterr()
        assert 'No changes needed' in captured.out

    def test_push_variables_create_new(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        """Test push_variables creating a new variable."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='new_var', default='default', type=str, description='A new variable for testing')
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Variables to CREATE' in captured.out
        assert 'new_var' in captured.out
        assert 'A new variable for testing' in captured.out or 'Description' in captured.out
        assert 'new_var' in provider._config.variables

    def test_push_variables_create_with_function_default(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables with a function default (no default label)."""

        def resolve_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'computed'  # pragma: no cover

        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='fn_var', default=resolve_fn, type=str)
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'No example value' in captured.out

    def test_push_variables_update_schema(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        """Test push_variables updating schema."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='123')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'integer'},  # Old schema
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Now we want it to be a string
        var = lf.var(name='my_var', default='default', type=str)
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Variables to UPDATE' in captured.out

    def test_push_variables_update_with_incompatible_labels(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables with incompatible labels warning."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'string'},
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Changing from string to int - existing label is incompatible
        var = lf.var(name='my_var', default=0, type=int)
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Warning' in captured.out or 'Incompatible' in captured.out

    def test_push_variables_strict_mode_fails_with_incompatible(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables in strict mode fails with incompatible labels."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'string'},
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default=0, type=int)
        result = provider.push_variables([var], strict=True)
        assert result is False
        captured = capsys.readouterr()
        # Error message may go to stdout or stderr depending on implementation
        all_output = captured.out + captured.err
        assert 'Error' in all_output or 'strict' in all_output.lower()

    def test_push_variables_both_schema_and_unchanged_incompatible(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables message when both schema-change and unchanged variables have incompatible labels (line 1035)."""
        server_config = VariablesConfig(
            variables={
                'schema_change_var': VariableConfig(
                    name='schema_change_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'string'},  # Old schema
                ),
                'unchanged_var': VariableConfig(
                    name='unchanged_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'integer'},  # Same schema as local
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # schema_change_var: was string, now int → update_schema with incompatible label
        var1 = lf.var(name='schema_change_var', default=0, type=int)
        # unchanged_var: same schema (int) but label value is incompatible
        var2 = lf.var(name='unchanged_var', default=0, type=int)
        result = provider.push_variables([var1, var2], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'incompatible with the variable types' in captured.out
        assert 'schema changes will make additional values incompatible' in captured.out

    def test_push_variables_only_unchanged_incompatible(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables message when only unchanged variables have incompatible labels (line 1039)."""
        server_config = VariablesConfig(
            variables={
                'unchanged_var': VariableConfig(
                    name='unchanged_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'integer'},  # Same schema as local
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Create a new var to ensure there are changes (so push proceeds)
        var_new = lf.var(name='new_var', default='hello', type=str)
        var_unchanged = lf.var(name='unchanged_var', default=0, type=int)
        result = provider.push_variables([var_new, var_unchanged], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'incompatible with the variable types (schema unchanged)' in captured.out

    def test_push_variables_dry_run(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        """Test push_variables dry run mode."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='new_var', default='default', type=str)
        result = provider.push_variables([var], dry_run=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Dry run mode' in captured.out
        # Variable should NOT be created
        assert 'new_var' not in provider._config.variables

    def test_push_variables_orphaned_server_variables(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables shows orphaned server variables."""
        server_config = VariablesConfig(
            variables={
                'orphaned_var': VariableConfig(
                    name='orphaned_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Push a different variable, orphaned_var is not in local code
        var = lf.var(name='local_var', default='default', type=str)
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Server-only variables' in captured.out or 'orphaned_var' in captured.out

    def test_push_variables_description_differences(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables shows description differences."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    description='Old description',
                    json_schema={'type': 'string'},
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default='default', type=str, description='New description')
        provider.push_variables([var], yes=True)
        captured = capsys.readouterr()
        assert 'Description differences' in captured.out or 'description' in captured.out.lower()


# =============================================================================
# Test validate_variables Method
# =============================================================================


class TestValidateVariables:
    def test_validate_variables_empty_list(self):
        """Test validate_variables with empty variables list."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        result = provider.validate_variables([])
        assert result.is_valid
        assert result.variables_checked == 0
        assert result.errors == []
        assert result.variables_not_on_server == []

    def test_validate_variables_all_valid(self, config_kwargs: dict[str, Any]):
        """Test validate_variables with all valid labels."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"valid_string"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default='default', type=str)
        result = provider.validate_variables([var])
        assert result.is_valid
        assert result.variables_checked == 1
        assert result.errors == []
        assert result.variables_not_on_server == []

    def test_validate_variables_with_errors(self, config_kwargs: dict[str, Any]):
        """Test validate_variables with validation errors."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_an_int"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default=0, type=int)
        result = provider.validate_variables([var])
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].variable_name == 'my_var'
        assert result.errors[0].label == 'v1'
        # Check that format() produces output about the error
        formatted = result.format(colors=False)
        assert 'my_var' in formatted
        assert 'v1' in formatted

    def test_validate_variables_not_on_server(self, config_kwargs: dict[str, Any]):
        """Test validate_variables with variables not on server."""
        provider = LocalVariableProvider(VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='missing_var', default='default', type=str)
        result = provider.validate_variables([var])
        assert not result.is_valid
        assert 'missing_var' in result.variables_not_on_server
        # Check that format() produces output about missing variable
        formatted = result.format(colors=False)
        assert 'missing_var' in formatted
        assert 'Not Found' in formatted or 'not on server' in formatted.lower()

    def test_validate_variables_description_differences(self, config_kwargs: dict[str, Any]):
        """Test validate_variables shows description differences."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    description='Server description',
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default='default', type=str, description='Local description')
        result = provider.validate_variables([var])
        # The variable is valid (labels match) but has description differences
        assert result.is_valid  # No validation errors
        assert len(result.description_differences) == 1
        assert result.description_differences[0].variable_name == 'my_var'
        assert result.description_differences[0].local_description == 'Local description'
        assert result.description_differences[0].server_description == 'Server description'
        # Check that format() produces output about description differences
        formatted = result.format(colors=False)
        assert 'description' in formatted.lower() or 'my_var' in formatted


# =============================================================================
# Test Error Handling in push_variables and validate_variables
# =============================================================================


class TestPushValidateErrorHandling:
    """Test error handling in push_variables and validate_variables methods."""

    def test_push_variables_refresh_error(self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]):
        """Test push_variables handles refresh errors gracefully."""

        class FailingRefreshProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def refresh(self, force: bool = False):
                raise RuntimeError('Refresh failed!')

            def get_all_variables_config(self) -> VariablesConfig:
                return VariablesConfig(variables={})

        provider = FailingRefreshProvider()
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='test_var', default='default', type=str)
        # Should not crash, should print warning
        provider.push_variables([var], yes=True)
        captured = capsys.readouterr()
        # Output may go to stdout or stderr depending on implementation
        all_output = captured.out + captured.err
        assert 'Could not refresh provider' in all_output or 'Warning' in all_output

    def test_push_variables_get_all_config_error(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables handles get_all_variables_config errors."""

        class FailingConfigProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_all_variables_config(self) -> VariablesConfig:
                raise RuntimeError('Config fetch failed!')

        provider = FailingConfigProvider()
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='test_var', default='default', type=str)
        result = provider.push_variables([var])
        assert result is False
        captured = capsys.readouterr()
        # Output may go to stdout or stderr depending on implementation
        all_output = captured.out + captured.err
        assert 'Error fetching current config' in all_output

    def test_push_variables_apply_changes_error(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables handles apply changes errors."""

        class FailingApplyProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_all_variables_config(self) -> VariablesConfig:
                return VariablesConfig(variables={})

            def create_variable(self, config: VariableConfig) -> VariableConfig:
                raise RuntimeError('Create failed!')

        provider = FailingApplyProvider()
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='new_var', default='default', type=str)
        result = provider.push_variables([var], yes=True)
        assert result is False
        captured = capsys.readouterr()
        # Output may go to stdout or stderr depending on implementation
        all_output = captured.out + captured.err
        assert 'Error applying changes' in all_output

    def test_validate_variables_refresh_error(self, config_kwargs: dict[str, Any]):
        """Test validate_variables propagates refresh errors."""

        class FailingRefreshProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def refresh(self, force: bool = False):
                raise RuntimeError('Refresh failed!')

            def get_all_variables_config(self) -> VariablesConfig:
                return VariablesConfig(variables={})  # pragma: no cover

        provider = FailingRefreshProvider()
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='test_var', default='default', type=str)
        # Exception should propagate for CI automation
        with pytest.raises(RuntimeError, match='Refresh failed'):
            provider.validate_variables([var])

    def test_validate_variables_get_all_config_error(self, config_kwargs: dict[str, Any]):
        """Test validate_variables propagates get_all_variables_config errors."""

        class FailingConfigProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_all_variables_config(self) -> VariablesConfig:
                raise RuntimeError('Config fetch failed!')

        provider = FailingConfigProvider()
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='test_var', default='default', type=str)
        # Exception should propagate for CI automation
        with pytest.raises(RuntimeError, match='Config fetch failed'):
            provider.validate_variables([var])


# =============================================================================
# Test Additional Edge Cases for Coverage
# =============================================================================


class TestAdditionalEdgeCases:
    def test_push_variables_with_compatible_labels(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables when existing labels are compatible with the new schema."""
        # Server has a string variable with string labels
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"compatible_value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'integer'},  # Old schema is integer
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Local expects a string - variant is compatible since it's a valid JSON string
        var = lf.var(name='my_var', default='default', type=str)
        result = provider.push_variables([var], yes=True)
        # This should succeed since the variant can deserialize to string
        assert result is True
        captured = capsys.readouterr()
        # The variant '"compatible_value"' should be compatible with type str
        assert 'Variables to UPDATE' in captured.out

    def test_variable_get_with_active_trace(self, config_kwargs: dict[str, Any]):
        """Test that variable.get() uses trace_id as targeting_key when in active span."""
        from opentelemetry import trace

        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='test_var', default='default', type=str)

        # Create a real trace context using the logfire instance
        with lf.span('test_span'):
            current_span = trace.get_current_span()
            trace_id = current_span.get_span_context().trace_id
            # Verify we have an active trace
            assert trace_id != 0

            # Call get() - should use trace_id as targeting_key
            result = var.get()

            # The targeting_key should be set from the trace_id
            # We can't easily verify the exact targeting_key used internally,
            # but we can verify the call succeeded and the span was created
            assert result.value == 'default'  # Falls back to default since no config

    def test_format_validation_report_with_missing_variable(self, config_kwargs: dict[str, Any]):
        """Test validate_variables when variable is not on server."""
        # Create a config that will report "not on server"
        server_config = VariablesConfig(variables={})
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='missing_var', default='default', type=str)
        result = provider.validate_variables([var])
        assert not result.is_valid
        assert 'missing_var' in result.variables_not_on_server
        # Test formatting
        formatted = result.format(colors=False)
        assert 'missing_var' in formatted

    def test_format_validation_report_with_many_error_lines(self, config_kwargs: dict[str, Any]):
        """Test validate_variables formatting when error has many lines."""
        # Create a config where variant validation will produce a multi-line error
        server_config = VariablesConfig(
            variables={
                'complex_var': VariableConfig(
                    name='complex_var',
                    labels={
                        'v1': LabeledValue(
                            version=1,
                            # This JSON won't validate against a complex Pydantic model
                            serialized_value='{"invalid": "structure", "with": "many", "fields": "that", "are": "wrong"}',
                        )
                    },
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)

        # Create a variable with a complex type that will generate multi-line errors
        class ComplexModel(BaseModel):
            required_field: str
            another_required: int
            yet_another: list[str]
            nested: dict[str, int]

        var = lf.var(
            name='complex_var',
            default=ComplexModel(required_field='x', another_required=1, yet_another=[], nested={}),
            type=ComplexModel,
        )
        result = provider.validate_variables([var])
        assert not result.is_valid
        assert len(result.errors) > 0
        # Check formatting with multi-line error
        formatted = result.format(colors=False)
        assert 'complex_var' in formatted
        assert 'v1' in formatted


class TestVariableToConfig:
    """Tests for Variable.to_config() method."""

    def test_to_config(self, config_kwargs: dict[str, Any]):
        """Test converting a Variable to VariableConfig."""
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', type=str, default='hello', description='Test desc')
        config = var.to_config()
        assert config.name == 'my_var'
        assert config.description == 'Test desc'
        assert config.example == '"hello"'
        assert config.labels == {}
        assert config.rollout.labels == {}
        assert config.overrides == []

    def test_to_config_with_function_default(self, config_kwargs: dict[str, Any]):
        """Test to_config when default is a function."""
        lf = logfire.configure(**config_kwargs)

        def my_resolver(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> int:
            return 99  # pragma: no cover

        var = lf.var(name='func_var', type=int, default=my_resolver)
        config = var.to_config()
        assert config.name == 'func_var'
        # Example should be None when default is a function
        assert config.example is None


# =============================================================================
# Tests for additional coverage
# =============================================================================


class TestIsResolveFunctionEdgeCases:
    """Test edge cases in is_resolve_function."""

    def test_uninspectable_callable(self):
        """Callables that raise ValueError from inspect.signature return False."""

        class Uninspectable:
            def __call__(self) -> None:
                pass  # pragma: no cover

            __signature__: Any = 'not a signature'

        assert is_resolve_function(Uninspectable()) is False

    def test_no_params(self):
        """A callable with no parameters is not a resolve function."""

        def no_args():
            pass  # pragma: no cover

        assert is_resolve_function(no_args) is False

    def test_var_positional(self):
        """A callable with *args counts as a resolve function."""

        def with_args(*args: Any):
            pass  # pragma: no cover

        assert is_resolve_function(with_args) is True

    def test_var_positional_with_required(self):
        """A callable with 3 required args + *args is not a resolve function."""

        def three_required(a: Any, b: Any, c: Any, *args: Any):
            pass  # pragma: no cover

        assert is_resolve_function(three_required) is False

    def test_var_keyword_only(self):
        """**kwargs doesn't count toward positional."""

        def two_pos_with_kwargs(a: Any, b: Any, **kwargs: Any):
            pass  # pragma: no cover

        assert is_resolve_function(two_pos_with_kwargs) is True

    def test_optional_positional(self):
        """A callable with one required and one optional positional param."""

        def one_required_one_optional(a: Any, b: Any = None):
            pass  # pragma: no cover

        assert is_resolve_function(one_required_one_optional) is True

    def test_all_optional(self):
        """A callable with two optional positional params."""

        def both_optional(a: Any = 1, b: Any = 2):
            pass  # pragma: no cover

        assert is_resolve_function(both_optional) is True

    def test_keyword_only_param(self):
        """Keyword-only params don't affect positional count."""

        def with_keyword_only(a: Any, b: Any, *, c: Any):
            pass  # pragma: no cover

        assert is_resolve_function(with_keyword_only) is True


class TestVariableGetReprFallback:
    """Test that variable.get() falls back to repr() when dump_json fails."""

    def test_repr_fallback_when_dump_json_fails(self, config_kwargs: dict[str, Any]):
        """When type_adapter.dump_json raises, we fall back to repr()."""
        from unittest.mock import patch

        variables_config = VariablesConfig(
            variables={
                'repr_var': VariableConfig(
                    name='repr_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"hello"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='repr_var', default='default', type=str)

        # Patch dump_json to raise an exception
        with patch.object(var.type_adapter, 'dump_json', side_effect=RuntimeError('Cannot serialize')):
            result = var.get()
            # Value should still be resolved correctly
            assert result.value == 'hello'


class TestValidationReportHasErrors:
    """Test the has_errors property of ValidationReport."""

    def test_has_errors_with_errors(self):
        """has_errors returns True when there are validation errors."""
        from logfire.variables.abstract import LabelValidationError, ValidationReport

        report = ValidationReport(
            errors=[LabelValidationError(variable_name='test', label='staging', error=ValueError('bad'))],
            variables_checked=1,
            variables_not_on_server=[],
            description_differences=[],
        )
        assert report.has_errors is True

    def test_has_errors_without_errors(self):
        """has_errors returns False when validation passed."""
        from logfire.variables.abstract import ValidationReport

        report = ValidationReport(
            errors=[],
            variables_checked=1,
            variables_not_on_server=[],
            description_differences=[],
        )
        assert report.has_errors is False

    def test_has_errors_with_variables_not_on_server(self):
        """has_errors returns True when variables are not on the server."""
        from logfire.variables.abstract import ValidationReport

        report = ValidationReport(
            errors=[],
            variables_checked=1,
            variables_not_on_server=['missing'],
            description_differences=[],
        )
        assert report.has_errors is True


class TestGetSerializedValueForVariantUnknown:
    """Test get_serialized_value_for_label when the variable doesn't exist."""

    def test_unknown_variable_returns_unrecognized(self):
        """Default implementation returns unrecognized when variable config is None."""
        provider = NoOpVariableProvider()
        result = provider.get_serialized_value_for_label('nonexistent', 'v1')
        assert result.value is None
        assert result._reason == 'unrecognized_variable'


class TestBaseVariableProviderTypesMethods:
    """Test base VariableProvider methods for variable types."""

    def test_list_variable_types_warns(self):
        """Default list_variable_types emits warning and returns empty dict."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        with pytest.warns(UserWarning, match='does not support variable types'):
            result = provider.list_variable_types()
        assert result == {}

    def test_get_variable_type(self):
        """Default get_variable_type delegates to list_variable_types."""

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        with pytest.warns(UserWarning, match='does not support variable types'):
            result = provider.get_variable_type('some_type')
        assert result is None

    def test_upsert_variable_type_warns(self):
        """Default upsert_variable_type emits warning and returns config."""
        from logfire.variables.config import VariableTypeConfig

        class MinimalProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

        provider = MinimalProvider()
        config = VariableTypeConfig(name='test_type', json_schema={'type': 'string'})
        with pytest.warns(UserWarning, match='does not persist variable type writes'):
            result = provider.upsert_variable_type(config)
        assert result.name == 'test_type'


class TestNegativeRolloutWeights:
    """Test that negative rollout weights are rejected."""

    def test_negative_weight_raises_validation_error(self):
        """Negative variant proportions should raise."""
        with pytest.raises(ValidationError, match='Label proportions must not be negative'):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'labels': {'v1': {'version': 1, 'serialized_value': '"value"'}},
                    'rollout': {'labels': {'v1': -0.5}},
                    'overrides': [],
                }
            )


class TestGetDefaultTypeName:
    """Test get_default_type_name function."""

    def test_class_type(self):
        from logfire.variables.config import get_default_type_name

        assert get_default_type_name(int) == 'int'

    def test_non_class_type(self):
        from typing import Union

        from logfire.variables.config import get_default_type_name

        # Union types are not `type` instances
        result = get_default_type_name(Union[int, str])
        assert isinstance(result, str)
        assert result  # Should be a non-empty string


class TestGetSourceHint:
    """Test get_source_hint function."""

    def test_class_with_module(self):
        from pydantic import BaseModel

        from logfire.variables.config import get_source_hint

        class MyModel(BaseModel):
            x: int

        hint = get_source_hint(MyModel)
        assert hint is not None
        assert 'MyModel' in hint

    def test_non_class(self):
        from logfire.variables.config import get_source_hint

        assert get_source_hint('not a type') is None


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestRemoteProviderForceRefreshEvent:
    """Test the force refresh event (SSE trigger)."""

    def test_force_refresh_via_worker(self):
        """When _force_refresh_event is set, the worker makes a forced fetch."""
        request_mocker = requests_mock_module.Mocker()
        adapter = request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),  # Long poll so worker won't auto-refresh
                ),
            )
            try:
                # Start the provider to launch the worker thread
                provider.start(None)

                # Wait for initial fetch
                start_time = time.time()
                while adapter.call_count < 1:
                    if time.time() - start_time > 5:  # pragma: no cover
                        raise AssertionError(f'Timed out, call_count={adapter.call_count}')
                    time.sleep(0.01)  # pragma: no cover

                initial_count = adapter.call_count

                # Simulate an SSE event triggering a force refresh
                provider._force_refresh_event.set()
                provider._worker_awaken.set()  # Wake the worker

                # Wait for the forced fetch
                start_time = time.time()
                while adapter.call_count <= initial_count:
                    if time.time() - start_time > 5:  # pragma: no cover
                        raise AssertionError(f'Timed out, call_count={adapter.call_count}')
                    time.sleep(0.01)  # pragma: no cover

                # Force refresh event should have been cleared by the worker
                assert not provider._force_refresh_event.is_set()
                assert adapter.call_count > initial_count
            finally:
                provider.shutdown()


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestRemoteProviderConditionExtraFields:
    """Test _condition_extra_fields with various condition types."""

    def test_value_does_not_equal_condition(self):
        """Test ValueDoesNotEqual serialization."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        post_adapter = request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'test'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                ValueDoesNotEqual(attribute='status', value='blocked'),
                                ValueIsNotIn(attribute='region', values=['eu', 'us']),
                                ValueDoesNotMatchRegex(attribute='email', pattern=r'@test\.com$'),
                            ],
                            rollout=Rollout(labels={'v1': 1.0}),
                        )
                    ],
                )
                provider.create_variable(config)

                assert post_adapter.last_request is not None
                body = post_adapter.last_request.json()
                conditions = body['overrides'][0]['conditions']
                assert len(conditions) == 3
                assert conditions[0]['kind'] == 'value-does-not-equal'
                assert conditions[0]['value'] == 'blocked'
                assert conditions[1]['kind'] == 'value-is-not-in'
                assert conditions[1]['values'] == ['eu', 'us']
                assert conditions[2]['kind'] == 'value-does-not-match-regex'
                assert conditions[2]['pattern'] == r'@test\.com$'
            finally:
                provider.shutdown()

    def test_compiled_regex_pattern(self):
        """Test that compiled regex patterns are serialized correctly."""
        import re

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        post_adapter = request_mocker.post('http://localhost:8000/v1/variables/', json={'name': 'test'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                ValueMatchesRegex(attribute='name', pattern=re.compile(r'^test_\d+')),
                            ],
                            rollout=Rollout(labels={'v1': 1.0}),
                        )
                    ],
                )
                provider.create_variable(config)

                assert post_adapter.last_request is not None
                body = post_adapter.last_request.json()
                conditions = body['overrides'][0]['conditions']
                assert conditions[0]['pattern'] == r'^test_\d+'
            finally:
                provider.shutdown()


@pytest.mark.filterwarnings('ignore::pytest.PytestUnhandledThreadExceptionWarning')
class TestRemoteProviderVariableTypes:
    """Test remote provider variable type operations."""

    def test_list_variable_types(self):
        """Test listing variable types from remote API."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.get(
            'http://localhost:8000/v1/variable-types/',
            json=[
                {
                    'name': 'FeatureConfig',
                    'json_schema': {'type': 'object', 'properties': {'enabled': {'type': 'boolean'}}},
                    'description': 'Feature configuration',
                    'source_hint': 'myapp.config.FeatureConfig',
                },
                {
                    'name': 'SimpleType',
                    'json_schema': {'type': 'string'},
                },
            ],
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                types = provider.list_variable_types()
                assert len(types) == 2
                assert 'FeatureConfig' in types
                assert types['FeatureConfig'].description == 'Feature configuration'
                assert types['FeatureConfig'].source_hint == 'myapp.config.FeatureConfig'
                assert 'SimpleType' in types
                assert types['SimpleType'].description is None
            finally:
                provider.shutdown()

    def test_list_variable_types_api_error(self):
        """Test listing variable types when API fails."""
        from logfire.variables.abstract import VariableWriteError

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.get('http://localhost:8000/v1/variable-types/', status_code=500)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                with pytest.raises(VariableWriteError, match='Failed to list variable types'):
                    provider.list_variable_types()
            finally:
                provider.shutdown()

    def test_upsert_variable_type(self):
        """Test creating/updating a variable type via remote API."""
        from logfire.variables.config import VariableTypeConfig

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        post_adapter = request_mocker.post('http://localhost:8000/v1/variable-types/', json={'name': 'MyType'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableTypeConfig(
                    name='MyType',
                    json_schema={'type': 'object'},
                    description='My type',
                    source_hint='myapp.MyType',
                )
                result = provider.upsert_variable_type(config)
                assert result.name == 'MyType'

                assert post_adapter.last_request is not None
                body = post_adapter.last_request.json()
                assert body['name'] == 'MyType'
                assert body['json_schema'] == {'type': 'object'}
                assert body['description'] == 'My type'
                assert body['source_hint'] == 'myapp.MyType'
            finally:
                provider.shutdown()

    def test_upsert_variable_type_without_source_hint(self):
        """Test upsert without source_hint."""
        from logfire.variables.config import VariableTypeConfig

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        post_adapter = request_mocker.post('http://localhost:8000/v1/variable-types/', json={'name': 'MyType'})
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableTypeConfig(name='MyType', json_schema={'type': 'string'})
                provider.upsert_variable_type(config)

                assert post_adapter.last_request is not None
                body = post_adapter.last_request.json()
                assert 'source_hint' not in body
            finally:
                provider.shutdown()

    def test_upsert_variable_type_api_error(self):
        """Test upsert variable type when API fails."""
        from logfire.variables.abstract import VariableWriteError
        from logfire.variables.config import VariableTypeConfig

        request_mocker = requests_mock_module.Mocker()
        request_mocker.get('http://localhost:8000/v1/variables/', json={'variables': {}})
        request_mocker.post('http://localhost:8000/v1/variable-types/', status_code=500)
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                options=VariablesOptions(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableTypeConfig(name='MyType', json_schema={'type': 'string'})
                with pytest.raises(VariableWriteError, match='Failed to upsert variable type'):
                    provider.upsert_variable_type(config)
            finally:
                provider.shutdown()


class TestPushVariableTypes:
    """Test the push_variable_types method on VariableProvider."""

    @staticmethod
    def _make_types_provider(
        existing_types: dict[str, Any] | None = None,
    ) -> VariableProvider:
        """Create a provider that supports variable types for testing push_variable_types."""
        from logfire.variables.config import VariableTypeConfig

        class TypesProvider(VariableProvider):
            def __init__(self) -> None:
                self._types: dict[str, VariableTypeConfig] = {}
                if existing_types:
                    for name, schema in existing_types.items():
                        self._types[name] = VariableTypeConfig(name=name, json_schema=schema)

            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def list_variable_types(self) -> dict[str, VariableTypeConfig]:
                return dict(self._types)

            def upsert_variable_type(self, config: VariableTypeConfig) -> VariableTypeConfig:
                self._types[config.name] = config
                return config

        return TypesProvider()

    def test_push_variable_types_empty(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing empty types list."""
        provider = self._make_types_provider()
        result = provider.push_variable_types([])
        assert result is False
        captured = capsys.readouterr()
        assert 'No types to push' in captured.out

    def test_push_variable_types_create(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing new types."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool
            max_items: int = 10

        provider = self._make_types_provider()
        result = provider.push_variable_types([FeatureConfig], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'FeatureConfig' in captured.out
        assert 'New types' in captured.out

    def test_push_variable_types_with_explicit_name(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing types with explicit names."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        provider = self._make_types_provider()
        result = provider.push_variable_types([(FeatureConfig, 'my_feature')], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'my_feature' in captured.out

    def test_push_variable_types_no_changes(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing when types are already up to date."""
        from pydantic import BaseModel, TypeAdapter

        class FeatureConfig(BaseModel):
            enabled: bool

        adapter = TypeAdapter(FeatureConfig)
        existing_schema = adapter.json_schema()

        provider = self._make_types_provider(existing_types={'FeatureConfig': existing_schema})

        result = provider.push_variable_types([FeatureConfig])
        assert result is False
        captured = capsys.readouterr()
        assert 'No changes needed' in captured.out

    def test_push_variable_types_schema_update(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing when type schema has changed."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool
            new_field: str = 'default'

        # Existing schema is different from current
        provider = self._make_types_provider(existing_types={'FeatureConfig': {'type': 'object'}})

        result = provider.push_variable_types([FeatureConfig], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Schema updates' in captured.out

    def test_push_variable_types_dry_run(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing types in dry run mode."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        provider = self._make_types_provider()
        result = provider.push_variable_types([FeatureConfig], dry_run=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Dry run mode' in captured.out

    def test_push_variable_types_refresh_error(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing types when refresh fails."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        class FailingRefreshProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def refresh(self, force: bool = False):
                raise RuntimeError('Refresh failed!')

            def list_variable_types(self) -> dict[str, Any]:
                return {}

        provider = FailingRefreshProvider()
        provider.push_variable_types([FeatureConfig], yes=True)
        captured = capsys.readouterr()
        assert 'Could not refresh provider' in captured.out or 'Warning' in captured.out

    def test_push_variable_types_list_error(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing types when listing types fails."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        class FailingListProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def list_variable_types(self) -> dict[str, Any]:
                raise RuntimeError('List failed!')

        provider = FailingListProvider()
        result = provider.push_variable_types([FeatureConfig])
        assert result is False
        captured = capsys.readouterr()
        assert 'Error fetching current types' in captured.out

    def test_push_variable_types_apply_error(self, capsys: pytest.CaptureFixture[str]):
        """Test pushing types when applying changes fails."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        class FailingApplyProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def list_variable_types(self) -> dict[str, Any]:
                return {}

            def upsert_variable_type(self, config: Any) -> Any:
                raise RuntimeError('Upsert failed!')

        provider = FailingApplyProvider()
        result = provider.push_variable_types([FeatureConfig], yes=True)
        assert result is False
        captured = capsys.readouterr()
        assert 'Error applying changes' in captured.out


class TestResolveVariantDeserializationError:
    """Test the error path when deserialization fails for an explicitly requested variant."""

    def test_variant_deserialization_error_falls_back_to_default(self, config_kwargs: dict[str, Any]):
        """When an explicit variant value can't be deserialized, resolve falls back to the default."""
        variables_config = VariablesConfig(
            variables={
                'typed_var': VariableConfig(
                    name='typed_var',
                    json_schema={'type': 'integer'},
                    labels={
                        'bad_variant': LabeledValue(version=1, serialized_value='"not_an_int"'),
                    },
                    rollout=Rollout(labels={'bad_variant': 1.0}),
                    overrides=[],
                )
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='typed_var', default=99, type=int)

        result = var.get(label='bad_variant')
        # Should fall back to default because the variant value is invalid
        assert result.value == 99
        assert result.exception is not None


class TestGetSourceHintNoModule:
    """Test get_source_hint when a type has no module attribute."""

    def test_type_without_module(self):
        """A type with no __module__ should return None."""
        from logfire.variables.config import get_source_hint

        # Create a type-like object without __module__
        t = type('NoModule', (), {})
        # Remove __module__ to simulate edge case
        t.__module__ = ''  # empty module
        assert get_source_hint(t) is None


class TestPushVariableTypesWithUnchangedTypes:
    """Test push_variable_types with a mix of changed and unchanged types to cover loop skip."""

    def test_push_with_unchanged_and_new_types(self, capsys: pytest.CaptureFixture[str]):
        """When pushing multiple types where some are unchanged, unchanged ones are skipped in apply."""
        from pydantic import BaseModel, TypeAdapter

        from logfire.variables.config import VariableTypeConfig

        class ExistingType(BaseModel):
            value: int

        class NewType(BaseModel):
            name: str

        # ExistingType is already on server with same schema
        adapter = TypeAdapter(ExistingType)
        existing_schema = adapter.json_schema()

        class TypesProvider(VariableProvider):
            def __init__(self) -> None:
                self._types: dict[str, VariableTypeConfig] = {
                    'ExistingType': VariableTypeConfig(name='ExistingType', json_schema=existing_schema),
                }
                self.upserted: list[str] = []

            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def list_variable_types(self) -> dict[str, VariableTypeConfig]:
                return dict(self._types)

            def upsert_variable_type(self, config: VariableTypeConfig) -> VariableTypeConfig:
                self.upserted.append(config.name)
                self._types[config.name] = config
                return config

        provider = TypesProvider()
        result = provider.push_variable_types([ExistingType, NewType], yes=True)
        assert result is True
        # Only NewType should be upserted; ExistingType is unchanged
        assert 'NewType' in provider.upserted
        assert 'ExistingType' not in provider.upserted


class TestPushVariableTypesWithIncompatibleLabels:
    """Test push_variable_types label compatibility checking (lines 1336-1359)."""

    @staticmethod
    def _make_provider(
        existing_types: dict[str, Any],
        variables: dict[str, VariableConfig],
    ) -> VariableProvider:
        from logfire.variables.config import VariableTypeConfig

        class TypesWithVarsProvider(VariableProvider):
            def __init__(self) -> None:
                self._types: dict[str, VariableTypeConfig] = {}
                for name, schema in existing_types.items():
                    self._types[name] = VariableTypeConfig(name=name, json_schema=schema)
                self._variables_config = VariablesConfig(variables=variables)

            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_all_variables_config(self) -> VariablesConfig:
                return self._variables_config

            def list_variable_types(self) -> dict[str, VariableTypeConfig]:
                return dict(self._types)

            def upsert_variable_type(self, config: VariableTypeConfig) -> VariableTypeConfig:
                self._types[config.name] = config
                return config

        return TypesWithVarsProvider()

    def test_push_types_with_incompatible_labels_warning(self, capsys: pytest.CaptureFixture[str]):
        """Test push_variable_types shows incompatible label warnings (lines 1336-1359)."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool
            max_items: int = 10

        # Existing type has a different schema (old), so this will be an update
        provider = self._make_provider(
            existing_types={'FeatureConfig': {'type': 'object', 'properties': {'enabled': {'type': 'string'}}}},
            variables={
                'my_feature': VariableConfig(
                    name='my_feature',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_valid"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    type_name='FeatureConfig',
                ),
                # A variable with a different type_name to cover the `continue` branch (line 1337)
                'other_feature': VariableConfig(
                    name='other_feature',
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                    type_name='OtherType',
                ),
                # A variable with matching type_name but compatible labels (covers 1339->1335)
                'compatible_feature': VariableConfig(
                    name='compatible_feature',
                    labels={'v1': LabeledValue(version=1, serialized_value='{"enabled": true}')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    type_name='FeatureConfig',
                ),
            },
        )
        result = provider.push_variable_types([FeatureConfig], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Label compatibility warnings' in captured.out
        assert 'my_feature' in captured.out
        assert 'incompatible with the new type schema' in captured.out

    def test_push_types_with_incompatible_labels_strict(self, capsys: pytest.CaptureFixture[str]):
        """Test push_variable_types in strict mode fails with incompatible labels (line 1356-1357)."""
        from pydantic import BaseModel

        class FeatureConfig(BaseModel):
            enabled: bool

        provider = self._make_provider(
            existing_types={'FeatureConfig': {'type': 'object', 'properties': {'enabled': {'type': 'string'}}}},
            variables={
                'my_feature': VariableConfig(
                    name='my_feature',
                    labels={'v1': LabeledValue(version=1, serialized_value='"not_valid"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                    type_name='FeatureConfig',
                ),
            },
        )
        result = provider.push_variable_types([FeatureConfig], strict=True)
        assert result is False
        captured = capsys.readouterr()
        assert 'Error' in captured.out
        assert 'strict=False' in captured.out

    def test_push_types_compatibility_check_error(self, capsys: pytest.CaptureFixture[str]):
        """Test push_variable_types when get_all_variables_config fails during compatibility check (line 1343-1344)."""
        from pydantic import BaseModel

        from logfire.variables.config import VariableTypeConfig

        class FeatureConfig(BaseModel):
            enabled: bool

        class FailingConfigProvider(VariableProvider):
            def get_serialized_value(
                self, variable_name: str, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
            ) -> ResolvedVariable[str | None]:
                return ResolvedVariable(name=variable_name, value=None, _reason='no_provider')  # pragma: no cover

            def get_all_variables_config(self) -> VariablesConfig:
                raise RuntimeError('Config fetch failed!')

            def list_variable_types(self) -> dict[str, VariableTypeConfig]:
                return {'FeatureConfig': VariableTypeConfig(name='FeatureConfig', json_schema={'type': 'object'})}

            def upsert_variable_type(self, config: VariableTypeConfig) -> VariableTypeConfig:
                return config

        provider = FailingConfigProvider()
        result = provider.push_variable_types([FeatureConfig], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Could not check label compatibility' in captured.out


class TestVarResolveFunctionWithoutType:
    """Test that var() raises when default is a resolve function but type is not provided."""

    def test_resolve_function_default_without_type(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)

        def resolver(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'value'  # pragma: no cover

        with pytest.raises(TypeError, match='`type` must be provided'):
            lf.var(name='my_var', default=resolver)


class TestVarDuplicateName:
    """Test that var() raises when registering a variable with a duplicate name."""

    def test_duplicate_name_raises(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        lf.var(name='dup_var', default='hello', type=str)

        with pytest.raises(ValueError, match="A variable with name 'dup_var' has already been registered"):
            lf.var(name='dup_var', default='world', type=str)


class TestVarInvalidName:
    """Test that var() raises when registering a variable with an invalid name."""

    def test_invalid_name_raises(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)

        with pytest.raises(ValueError, match='Invalid variable name'):
            lf.var(name='1bad-name!', default='hello', type=str)


class TestVariablesOptionsPollingInterval:
    """Test that VariablesOptions validates polling_interval."""

    def test_too_short_timedelta_raises(self):
        with pytest.raises(ValueError, match='polling_interval must be at least 10 seconds'):
            VariablesOptions(polling_interval=timedelta(seconds=5))

    def test_too_short_float_raises(self):
        with pytest.raises(ValueError, match='polling_interval must be at least 10 seconds'):
            VariablesOptions(polling_interval=0.0)

    def test_valid_interval_accepted(self):
        config = VariablesOptions(polling_interval=timedelta(seconds=10))
        assert config.polling_interval == timedelta(seconds=10)


class TestIsResolveFunctionMultipleKeywordOnly:
    """Test is_resolve_function with multiple keyword-only params (covers 108->97 branch)."""

    def test_multiple_keyword_only_params(self):
        def with_multiple_kw_only(a: Any, b: Any, *, c: Any, d: Any):
            pass  # pragma: no cover

        assert is_resolve_function(with_multiple_kw_only) is True


# =============================================================================
# Additional coverage tests
# =============================================================================


class TestRolloutSelectLabelEmptyLabels:
    """Test Rollout.select_label with empty labels dict."""

    def test_empty_labels_returns_none(self):
        rollout = Rollout(labels={})
        assert rollout.select_label('any_seed') is None
        assert rollout.select_label(None) is None


class TestVariableConfigValidateRefToNonExistentLabel:
    """Test _validate_labels rejects ref to non-existent label."""

    def test_ref_to_nonexistent_label_raises(self):
        with pytest.raises(ValidationError, match="has ref 'nonexistent' which is not present"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'labels': {
                        'v1': {'version': 1, 'ref': 'nonexistent'},
                    },
                    'rollout': {'labels': {}},
                    'overrides': [],
                }
            )


class TestVariableConfigResolveValueCodeDefault:
    """Test resolve_value when labels point to code_default."""

    def test_code_default_ref_returns_none(self):
        config = VariableConfig(
            name='test_var',
            labels={'v1': LabelRef(ref='code_default')},
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        result = config.resolve_value()
        assert result == (None, 'v1', None)


class TestVariableConfigResolveValueExplicitLabel:
    """Test resolve_value with an explicit label parameter."""

    def test_explicit_label_found(self):
        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabeledValue(version=1, serialized_value='"value_v1"'),
                'v2': LabeledValue(version=2, serialized_value='"value_v2"'),
            },
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        serialized, label, version = config.resolve_value(label='v2')
        assert serialized == '"value_v2"'
        assert label == 'v2'
        assert version == 2

    def test_explicit_label_not_found_falls_through(self):
        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabeledValue(version=1, serialized_value='"value_v1"'),
            },
            rollout=Rollout(labels={'v1': 1.0}),
            overrides=[],
        )
        # Label 'missing' doesn't exist, should fall through to rollout
        serialized, label, _version = config.resolve_value(label='missing')
        assert serialized == '"value_v1"'
        assert label == 'v1'


class TestVariableConfigResolveValueLatestVersionFallback:
    """Test resolve_value falls back to latest_version when no label is selected."""

    def test_latest_version_used_when_no_label_selected(self):
        from logfire.variables.config import LatestVersion

        config = VariableConfig(
            name='test_var',
            labels={},
            rollout=Rollout(labels={}),  # No labels in rollout -> selects None
            overrides=[],
            latest_version=LatestVersion(version=5, serialized_value='"latest_val"'),
        )
        serialized, label, version = config.resolve_value()
        assert serialized == '"latest_val"'
        assert label is None
        assert version == 5


class TestVariableConfigFollowRef:
    """Test follow_ref method on VariableConfig."""

    def test_follow_ref_to_latest(self):
        from logfire.variables.config import LatestVersion

        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabelRef(version=1, ref='latest'),
            },
            rollout=Rollout(labels={}),
            overrides=[],
            latest_version=LatestVersion(version=3, serialized_value='"latest_val"'),
        )
        serialized, version = config.follow_ref(config.labels['v1'])
        assert serialized == '"latest_val"'
        assert version == 3

    def test_follow_ref_to_latest_no_latest_version(self):
        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabelRef(version=1, ref='latest'),
            },
            rollout=Rollout(labels={}),
            overrides=[],
            latest_version=None,
        )
        serialized, version = config.follow_ref(config.labels['v1'])
        assert serialized is None
        assert version == 1

    def test_follow_ref_chain(self):
        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabeledValue(version=1, serialized_value='"final_value"'),
                'v2': LabelRef(version=2, ref='v1'),
            },
            rollout=Rollout(labels={}),
            overrides=[],
        )
        serialized, version = config.follow_ref(config.labels['v2'])
        assert serialized == '"final_value"'
        assert version == 1

    def test_follow_ref_cycle_detection(self):
        config = VariableConfig.__new__(VariableConfig)
        # Bypass validation to create a cycle
        object.__setattr__(
            config,
            '__dict__',
            {
                'name': 'test_var',
                'labels': {
                    'a': LabelRef(version=1, ref='b'),
                    'b': LabelRef(version=2, ref='a'),
                },
                'rollout': Rollout(labels={}),
                'overrides': [],
                'latest_version': None,
                'description': None,
                'json_schema': None,
                'aliases': None,
                'example': None,
            },
        )
        serialized, version = config.follow_ref(config.labels['a'])
        assert serialized is None  # Cycle detected, returns None
        assert version == 1

    def test_follow_ref_to_nonexistent_label(self):
        config = VariableConfig.__new__(VariableConfig)
        # Bypass validation to create a ref to missing label
        object.__setattr__(
            config,
            '__dict__',
            {
                'name': 'test_var',
                'labels': {
                    'v1': LabelRef(version=1, ref='missing'),
                },
                'rollout': Rollout(labels={}),
                'overrides': [],
                'latest_version': None,
                'description': None,
                'json_schema': None,
                'aliases': None,
                'example': None,
            },
        )
        serialized, version = config.follow_ref(config.labels['v1'])
        assert serialized is None
        assert version == 1

    def test_follow_ref_to_code_default(self):
        from logfire.variables.config import LatestVersion

        config = VariableConfig(
            name='test_var',
            labels={
                'v1': LabelRef(ref='code_default'),
            },
            rollout=Rollout(labels={}),
            overrides=[],
            latest_version=LatestVersion(version=3, serialized_value='"latest_val"'),
        )
        serialized, version = config.follow_ref(config.labels['v1'])
        assert serialized is None
        assert version is None

    def test_label_ref_without_version(self):
        """LabelRef with version=None (default) parses correctly."""
        config = VariableConfig(
            name='test_var',
            labels={
                'staging': LabeledValue(version=1, serialized_value='"val"'),
                'prod': LabelRef(ref='staging'),
            },
            rollout=Rollout(labels={}),
            overrides=[],
        )
        prod_label = config.labels['prod']
        assert isinstance(prod_label, LabelRef)
        assert prod_label.version is None
        assert prod_label.ref == 'staging'


class TestVariablesConfigResolveSerializedValueCodeDefault:
    """Test resolve_serialized_value when labels point to code_default."""

    def test_code_default_variable_returns_none(self):
        config = VariablesConfig(
            variables={
                'test_var': VariableConfig(
                    name='test_var',
                    labels={'v1': LabelRef(ref='code_default')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        result = config.resolve_serialized_value('test_var')
        assert result.value is None
        assert result._reason == 'resolved'


class TestVariablesConfigValidationErrorsWithLatestVersion:
    """Test get_validation_errors validates latest_version values."""

    def test_invalid_latest_version_value(self, config_kwargs: dict[str, Any]):
        from logfire.variables.config import LatestVersion

        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='typed_var', default=0, type=int)

        config = VariablesConfig(
            variables={
                'typed_var': VariableConfig(
                    name='typed_var',
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                    latest_version=LatestVersion(version=1, serialized_value='"not_an_int"'),
                ),
            }
        )
        errors = config.get_validation_errors([var])
        assert 'typed_var' in errors
        assert 'latest' in errors['typed_var']

    def test_valid_latest_version_value(self, config_kwargs: dict[str, Any]):
        from logfire.variables.config import LatestVersion

        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='typed_var2', default=0, type=int)

        config = VariablesConfig(
            variables={
                'typed_var2': VariableConfig(
                    name='typed_var2',
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                    latest_version=LatestVersion(version=1, serialized_value='42'),
                ),
            }
        )
        errors = config.get_validation_errors([var])
        assert errors == {}

    def test_ref_only_label_skipped_in_validation(self, config_kwargs: dict[str, Any]):
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='typed_var3', default=0, type=int)

        config = VariablesConfig(
            variables={
                'typed_var3': VariableConfig(
                    name='typed_var3',
                    labels={
                        'v1': LabeledValue(version=1, serialized_value='42'),
                        'v2': LabelRef(version=2, ref='v1'),
                    },
                    rollout=Rollout(labels={}),
                    overrides=[],
                ),
            }
        )
        errors = config.get_validation_errors([var])
        assert errors == {}  # v1 is valid, v2 is skipped (ref-only)


class TestGetSerializedValueForLabelCodeDefault:
    """Test get_serialized_value_for_label when the label points to code_default."""

    def test_code_default_label_returns_none(self):
        config = VariablesConfig(
            variables={
                'test_var': VariableConfig(
                    name='test_var',
                    labels={'v1': LabelRef(ref='code_default')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(config)
        result = provider.get_serialized_value_for_label('test_var', 'v1')
        assert result.value is None
        assert result._reason == 'resolved'


class TestGetSerializedValueForLabelNotFound:
    """Test get_serialized_value_for_label when the label doesn't exist."""

    def test_missing_label_returns_none(self):
        config = VariablesConfig(
            variables={
                'test_var': VariableConfig(
                    name='test_var',
                    labels={'v1': LabeledValue(version=1, serialized_value='"value"')},
                    rollout=Rollout(labels={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        provider = LocalVariableProvider(config)
        result = provider.get_serialized_value_for_label('test_var', 'nonexistent')
        assert result.value is None
        assert result._reason == 'resolved'


class TestVariableGetWithExplicitLabel:
    """Test Variable.get() with explicit label parameter."""

    def test_explicit_label_resolves_successfully(self, config_kwargs: dict[str, Any]):
        variables_config = VariablesConfig(
            variables={
                'label_test': VariableConfig(
                    name='label_test',
                    labels={
                        'control': LabeledValue(version=1, serialized_value='"control_value"'),
                        'experiment': LabeledValue(version=2, serialized_value='"experiment_value"'),
                    },
                    rollout=Rollout(labels={'control': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='label_test', default='default', type=str)
        result = var.get(label='experiment')
        assert result.value == 'experiment_value'
        assert result.label == 'experiment'
        assert result.version == 2
        assert result._reason == 'resolved'

    def test_explicit_label_not_found_falls_through(self, config_kwargs: dict[str, Any]):
        variables_config = VariablesConfig(
            variables={
                'label_test2': VariableConfig(
                    name='label_test2',
                    labels={
                        'control': LabeledValue(version=1, serialized_value='"control_value"'),
                    },
                    rollout=Rollout(labels={'control': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='label_test2', default='default', type=str)
        # Label 'missing' doesn't exist, falls through to normal resolution
        result = var.get(label='missing')
        assert result.value == 'control_value'
        assert result.label == 'control'


# =============================================================================
# Test Lazy Variable Provider Initialization
# =============================================================================


class TestLazyVariableProviderInit:
    """Tests for lazy initialization of the variable provider when LOGFIRE_API_KEY is set."""

    def test_lazy_init_when_api_key_set(self, config_kwargs: dict[str, Any]) -> None:
        """When LOGFIRE_API_KEY is set but variables= is not passed, get_variable_provider()
        should lazily create a LogfireRemoteVariableProvider."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            lf = logfire.configure(**config_kwargs)
            config = lf.config

            # Before setting API key, should be NoOpVariableProvider
            assert isinstance(config._variable_provider, NoOpVariableProvider)
            assert config.variables is None

            # Set the API key in the environment
            with unittest.mock.patch.dict('os.environ', {'LOGFIRE_API_KEY': REMOTE_TOKEN}):
                provider = config.get_variable_provider()

            # Should now be a LogfireRemoteVariableProvider
            assert isinstance(provider, LogfireRemoteVariableProvider)
            assert isinstance(config._variable_provider, LogfireRemoteVariableProvider)
            # variables should still be None (unchanged)
            assert config.variables is None

            provider.shutdown()

    def test_no_lazy_init_when_api_key_absent(self, config_kwargs: dict[str, Any]) -> None:
        """When LOGFIRE_API_KEY is not set and variables= is not passed, get_variable_provider()
        should return NoOpVariableProvider."""
        lf = logfire.configure(**config_kwargs)
        config = lf.config

        # Ensure no API key is set
        with unittest.mock.patch.dict('os.environ', {}, clear=False):
            # Remove LOGFIRE_API_KEY if present
            env = dict(os.environ)
            env.pop('LOGFIRE_API_KEY', None)
            with unittest.mock.patch.dict('os.environ', env, clear=True):
                provider = config.get_variable_provider()

        # Should still be NoOpVariableProvider
        assert isinstance(provider, NoOpVariableProvider)

    def test_no_lazy_init_when_variables_explicitly_set(self, config_kwargs: dict[str, Any]) -> None:
        """When variables= is explicitly passed (e.g., LocalVariablesOptions), lazy init should
        not interfere even if LOGFIRE_API_KEY is set."""
        variables_config = VariablesConfig(
            variables={
                'test_var': VariableConfig(
                    name='test_var',
                    labels={},
                    rollout=Rollout(labels={}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = LocalVariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)
        config = lf.config

        # Even with API key set, should not lazily init because variables was explicitly passed
        with unittest.mock.patch.dict('os.environ', {'LOGFIRE_API_KEY': REMOTE_TOKEN}):
            provider = config.get_variable_provider()

        # Should be LocalVariableProvider, not LogfireRemoteVariableProvider
        assert isinstance(provider, LocalVariableProvider)

    def test_lazy_init_is_idempotent(self, config_kwargs: dict[str, Any]) -> None:
        """Calling get_variable_provider() multiple times should return the same provider."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            lf = logfire.configure(**config_kwargs)
            config = lf.config

            with unittest.mock.patch.dict('os.environ', {'LOGFIRE_API_KEY': REMOTE_TOKEN}):
                provider1 = config.get_variable_provider()
                provider2 = config.get_variable_provider()

            assert provider1 is provider2
            assert isinstance(provider1, LogfireRemoteVariableProvider)

            provider1.shutdown()

    def test_lazy_init_double_check_returns_early(self, config_kwargs: dict[str, Any]) -> None:
        """_lazy_init_variable_provider() returns early if provider is already set (double-check guard)."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={'variables': {}},
        )
        with request_mocker:
            lf = logfire.configure(**config_kwargs)
            config = lf.config

            # Perform lazy init to set the provider
            with unittest.mock.patch.dict('os.environ', {'LOGFIRE_API_KEY': REMOTE_TOKEN}):
                provider1 = config.get_variable_provider()
            assert isinstance(provider1, LogfireRemoteVariableProvider)

            # Now call _lazy_init_variable_provider() again — should hit the double-check guard
            provider2 = config._lazy_init_variable_provider()
            assert provider2 is provider1

            provider1.shutdown()


class TestConfigVariablesDictDeserialization:
    """Tests for LogfireConfig deserializing variables from a dict (as in executors.py)."""

    def test_variables_dict_with_config_no_variables_key(self) -> None:
        """When variables is a dict with 'config' as a dict that does NOT contain 'variables',
        it should deserialize into VariablesOptions(**config, **variables)."""
        from logfire._internal.config import LogfireConfig

        lf_config = LogfireConfig(variables={'config': {'block_before_first_resolve': False}})  # type: ignore
        assert isinstance(lf_config.variables, VariablesOptions)
        assert lf_config.variables.block_before_first_resolve is False
