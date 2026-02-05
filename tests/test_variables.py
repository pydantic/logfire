"""Tests for managed variables."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import time
import warnings
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

import pytest
import requests_mock as requests_mock_module
from pydantic import BaseModel, ValidationError

import logfire
from logfire._internal.config import RemoteVariablesConfig, VariablesOptions
from logfire.testing import TestExporter
from logfire.variables.abstract import NoOpVariableProvider, ResolvedVariable, VariableProvider
from logfire.variables.config import (
    KeyIsNotPresent,
    KeyIsPresent,
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
    Variant,
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

    def test_no_match_when_missing(self):
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'.*')
        assert condition.matches({}) is False

    def test_no_match_when_not_string(self):
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'.*')
        assert condition.matches({'email': 123}) is False

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
    def test_select_variant_deterministic_with_seed(self):
        rollout = Rollout(variants={'v1': 0.5, 'v2': 0.5})
        # With a seed, the result should be deterministic
        result1 = rollout.select_variant('user123')
        result2 = rollout.select_variant('user123')
        assert result1 == result2

    def test_select_variant_different_seeds_can_differ(self):
        rollout = Rollout(variants={'v1': 0.5, 'v2': 0.5})
        # Different seeds may produce different results
        results = {rollout.select_variant(f'user{i}') for i in range(100)}
        # With 50/50 split, we should see both variants
        assert results == {'v1', 'v2'}

    def test_select_variant_can_return_none(self):
        rollout = Rollout(variants={'v1': 0.3})  # 70% chance of None
        results = {rollout.select_variant(f'user{i}') for i in range(100)}
        # Should include None in results
        assert None in results
        assert 'v1' in results

    def test_select_variant_full_probability(self):
        rollout = Rollout(variants={'v1': 1.0})
        for i in range(10):
            assert rollout.select_variant(f'user{i}') == 'v1'

    def test_select_variant_without_seed(self):
        rollout = Rollout(variants={'v1': 0.5, 'v2': 0.5})
        # Without seed, still works but isn't deterministic
        result = rollout.select_variant(None)
        assert result in {'v1', 'v2'}

    def test_validation_sum_exceeds_one(self):
        # Note: Validation only runs when using TypeAdapter (not direct instantiation)
        with pytest.raises(ValidationError, match='Variant proportions must not sum to more than 1'):
            VariableConfig.model_validate({'rollout': {'variants': {'v1': 0.6, 'v2': 0.6}}})


# =============================================================================
# Test Variant
# =============================================================================


class TestVariant:
    def test_basic_variant(self):
        variant = Variant(key='v1', serialized_value='"hello"')
        assert variant.key == 'v1'
        assert variant.serialized_value == '"hello"'
        assert variant.description is None
        assert variant.version is None

    def test_variant_with_metadata(self):
        variant = Variant(
            key='v1',
            serialized_value='"hello"',
            description='Test variant',
            version=1,
        )
        assert variant.description == 'Test variant'
        assert variant.version == 1


# =============================================================================
# Test RolloutOverride
# =============================================================================


class TestRolloutOverride:
    def test_single_condition_override_applies_when_matched(self):
        """Test that override applies when single condition matches."""
        config = VariableConfig(
            name='test_var',
            variants={
                'default': Variant(key='default', serialized_value='"default_value"'),
                'premium': Variant(key='premium', serialized_value='"premium_value"'),
            },
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
        )

        # Without matching attribute, default rollout applies
        variant = config.resolve_variant(targeting_key='user1')
        assert variant is not None
        assert variant.key == 'default'

        # With matching attribute, override applies
        variant = config.resolve_variant(targeting_key='user1', attributes={'plan': 'enterprise'})
        assert variant is not None
        assert variant.key == 'premium'

        # With non-matching attribute, default rollout applies
        variant = config.resolve_variant(targeting_key='user1', attributes={'plan': 'free'})
        assert variant is not None
        assert variant.key == 'default'

    def test_multiple_conditions_require_all_to_match(self):
        """Test that all conditions must match for an override to apply (AND logic)."""
        config = VariableConfig(
            name='test_var',
            variants={
                'default': Variant(key='default', serialized_value='"default_value"'),
                'premium': Variant(key='premium', serialized_value='"premium_value"'),
            },
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[
                        ValueEquals(attribute='plan', value='enterprise'),
                        ValueIsIn(attribute='country', values=['US', 'UK']),
                    ],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
        )

        # Both conditions match -> override applies
        variant = config.resolve_variant(
            targeting_key='user1',
            attributes={'plan': 'enterprise', 'country': 'US'},
        )
        assert variant is not None
        assert variant.key == 'premium'

        # Only first condition matches -> override does not apply
        variant = config.resolve_variant(
            targeting_key='user1',
            attributes={'plan': 'enterprise', 'country': 'DE'},
        )
        assert variant is not None
        assert variant.key == 'default'

        # Only second condition matches -> override does not apply
        variant = config.resolve_variant(
            targeting_key='user1',
            attributes={'plan': 'free', 'country': 'UK'},
        )
        assert variant is not None
        assert variant.key == 'default'

        # Neither condition matches -> override does not apply
        variant = config.resolve_variant(
            targeting_key='user1',
            attributes={'plan': 'free', 'country': 'DE'},
        )
        assert variant is not None
        assert variant.key == 'default'

        # No attributes -> override does not apply
        variant = config.resolve_variant(targeting_key='user1')
        assert variant is not None
        assert variant.key == 'default'


# =============================================================================
# Test VariableConfig
# =============================================================================


class TestVariableConfig:
    @pytest.fixture
    def simple_config(self) -> VariableConfig:
        return VariableConfig(
            name='test_var',
            variants={
                'default': Variant(key='default', serialized_value='"default value"'),
                'experimental': Variant(key='experimental', serialized_value='"experimental value"'),
            },
            rollout=Rollout(variants={'default': 0.8, 'experimental': 0.2}),
            overrides=[],
        )

    @pytest.fixture
    def config_with_overrides(self) -> VariableConfig:
        return VariableConfig(
            name='test_var',
            variants={
                'default': Variant(key='default', serialized_value='"default value"'),
                'premium': Variant(key='premium', serialized_value='"premium value"'),
            },
            rollout=Rollout(variants={'default': 1.0}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'premium': 1.0}),
                ),
            ],
        )

    def test_resolve_variant_basic(self, simple_config: VariableConfig):
        # Deterministic selection with targeting_key
        variant = simple_config.resolve_variant(targeting_key='user123')
        assert variant is not None
        assert variant.key in {'default', 'experimental'}

    def test_resolve_variant_with_override(self, config_with_overrides: VariableConfig):
        # Without matching attributes, uses default rollout
        variant = config_with_overrides.resolve_variant(targeting_key='user1')
        assert variant is not None
        assert variant.key == 'default'

        # With matching attributes, uses override rollout
        variant = config_with_overrides.resolve_variant(
            targeting_key='user1',
            attributes={'plan': 'enterprise'},
        )
        assert variant is not None
        assert variant.key == 'premium'

    def test_resolve_variant_can_return_none(self):
        config = VariableConfig(
            name='test_var',
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 0.5}),  # 50% chance of None
            overrides=[],
        )
        # Try many times to get None
        results = [config.resolve_variant(targeting_key=f'user{i}') for i in range(100)]
        keys = {v.key if v else None for v in results}
        assert None in keys

    def test_validation_invalid_variant_key(self):
        with pytest.raises(ValidationError, match='invalid lookup key'):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'variants': {
                        'wrong_key': {'key': 'correct_key', 'serialized_value': '"value"'},
                    },
                    'rollout': {'variants': {'correct_key': 1.0}},
                    'overrides': [],
                }
            )

    def test_validation_rollout_references_missing_variant(self):
        with pytest.raises(ValidationError, match="Variant 'missing' present in `rollout.variants` is not present"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'variants': {
                        'v1': {'key': 'v1', 'serialized_value': '"value"'},
                    },
                    'rollout': {'variants': {'missing': 1.0}},
                    'overrides': [],
                }
            )

    def test_validation_override_references_missing_variant(self):
        with pytest.raises(ValidationError, match="Variant 'missing' present in `overrides"):
            VariableConfig.model_validate(
                {
                    'name': 'test',
                    'variants': {
                        'v1': {'key': 'v1', 'serialized_value': '"value"'},
                    },
                    'rollout': {'variants': {'v1': 1.0}},
                    'overrides': [
                        {
                            'conditions': [],
                            'rollout': {'variants': {'missing': 1.0}},
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                            'variants': {'v1': {'key': 'v1', 'serialized_value': '"value"'}},
                            'rollout': {'variants': {'v1': 1.0}},
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
                        'variants': {'v1': {'key': 'v1', 'serialized_value': '"value"'}},
                        'rollout': {'variants': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            }
        )
        assert isinstance(config, VariablesConfig)
        assert 'my_var' in config.variables

    def test_get_validation_errors_no_errors(self, config_kwargs: dict[str, Any]):
        """Test that get_validation_errors returns empty dict when all variants are valid."""
        lf = logfire.configure(**config_kwargs)
        config = VariablesConfig(
            variables={
                'valid_var': VariableConfig(
                    name='valid_var',
                    variants={'v1': Variant(key='v1', serialized_value='"valid_string"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"not_an_int"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
        assert str_config.variants == {}  # No variants created
        assert str_config.rollout.variants == {}  # Empty rollout
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
                    variants={'v1': Variant(key='v1', serialized_value='"value_a1"')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    variants={'v1': Variant(key='v1', serialized_value='"value_b1"')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[],
                ),
            }
        )
        config2 = VariablesConfig(
            variables={
                'var_b': VariableConfig(
                    name='var_b',
                    variants={'v2': Variant(key='v2', serialized_value='"value_b2"')},
                    rollout=Rollout(variants={'v2': 1.0}),
                    overrides=[],
                ),
                'var_c': VariableConfig(
                    name='var_c',
                    variants={'v1': Variant(key='v1', serialized_value='"value_c1"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
        assert 'v2' in merged.variables['var_b'].variants
        assert 'v1' not in merged.variables['var_b'].variants


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
        assert details.variant is None
        assert details.exception is None

    def test_with_variant(self):
        details = ResolvedVariable(name='test_var', value='test', variant='v1', _reason='resolved')
        assert details.variant == 'v1'

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
            # Value should be '<code_default>' since no variant was selected (no config)
            assert baggage_inside['logfire.variables.context_test_var'] == '<code_default>'

        # After exiting context, baggage should be unset
        baggage_after = logfire.get_baggage()
        assert 'logfire.variables.context_test_var' not in baggage_after

    def test_context_manager_sets_variant_name_in_baggage(self, config_kwargs: dict[str, Any]):
        variables_config = VariablesConfig(
            variables={
                'cm_var': VariableConfig(
                    name='cm_var',
                    variants={
                        'my_variant': Variant(key='my_variant', serialized_value='"variant_value"'),
                    },
                    rollout=Rollout(variants={'my_variant': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='cm_var', default='default', type=str)
        details = var.get()

        assert details.variant == 'my_variant'

        with details:
            baggage = logfire.get_baggage()
            assert baggage['logfire.variables.cm_var'] == 'my_variant'

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
                    variants={'a1': Variant(key='a1', serialized_value='"value_a"')},
                    rollout=Rollout(variants={'a1': 1.0}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    variants={'b1': Variant(key='b1', serialized_value='"value_b"')},
                    rollout=Rollout(variants={'b1': 1.0}),
                    overrides=[],
                ),
            }
        )
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
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
                    variants={
                        'default': Variant(key='default', serialized_value='"default_value"'),
                        'premium': Variant(key='premium', serialized_value='"premium_value"'),
                    },
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='plan', value='enterprise')],
                            rollout=Rollout(variants={'premium': 1.0}),
                        ),
                    ],
                ),
            }
        )

    def test_get_serialized_value_basic(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(simple_config)
        result = provider.get_serialized_value('test_var')
        assert result.value == '"default_value"'
        assert result.variant == 'default'
        assert result._reason == 'resolved'

    def test_get_serialized_value_with_override(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(simple_config)
        result = provider.get_serialized_value(
            'test_var',
            attributes={'plan': 'enterprise'},
        )
        assert result.value == '"premium_value"'
        assert result.variant == 'premium'

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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 0.0}),  # 0% chance
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
                        'variants': {
                            'default': {
                                'key': 'default',
                                'serialized_value': '"remote_value"',
                                'description': None,
                                'version': None,
                            }
                        },
                        'rollout': {'variants': {'default': 1.0}},
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
                config=RemoteVariablesConfig(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            try:
                result = provider.get_serialized_value('test_var')
                assert result.value == '"remote_value"'
                assert result.variant == 'default'
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
                config=RemoteVariablesConfig(
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
                        'variants': {
                            'default': {
                                'key': 'default',
                                'serialized_value': '"value"',
                            }
                        },
                        'rollout': {'variants': {'default': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
                    block_before_first_resolve=False,
                    polling_interval=timedelta(seconds=60),
                ),
            )
            provider.shutdown()
            provider.shutdown()  # Should not raise

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
                config=RemoteVariablesConfig(
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

    def test_rollout_returns_none_variant(self) -> None:
        """Test case where rollout returns None (no variant selected)."""
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'partial_var': {
                        'name': 'partial_var',
                        'variants': {
                            'v1': {
                                'key': 'v1',
                                'serialized_value': '"value"',
                            }
                        },
                        # 0% rollout means no variant is ever selected
                        'rollout': {'variants': {'v1': 0.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
                config=RemoteVariablesConfig(
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
        """Test that api_key can be specified in RemoteVariablesConfig."""
        api_key = 'test_api_key_12345'
        request_mocker = requests_mock_module.Mocker()
        request_mocker.get(
            'http://localhost:8000/v1/variables/',
            json={
                'variables': {
                    'test_var': {
                        'name': 'test_var',
                        'variants': {
                            'default': {
                                'key': 'default',
                                'serialized_value': '"api_key_value"',
                                'description': None,
                                'version': None,
                            }
                        },
                        'rollout': {'variants': {'default': 1.0}},
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
                config=RemoteVariablesConfig(
                    block_before_first_resolve=True,
                    polling_interval=timedelta(seconds=60),
                    api_key=api_key,
                ),
            )
            try:
                result = provider.get_serialized_value('test_var')
                assert result.value == '"api_key_value"'
                assert result.variant == 'default'
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
                    variants={
                        'default': Variant(key='default', serialized_value='"hello"'),
                        'alt': Variant(key='alt', serialized_value='"world"'),
                    },
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='use_alt', value=True)],
                            rollout=Rollout(variants={'alt': 1.0}),
                        ),
                    ],
                ),
                'int_var': VariableConfig(
                    name='int_var',
                    variants={'default': Variant(key='default', serialized_value='42')},
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[],
                ),
                'model_var': VariableConfig(
                    name='model_var',
                    variants={
                        'default': Variant(
                            key='default',
                            serialized_value='{"name": "test", "value": 123}',
                        )
                    },
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[],
                ),
                'invalid_var': VariableConfig(
                    name='invalid_var',
                    variants={'default': Variant(key='default', serialized_value='"not_an_int"')},
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[],
                ),
            }
        )

    def test_get_string_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        details = var.get()
        assert details.value == 'hello'

    def test_get_int_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='int_var', default=0, type=int)
        details = var.get()
        assert details.value == 42

    def test_get_model_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        class MyModel(BaseModel):
            name: str
            value: int

        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='model_var', default=MyModel(name='default', value=0), type=MyModel)
        details = var.get()
        assert details.value.name == 'test'
        assert details.value.value == 123

    def test_get_with_attributes(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        # Without override condition
        assert var.get().value == 'hello'

        # With override condition
        assert var.get(attributes={'use_alt': True}).value == 'world'

    def test_get_details(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        details = var.get()
        assert details.value == 'hello'
        assert details.variant == 'default'
        assert details.exception is None

    def test_get_details_with_validation_error(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='invalid_var', default=999, type=int)
        details = var.get()
        # Falls back to default when validation fails
        assert details.value == 999
        assert details.exception is not None
        assert details._reason == 'validation_error'

    def test_get_uses_default_when_no_config(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = VariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='unconfigured', default='my_default', type=str)
        value = var.get().value
        assert value == 'my_default'

    def test_override_context_manager(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        assert var.get().value == 'hello'

        with var.override('overridden'):
            assert var.get().value == 'overridden'

        assert var.get().value == 'hello'

    def test_override_nested(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        with var.override('outer'):
            assert var.get().value == 'outer'
            with var.override('inner'):
                assert var.get().value == 'inner'
            assert var.get().value == 'outer'

    def test_override_with_function(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
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
        config_kwargs['variables'] = VariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        def resolve_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            if targeting_key:
                return f'default_for_{targeting_key}'
            return 'generic_default'

        var = lf.var(name='with_fn_default', default=resolve_default, type=str)
        assert var.get().value == 'generic_default'
        assert var.get(targeting_key='user123').value == 'default_for_user123'

    def test_refresh_sync(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        var.refresh_sync()  # Should not raise

    @pytest.mark.anyio
    async def test_refresh_async(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        await var.refresh()  # Should not raise

    def test_get_creates_span_when_instrumented(
        self, config_kwargs: dict[str, Any], variables_config: VariablesConfig, exporter: TestExporter
    ):
        """Test that var.get() creates a span when instrument=True."""
        config_kwargs['variables'] = VariablesOptions(config=variables_config, instrument=True)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        exporter.clear()  # Clear any spans from configure

        details = var.get()

        # Verify the variable was resolved correctly
        assert details.value == 'hello'
        assert details.variant == 'default'

        # Verify a "Resolve variable string_var" span was created
        spans = exporter.exported_spans
        resolve_spans = [s for s in spans if s.name == 'Resolve variable string_var']
        assert len(resolve_spans) >= 1
        span = resolve_spans[-1]  # Get the most recent one
        # Verify span attributes
        attrs = dict(span.attributes or {})
        assert attrs.get('name') == 'string_var'
        assert attrs.get('value') == 'hello'
        assert attrs.get('variant') == 'default'

    def test_get_records_exception_on_span_when_validation_error(
        self, config_kwargs: dict[str, Any], variables_config: VariablesConfig, exporter: TestExporter
    ):
        """Test that validation errors are recorded on the span when instrument=True."""
        config_kwargs['variables'] = VariablesOptions(config=variables_config, instrument=True)
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
        config_kwargs['variables'] = VariablesOptions(config=variables_config, instrument=False)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        exporter.clear()  # Clear any spans from configure

        details = var.get()

        # Verify the variable was resolved correctly
        assert details.value == 'hello'
        assert details.variant == 'default'

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
                    variants={
                        'v1': Variant(key='v1', serialized_value='"value_1"'),
                        'v2': Variant(key='v2', serialized_value='"value_2"'),
                    },
                    # 50/50 split - targeting_key determines which variant
                    rollout=Rollout(variants={'v1': 0.5, 'v2': 0.5}),
                    overrides=[],
                ),
                'var_b': VariableConfig(
                    name='var_b',
                    variants={
                        'v1': Variant(key='v1', serialized_value='"b_value_1"'),
                        'v2': Variant(key='v2', serialized_value='"b_value_2"'),
                    },
                    rollout=Rollout(variants={'v1': 0.5, 'v2': 0.5}),
                    overrides=[],
                ),
            }
        )

    def test_targeting_context_default_for_all_variables(
        self, config_kwargs: dict[str, Any], rollout_config: VariablesConfig
    ):
        """targeting_context without variables sets targeting for all variables."""
        from logfire.variables.variable import targeting_context

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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

        config_kwargs['variables'] = VariablesOptions(config=rollout_config)
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
                    variants={
                        'default': Variant(key='default', serialized_value='"default"'),
                        'premium': Variant(key='premium', serialized_value='"premium"'),
                    },
                    rollout=Rollout(variants={'default': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[ValueEquals(attribute='plan', value='enterprise')],
                            rollout=Rollout(variants={'premium': 1.0}),
                        ),
                    ],
                ),
            }
        )

    def test_baggage_included_in_resolution(
        self, config_kwargs: dict[str, Any], config_with_targeting: VariablesConfig
    ):
        config_kwargs['variables'] = VariablesOptions(
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
        config_kwargs['variables'] = VariablesOptions(
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
        config_kwargs['variables'] = VariablesOptions(
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

    def test_invalid_param_names(self):
        def invalid_fn(key: str | None, attrs: Mapping[str, Any] | None) -> str:
            return 'value'  # pragma: no cover

        assert is_resolve_function(invalid_fn) is False

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
        config_kwargs['variables'] = VariablesOptions(
            config=VariablesConfig(
                variables={
                    'default_var': VariableConfig(
                        name='default_var',
                        variants={'v1': Variant(key='v1', serialized_value='"string_value"')},
                        rollout=Rollout(variants={'v1': 1.0}),
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

        lf = logfire.configure(variables=VariablesOptions(config=FailingProvider()))

        var = lf.var(name='failing_var', default='fallback', type=str)
        details = var.get()
        assert details.value == 'fallback'
        assert details._reason == 'other_error'
        assert isinstance(details.exception, RuntimeError)


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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
            variants={'v1': Variant(key='v1', serialized_value='"new_value"')},
            rollout=Rollout(variants={'v1': 1.0}),
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
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 1.0}),
            overrides=[],
        )
        with pytest.raises(VariableAlreadyExistsError, match="Variable 'existing_var' already exists"):
            provider.create_variable(duplicate_config)

    def test_update_variable_success(self, config_with_var: VariablesConfig):
        provider = LocalVariableProvider(config_with_var)
        updated_config = VariableConfig(
            name='existing_var',
            variants={'v2': Variant(key='v2', serialized_value='"updated_value"')},
            rollout=Rollout(variants={'v2': 1.0}),
            overrides=[],
        )
        result = provider.update_variable('existing_var', updated_config)
        assert result.variants['v2'].serialized_value == '"updated_value"'

    def test_update_variable_not_found(self, empty_config: VariablesConfig):
        from logfire.variables.abstract import VariableNotFoundError

        provider = LocalVariableProvider(empty_config)
        new_config = VariableConfig(
            name='nonexistent',
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 1.0}),
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
                        'variants': {'v1': {'key': 'v1', 'serialized_value': '"value"'}},
                        'rollout': {'variants': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                config=RemoteVariablesConfig(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
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
                        'variants': {'v1': {'key': 'v1', 'serialized_value': '"value"'}},
                        'rollout': {'variants': {'v1': 1.0}},
                        'overrides': [],
                    }
                }
            },
        )
        with request_mocker:
            provider = LogfireRemoteVariableProvider(
                base_url=REMOTE_BASE_URL,
                token=REMOTE_TOKEN,
                config=RemoteVariablesConfig(block_before_first_resolve=True, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='existing_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='new_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='my_var',
                    variants={'v2': Variant(key='v2', serialized_value='"updated"')},
                    rollout=Rollout(variants={'v2': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='nonexistent',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='my_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"', description='variant desc')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                ValueEquals(attribute='attr1', value='val1'),
                                ValueIsIn(attribute='attr2', values=['a', 'b']),
                                ValueMatchesRegex(attribute='attr3', pattern=r'test.*'),
                            ],
                            rollout=Rollout(variants={'v1': 1.0}),
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
                config=RemoteVariablesConfig(block_before_first_resolve=False, polling_interval=timedelta(seconds=60)),
            )
            try:
                config = VariableConfig(
                    name='test_var',
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[
                        RolloutOverride(
                            conditions=[
                                KeyIsPresent(attribute='must_exist'),
                                KeyIsNotPresent(attribute='must_not_exist'),
                            ],
                            rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"direct"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 1.0}),
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
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 1.0}),
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
            variants={'v1': Variant(key='v1', serialized_value='"old"')},
            rollout=Rollout(variants={'v1': 1.0}),
            overrides=[],
        )

        updates: dict[str, VariableConfig | None] = {
            'new_var': VariableConfig(
                name='new_var',
                variants={'v1': Variant(key='v1', serialized_value='"new"')},
                rollout=Rollout(variants={'v1': 1.0}),
                overrides=[],
            ),
            'existing': VariableConfig(
                name='existing',
                variants={'v2': Variant(key='v2', serialized_value='"updated"')},
                rollout=Rollout(variants={'v2': 1.0}),
                overrides=[],
            ),
            'to_delete': None,
        }
        # Add to_delete to configs first
        provider.configs['to_delete'] = VariableConfig(
            name='to_delete',
            variants={'v1': Variant(key='v1', serialized_value='"value"')},
            rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
        """Test push_variables with a function default (no default variant)."""

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
                    variants={'v1': Variant(key='v1', serialized_value='123')},
                    rollout=Rollout(variants={'v1': 1.0}),
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

    def test_push_variables_update_with_incompatible_variants(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables with incompatible variants warning."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    variants={'v1': Variant(key='v1', serialized_value='"not_an_int"')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[],
                    json_schema={'type': 'string'},
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        # Changing from string to int - existing variant is incompatible
        var = lf.var(name='my_var', default=0, type=int)
        result = provider.push_variables([var], yes=True)
        assert result is True
        captured = capsys.readouterr()
        assert 'Warning' in captured.out or 'Incompatible' in captured.out

    def test_push_variables_strict_mode_fails_with_incompatible(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables in strict mode fails with incompatible variants."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    variants={'v1': Variant(key='v1', serialized_value='"not_an_int"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
        """Test validate_variables with all valid variants."""
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    variants={'v1': Variant(key='v1', serialized_value='"valid_string"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={'v1': Variant(key='v1', serialized_value='"not_an_int"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
        assert result.errors[0].variant_key == 'v1'
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
                    variants={'v1': Variant(key='v1', serialized_value='"value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[],
                    description='Server description',
                ),
            }
        )
        provider = LocalVariableProvider(server_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='my_var', default='default', type=str, description='Local description')
        result = provider.validate_variables([var])
        # The variable is valid (variants match) but has description differences
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
    def test_push_variables_with_compatible_variants(
        self, capsys: pytest.CaptureFixture[str], config_kwargs: dict[str, Any]
    ):
        """Test push_variables when existing variants are compatible with the new schema."""
        # Server has a string variable with string variants
        server_config = VariablesConfig(
            variables={
                'my_var': VariableConfig(
                    name='my_var',
                    variants={'v1': Variant(key='v1', serialized_value='"compatible_value"')},
                    rollout=Rollout(variants={'v1': 1.0}),
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
                    variants={
                        'v1': Variant(
                            key='v1',
                            # This JSON won't validate against a complex Pydantic model
                            serialized_value='{"invalid": "structure", "with": "many", "fields": "that", "are": "wrong"}',
                        )
                    },
                    rollout=Rollout(variants={'v1': 1.0}),
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
        assert config.variants == {}
        assert config.rollout.variants == {}
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
# Test use_variant (explicit variant selection)
# =============================================================================


class TestUseVariant:
    """Tests for the use_variant context manager and variant parameter."""

    @pytest.fixture
    def variant_config(self) -> VariablesConfig:
        """Config with multiple variants."""
        return VariablesConfig(
            variables={
                'feature_var': VariableConfig(
                    name='feature_var',
                    variants={
                        'default': Variant(key='default', serialized_value='"default_value"'),
                        'experimental': Variant(key='experimental', serialized_value='"experimental_value"'),
                        'legacy': Variant(key='legacy', serialized_value='"legacy_value"'),
                    },
                    rollout=Rollout(variants={'default': 1.0}),  # 100% default
                    overrides=[],
                ),
            }
        )

    def test_get_with_variant_parameter(self, config_kwargs: dict[str, Any], variant_config: VariablesConfig):
        """Test getting a specific variant via the variant parameter."""
        config_kwargs['variables'] = VariablesOptions(config=variant_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='feature_var', default='code_default', type=str)

        # Without variant param, uses rollout (100% default)
        assert var.get().value == 'default_value'
        assert var.get().variant == 'default'

        # With variant param, bypasses rollout
        result = var.get(variant='experimental')
        assert result.value == 'experimental_value'
        assert result.variant == 'experimental'

        result = var.get(variant='legacy')
        assert result.value == 'legacy_value'
        assert result.variant == 'legacy'

    def test_get_with_nonexistent_variant(self, config_kwargs: dict[str, Any], variant_config: VariablesConfig):
        """Test that nonexistent variant falls back to normal resolution."""
        config_kwargs['variables'] = VariablesOptions(config=variant_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='feature_var', default='code_default', type=str)

        # Nonexistent variant should fall through to normal resolution
        result = var.get(variant='nonexistent')
        assert result.value == 'default_value'  # Falls back to rollout resolution
        assert result.variant == 'default'

    def test_use_variant_context_manager(self, config_kwargs: dict[str, Any], variant_config: VariablesConfig):
        """Test the use_variant context manager."""
        config_kwargs['variables'] = VariablesOptions(config=variant_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='feature_var', default='code_default', type=str)

        assert var.get().value == 'default_value'

        with var.use_variant('experimental'):
            assert var.get().value == 'experimental_value'
            assert var.get().variant == 'experimental'

        assert var.get().value == 'default_value'

    def test_use_variant_nested(self, config_kwargs: dict[str, Any], variant_config: VariablesConfig):
        """Test nested use_variant contexts."""
        config_kwargs['variables'] = VariablesOptions(config=variant_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='feature_var', default='code_default', type=str)

        with var.use_variant('experimental'):
            assert var.get().value == 'experimental_value'

            with var.use_variant('legacy'):
                assert var.get().value == 'legacy_value'

            assert var.get().value == 'experimental_value'

        assert var.get().value == 'default_value'

    def test_variant_param_overrides_context(self, config_kwargs: dict[str, Any], variant_config: VariablesConfig):
        """Test that call-site variant param overrides context."""
        config_kwargs['variables'] = VariablesOptions(config=variant_config)
        lf = logfire.configure(**config_kwargs)
        var = lf.var(name='feature_var', default='code_default', type=str)

        with var.use_variant('experimental'):
            # Context says experimental, but call-site says legacy
            result = var.get(variant='legacy')
            # Call-site variant wins (variant param is checked first in get method)
            # Actually, checking the code - the call-site variant is used directly
            assert result.value == 'legacy_value'
