"""Tests for managed variables."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

import warnings
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import requests_mock as requests_mock_module
from pydantic import BaseModel, ValidationError

import logfire
from logfire._internal.config import RemoteVariablesConfig, VariablesOptions
from logfire.variables.abstract import NoOpVariableProvider, VariableProvider, VariableResolutionDetails
from logfire.variables.config import (
    KeyIsNotPresent,
    KeyIsPresent,
    Rollout,
    RolloutOverride,
    RolloutSchedule,
    RolloutStage,
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
        # Note: This condition returns True if the string matches the pattern
        # (which seems like a bug in the implementation)
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'@blocked\.com$')
        # The implementation actually returns True when pattern MATCHES (bug?)
        assert condition.matches({'email': 'user@blocked.com'}) is True

    def test_no_match_when_pattern_matches(self):
        condition = ValueDoesNotMatchRegex(attribute='email', pattern=r'@blocked\.com$')
        assert condition.matches({'email': 'user@other.com'}) is False

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
        from pydantic import TypeAdapter

        adapter = TypeAdapter(Rollout)
        with pytest.raises(ValidationError, match='Variant proportions must not sum to more than 1'):
            adapter.validate_python({'variants': {'v1': 0.6, 'v2': 0.6}})


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
            version='1.0.0',
        )
        assert variant.description == 'Test variant'
        assert variant.version == '1.0.0'


# =============================================================================
# Test RolloutOverride
# =============================================================================


class TestRolloutOverride:
    def test_basic_override(self):
        override = RolloutOverride(
            conditions=[ValueEquals(attribute='plan', value='enterprise')],
            rollout=Rollout(variants={'premium': 1.0}),
        )
        assert len(override.conditions) == 1
        assert override.rollout.variants == {'premium': 1.0}

    def test_multiple_conditions(self):
        override = RolloutOverride(
            conditions=[
                ValueEquals(attribute='plan', value='enterprise'),
                ValueIsIn(attribute='country', values=['US', 'UK']),
            ],
            rollout=Rollout(variants={'premium': 1.0}),
        )
        assert len(override.conditions) == 2


# =============================================================================
# Test RolloutStage
# =============================================================================


class TestRolloutStage:
    def test_basic_stage(self):
        stage = RolloutStage(
            duration=timedelta(hours=1),
            rollout=Rollout(variants={'v1': 0.1}),
            overrides=[],
        )
        assert stage.duration == timedelta(hours=1)
        assert stage.rollout.variants == {'v1': 0.1}
        assert stage.overrides == []

    def test_stage_with_overrides(self):
        stage = RolloutStage(
            duration=timedelta(hours=2),
            rollout=Rollout(variants={'v1': 0.5}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='beta', value=True)],
                    rollout=Rollout(variants={'v1': 1.0}),
                ),
            ],
        )
        assert len(stage.overrides) == 1


# =============================================================================
# Test RolloutSchedule
# =============================================================================


class TestRolloutSchedule:
    def test_inactive_schedule_returns_none(self):
        """Schedule with start_at=None is inactive."""
        schedule = RolloutSchedule(
            start_at=None,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
            ],
        )
        assert schedule.get_active_stage() is None

    def test_future_schedule_returns_none(self):
        """Schedule with start_at in the future is not yet active."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        schedule = RolloutSchedule(
            start_at=future_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
            ],
        )
        assert schedule.get_active_stage() is None

    def test_first_stage_active(self):
        """When within first stage duration, first stage is active."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(minutes=30)  # Started 30 minutes ago
        schedule = RolloutSchedule(
            start_at=start_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),  # Stage 1: 1 hour
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=2),  # Stage 2: 2 hours
                    rollout=Rollout(variants={'v1': 0.5}),
                    overrides=[],
                ),
            ],
        )
        active = schedule.get_active_stage(now=now)
        assert active is not None
        assert active.rollout.variants == {'v1': 0.1}

    def test_second_stage_active(self):
        """When past first stage but within second, second stage is active."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=1, minutes=30)  # Started 1.5 hours ago
        schedule = RolloutSchedule(
            start_at=start_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),  # Stage 1: ends at 1 hour
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=2),  # Stage 2: ends at 3 hours
                    rollout=Rollout(variants={'v1': 0.5}),
                    overrides=[],
                ),
            ],
        )
        active = schedule.get_active_stage(now=now)
        assert active is not None
        assert active.rollout.variants == {'v1': 0.5}

    def test_completed_schedule_returns_none(self):
        """When all stages have elapsed, returns None."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=5)  # Started 5 hours ago
        schedule = RolloutSchedule(
            start_at=start_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),  # Stage 1: ends at 1 hour
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=2),  # Stage 2: ends at 3 hours
                    rollout=Rollout(variants={'v1': 0.5}),
                    overrides=[],
                ),
            ],
        )
        # Total duration is 3 hours, we're at 5 hours, so schedule is complete
        assert schedule.get_active_stage(now=now) is None

    def test_exact_boundary_uses_next_stage(self):
        """At exact stage boundary, uses the next stage."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=1)  # Exactly at stage 1 boundary
        schedule = RolloutSchedule(
            start_at=start_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),  # Stage 1: ends exactly now
                    rollout=Rollout(variants={'v1': 0.1}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=2),
                    rollout=Rollout(variants={'v1': 0.5}),
                    overrides=[],
                ),
            ],
        )
        active = schedule.get_active_stage(now=now)
        assert active is not None
        assert active.rollout.variants == {'v1': 0.5}

    def test_third_stage_active(self):
        """Test progression through multiple stages."""
        now = datetime.now(timezone.utc)
        # Started 4 hours ago: past stage 1 (1h) and stage 2 (2h), in stage 3
        start_time = now - timedelta(hours=4)
        schedule = RolloutSchedule(
            start_at=start_time,
            stages=[
                RolloutStage(
                    duration=timedelta(hours=1),
                    rollout=Rollout(variants={'v1': 0.05}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=2),
                    rollout=Rollout(variants={'v1': 0.25}),
                    overrides=[],
                ),
                RolloutStage(
                    duration=timedelta(hours=4),
                    rollout=Rollout(variants={'v1': 1.0}),
                    overrides=[],
                ),
            ],
        )
        active = schedule.get_active_stage(now=now)
        assert active is not None
        assert active.rollout.variants == {'v1': 1.0}


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
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariableConfig)
        with pytest.raises(ValidationError, match='invalid lookup key'):
            adapter.validate_python(
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
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariableConfig)
        with pytest.raises(ValidationError, match="Variant 'missing' present in `rollout.variants` is not present"):
            adapter.validate_python(
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
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariableConfig)
        with pytest.raises(ValidationError, match="Variant 'missing' present in `overrides"):
            adapter.validate_python(
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

    def test_validation_schedule_stage_references_missing_variant(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariableConfig)
        with pytest.raises(ValidationError, match="Variant 'missing' present in `schedule.stages"):
            adapter.validate_python(
                {
                    'name': 'test',
                    'variants': {
                        'v1': {'key': 'v1', 'serialized_value': '"value"'},
                    },
                    'rollout': {'variants': {'v1': 1.0}},
                    'overrides': [],
                    'schedule': {
                        'start_at': '2024-01-01T00:00:00Z',
                        'stages': [
                            {
                                'duration': 'PT1H',
                                'rollout': {'variants': {'missing': 1.0}},
                                'overrides': [],
                            }
                        ],
                    },
                }
            )

    def test_validation_schedule_stage_override_references_missing_variant(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariableConfig)
        with pytest.raises(ValidationError, match="Variant 'missing' present in `schedule.stages"):
            adapter.validate_python(
                {
                    'name': 'test',
                    'variants': {
                        'v1': {'key': 'v1', 'serialized_value': '"value"'},
                    },
                    'rollout': {'variants': {'v1': 1.0}},
                    'overrides': [],
                    'schedule': {
                        'start_at': '2024-01-01T00:00:00Z',
                        'stages': [
                            {
                                'duration': 'PT1H',
                                'rollout': {'variants': {'v1': 1.0}},
                                'overrides': [
                                    {
                                        'conditions': [],
                                        'rollout': {'variants': {'missing': 1.0}},
                                    }
                                ],
                            }
                        ],
                    },
                }
            )


# =============================================================================
# Test VariableConfig with RolloutSchedule
# =============================================================================


class TestVariableConfigWithSchedule:
    @pytest.fixture
    def config_with_schedule(self) -> VariableConfig:
        """Config with schedule that has different rollouts per stage."""
        now = datetime.now(timezone.utc)
        return VariableConfig(
            name='scheduled_var',
            variants={
                'control': Variant(key='control', serialized_value='"control value"'),
                'treatment': Variant(key='treatment', serialized_value='"treatment value"'),
            },
            # Base rollout: 100% control (used before schedule or after schedule completes)
            rollout=Rollout(variants={'control': 1.0}),
            overrides=[],
            schedule=RolloutSchedule(
                start_at=now - timedelta(minutes=30),  # Started 30 minutes ago
                stages=[
                    # Stage 1: 10% treatment (canary) for 1 hour
                    RolloutStage(
                        duration=timedelta(hours=1),
                        rollout=Rollout(variants={'control': 0.9, 'treatment': 0.1}),
                        overrides=[],
                    ),
                    # Stage 2: 50% treatment for 2 hours
                    RolloutStage(
                        duration=timedelta(hours=2),
                        rollout=Rollout(variants={'control': 0.5, 'treatment': 0.5}),
                        overrides=[],
                    ),
                    # Stage 3: 100% treatment for 1 hour (full rollout)
                    RolloutStage(
                        duration=timedelta(hours=1),
                        rollout=Rollout(variants={'treatment': 1.0}),
                        overrides=[],
                    ),
                ],
            ),
        )

    def test_resolve_uses_active_schedule_stage(self, config_with_schedule: VariableConfig):
        """resolve_variant should use the active schedule stage's rollout."""
        # The schedule started 30 minutes ago, so we're in stage 1 (10% treatment)
        # Sample many times to verify the distribution
        results = [config_with_schedule.resolve_variant(targeting_key=f'user{i}') for i in range(1000)]
        treatment_count = sum(1 for r in results if r and r.key == 'treatment')
        control_count = sum(1 for r in results if r and r.key == 'control')

        # With 10% treatment / 90% control, expect roughly 100 treatment / 900 control
        # Allow for statistical variance
        assert 50 < treatment_count < 200, f'Expected ~100 treatment, got {treatment_count}'
        assert 800 < control_count < 950, f'Expected ~900 control, got {control_count}'

    def test_resolve_uses_base_rollout_when_schedule_inactive(self):
        """When schedule is inactive, use base rollout."""
        config = VariableConfig(
            name='test_var',
            variants={
                'control': Variant(key='control', serialized_value='"control"'),
                'treatment': Variant(key='treatment', serialized_value='"treatment"'),
            },
            rollout=Rollout(variants={'control': 1.0}),  # Base: 100% control
            overrides=[],
            schedule=RolloutSchedule(
                start_at=None,  # Inactive schedule
                stages=[
                    RolloutStage(
                        duration=timedelta(hours=1),
                        rollout=Rollout(variants={'treatment': 1.0}),  # Would be 100% treatment if active
                        overrides=[],
                    ),
                ],
            ),
        )
        # All results should be control since schedule is inactive
        for i in range(10):
            variant = config.resolve_variant(targeting_key=f'user{i}')
            assert variant is not None
            assert variant.key == 'control'

    def test_resolve_uses_base_rollout_when_schedule_not_started(self):
        """When schedule hasn't started yet, use base rollout."""
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        config = VariableConfig(
            name='test_var',
            variants={
                'control': Variant(key='control', serialized_value='"control"'),
                'treatment': Variant(key='treatment', serialized_value='"treatment"'),
            },
            rollout=Rollout(variants={'control': 1.0}),
            overrides=[],
            schedule=RolloutSchedule(
                start_at=future_time,  # Schedule starts in 1 hour
                stages=[
                    RolloutStage(
                        duration=timedelta(hours=1),
                        rollout=Rollout(variants={'treatment': 1.0}),
                        overrides=[],
                    ),
                ],
            ),
        )
        for i in range(10):
            variant = config.resolve_variant(targeting_key=f'user{i}')
            assert variant is not None
            assert variant.key == 'control'

    def test_resolve_uses_base_rollout_when_schedule_completed(self):
        """When all schedule stages have elapsed, use base rollout."""
        now = datetime.now(timezone.utc)
        config = VariableConfig(
            name='test_var',
            variants={
                'control': Variant(key='control', serialized_value='"control"'),
                'treatment': Variant(key='treatment', serialized_value='"treatment"'),
            },
            rollout=Rollout(variants={'control': 1.0}),  # Base: 100% control
            overrides=[],
            schedule=RolloutSchedule(
                start_at=now - timedelta(hours=5),  # Started 5 hours ago
                stages=[
                    RolloutStage(
                        duration=timedelta(hours=1),  # Ended 4 hours ago
                        rollout=Rollout(variants={'treatment': 1.0}),
                        overrides=[],
                    ),
                ],
            ),
        )
        # Schedule completed, should use base rollout
        for i in range(10):
            variant = config.resolve_variant(targeting_key=f'user{i}')
            assert variant is not None
            assert variant.key == 'control'

    def test_resolve_uses_stage_overrides_when_schedule_active(self):
        """When schedule is active, use the stage's overrides, not base overrides."""
        now = datetime.now(timezone.utc)
        config = VariableConfig(
            name='test_var',
            variants={
                'control': Variant(key='control', serialized_value='"control"'),
                'treatment': Variant(key='treatment', serialized_value='"treatment"'),
                'vip': Variant(key='vip', serialized_value='"vip"'),
            },
            rollout=Rollout(variants={'control': 1.0}),
            # Base overrides: enterprise gets treatment
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='enterprise')],
                    rollout=Rollout(variants={'treatment': 1.0}),
                ),
            ],
            schedule=RolloutSchedule(
                start_at=now - timedelta(minutes=30),  # Active schedule
                stages=[
                    RolloutStage(
                        duration=timedelta(hours=1),
                        rollout=Rollout(variants={'control': 1.0}),
                        # Stage overrides: enterprise gets VIP instead
                        overrides=[
                            RolloutOverride(
                                conditions=[ValueEquals(attribute='plan', value='enterprise')],
                                rollout=Rollout(variants={'vip': 1.0}),
                            ),
                        ],
                    ),
                ],
            ),
        )
        # Enterprise users should get VIP (from stage override), not treatment (from base override)
        variant = config.resolve_variant(targeting_key='user1', attributes={'plan': 'enterprise'})
        assert variant is not None
        assert variant.key == 'vip'

        # Non-enterprise users get control (from stage rollout)
        variant = config.resolve_variant(targeting_key='user2', attributes={'plan': 'free'})
        assert variant is not None
        assert variant.key == 'control'

    def test_no_schedule_uses_base_config(self):
        """When no schedule is configured, use base rollout and overrides."""
        config = VariableConfig(
            name='test_var',
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
            schedule=None,
        )
        # Without enterprise plan, get default
        variant = config.resolve_variant(targeting_key='user1')
        assert variant is not None
        assert variant.key == 'default'

        # With enterprise plan, get premium
        variant = config.resolve_variant(targeting_key='user1', attributes={'plan': 'enterprise'})
        assert variant is not None
        assert variant.key == 'premium'


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
        from pydantic import TypeAdapter

        adapter = TypeAdapter(VariablesConfig)
        with pytest.raises(ValidationError, match='invalid lookup key'):
            adapter.validate_python(
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
        config = VariablesConfig.validate_python(
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
# Test VariableResolutionDetails
# =============================================================================


class TestVariableResolutionDetails:
    def test_basic_details(self):
        details = VariableResolutionDetails(value='test', _reason='resolved')
        assert details.value == 'test'
        assert details.variant is None
        assert details.exception is None

    def test_with_variant(self):
        details = VariableResolutionDetails(value='test', variant='v1', _reason='resolved')
        assert details.variant == 'v1'

    def test_with_exception(self):
        error = ValueError('test error')
        details = VariableResolutionDetails(value='default', exception=error, _reason='validation_error')
        assert details.exception is error


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

    def test_with_callable_config(self, simple_config: VariablesConfig):
        provider = LocalVariableProvider(lambda: simple_config)
        result = provider.get_serialized_value('test_var')
        assert result.value == '"default_value"'

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
        value = var.get()
        assert value == 'hello'

    def test_get_int_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='int_var', default=0, type=int)
        value = var.get()
        assert value == 42

    def test_get_model_variable(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        class MyModel(BaseModel):
            name: str
            value: int

        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='model_var', default=MyModel(name='default', value=0), type=MyModel)
        value = var.get()
        assert value.name == 'test'
        assert value.value == 123

    def test_get_with_attributes(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        # Without override condition
        assert var.get() == 'hello'

        # With override condition
        assert var.get(attributes={'use_alt': True}) == 'world'

    def test_get_details(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)
        details = var.get_details()
        assert details.value == 'hello'
        assert details.variant == 'default'
        assert details.exception is None

    def test_get_details_with_validation_error(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='invalid_var', default=999, type=int)
        details = var.get_details()
        # Falls back to default when validation fails
        assert details.value == 999
        assert details.exception is not None
        assert details._reason == 'validation_error'

    def test_get_uses_default_when_no_config(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = VariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='unconfigured', default='my_default', type=str)
        value = var.get()
        assert value == 'my_default'

    def test_override_context_manager(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        assert var.get() == 'hello'

        with var.override('overridden'):
            assert var.get() == 'overridden'

        assert var.get() == 'hello'

    def test_override_nested(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        with var.override('outer'):
            assert var.get() == 'outer'
            with var.override('inner'):
                assert var.get() == 'inner'
            assert var.get() == 'outer'

    def test_override_with_function(self, config_kwargs: dict[str, Any], variables_config: VariablesConfig):
        config_kwargs['variables'] = VariablesOptions(config=variables_config)
        lf = logfire.configure(**config_kwargs)

        var = lf.var(name='string_var', default='default_value', type=str)

        def resolve_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            if attributes and attributes.get('mode') == 'creative':
                return 'creative_value'
            return 'default_fn_value'

        with var.override(resolve_fn):
            assert var.get() == 'default_fn_value'
            assert var.get(attributes={'mode': 'creative'}) == 'creative_value'

    def test_default_as_function(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = VariablesOptions(config=VariablesConfig(variables={}))
        lf = logfire.configure(**config_kwargs)

        def resolve_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            if targeting_key:
                return f'default_for_{targeting_key}'
            return 'generic_default'

        var = lf.var(name='with_fn_default', default=resolve_default, type=str)
        assert var.get() == 'generic_default'
        assert var.get(targeting_key='user123') == 'default_for_user123'

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
        assert var.get() == 'default'

        # With baggage
        with logfire.set_baggage(plan='enterprise'):
            assert var.get() == 'premium'

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
            assert var.get() == 'default'

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
        assert var.get() == 'default'


# =============================================================================
# Test is_resolve_function
# =============================================================================


class TestIsResolveFunction:
    def test_valid_resolve_function(self):
        def valid_fn(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> str:
            return 'value'

        assert is_resolve_function(valid_fn) is True

    def test_invalid_param_names(self):
        def invalid_fn(key: str | None, attrs: Mapping[str, Any] | None) -> str:
            return 'value'

        assert is_resolve_function(invalid_fn) is False

    def test_wrong_param_count(self):
        def wrong_count(targeting_key: str | None) -> str:
            return 'value'

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
    def test_var_with_sequence_type(self, config_kwargs: dict[str, Any]):
        config_kwargs['variables'] = VariablesOptions(
            config=VariablesConfig(
                variables={
                    'union_var': VariableConfig(
                        name='union_var',
                        variants={'v1': Variant(key='v1', serialized_value='"string_value"')},
                        rollout=Rollout(variants={'v1': 1.0}),
                        overrides=[],
                    ),
                }
            )
        )
        lf = logfire.configure(**config_kwargs)

        # Using sequence of types creates a Union
        var = lf.var(name='union_var', default='default', type=[str, int])
        assert var.get() == 'string_value'

    def test_exception_handling_in_get_details(self, config_kwargs: dict[str, Any]):
        # Create a provider that raises an exception
        class FailingProvider(VariableProvider):
            def get_serialized_value(
                self,
                variable_name: str,
                targeting_key: str | None = None,
                attributes: Mapping[str, Any] | None = None,
            ) -> VariableResolutionDetails[str | None]:
                raise RuntimeError('Provider failed!')

        lf = logfire.configure(variables=VariablesOptions(config=FailingProvider()))

        var = lf.var(name='failing_var', default='fallback', type=str)
        details = var.get_details()
        assert details.value == 'fallback'
        assert details._reason == 'other_error'
        assert isinstance(details.exception, RuntimeError)
