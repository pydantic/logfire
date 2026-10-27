from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import contextvars
import json
import math
import os
import threading
import warnings
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, ExitStack
from dataclasses import replace
from datetime import timedelta
from typing import Annotated, Any, Literal, cast
from unittest.mock import Mock, patch

import hypothesis.strategies as st
import pytest
import requests_mock as requests_mock_module
from hypothesis import given, settings
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,  # pyright: ignore[reportUnknownVariableType]
)
from opentelemetry import trace
from pydantic import AfterValidator, BaseModel, Field, PlainSerializer, RootModel, ValidationError

import logfire
from logfire._internal import trace_scope
from logfire._internal.config import LocalVariablesOptions, VariablesOptions
from logfire.experimental.feature_flags import (
    Flag,
    FlagEvaluationDetails,
    feature_context,
    flag as create_flag,
)
from logfire.testing import TestExporter
from logfire.variables import (
    LabeledValue,
    Rollout,
    RolloutOverride,
    ValueEquals,
    VariableConfig,
    VariablesConfig,
    targeting_context,
)
from logfire.variables.abstract import ResolvedVariable
from logfire.variables.remote import LogfireRemoteVariableProvider
from logfire.variables.variable import (
    _VARIABLE_OVERRIDES,
    _feature_flag_evaluation_details,
    _feature_flag_telemetry_attributes,
    _feature_flag_telemetry_value,
    _FlagEvaluationCore,
    _scrub_feature_flag_result,
)

MUTATION_TESTING = 'MUTANT_UNDER_TEST' in os.environ


def _finished_flag_spans(exporter: TestExporter) -> list[Any]:
    return [
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    ]


def test_flag_scrubbing_tolerates_an_already_omitted_value():
    assert _scrub_feature_flag_result({}, 'api_key', 'secret', logfire.DEFAULT_LOGFIRE_INSTANCE) == {
        'logfire.feature_flag.result.value_status': 'scrubbed'
    }


def test_rejected_flag_values_do_not_bypass_name_aware_scrubbing(config_kwargs: dict[str, Any], exporter: TestExporter):
    config = VariablesConfig(
        variables={
            'api_key': VariableConfig(
                name='api_key',
                labels={'bad': LabeledValue(version=1, serialized_value='{"value":"opaque-928413"}')},
                rollout=Rollout(labels={'bad': 1.0}),
                overrides=[],
            ),
        }
    )
    logfire.configure(variables=LocalVariablesOptions(config=config), **config_kwargs)
    secret = create_flag('api_key', default='')
    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = secret.details()
    assert details.value == ''
    assert details.error_code == 'type_mismatch'
    spans = _finished_flag_spans(exporter)
    assert len(spans) == 1
    assert 'opaque-928413' not in repr([dict(span.attributes or {}) for span in exporter.exported_spans])
    assert 'invalid_serialized_value' not in spans[0].attributes


DETERMINISTIC_PROPERTY_SETTINGS = settings(
    max_examples=60 if MUTATION_TESTING else 300,
    derandomize=True,
    deadline=None,
)
ROLLOUT_PARTS = st.tuples(*(st.integers(min_value=0, max_value=100) for _ in range(3))).filter(
    lambda parts: sum(parts) <= 100
)


def _boolean_config(*, rollout: Rollout, overrides: list[RolloutOverride] | None = None) -> VariablesConfig:
    return VariablesConfig(
        variables={
            'test_flag': VariableConfig(
                name='test_flag',
                labels={
                    'enabled': LabeledValue(version=2, serialized_value='true'),
                    'disabled': LabeledValue(version=1, serialized_value='false'),
                    'alternate': LabeledValue(version=3, serialized_value='true'),
                },
                rollout=rollout,
                overrides=overrides or [],
            )
        }
    )


def _code_default_config(*names: str) -> VariablesConfig:
    """Configure flags whose rollout selects the code default, so they exist but have no value."""
    return VariablesConfig(
        variables={
            name: VariableConfig(name=name, labels={}, rollout=Rollout(labels={}), overrides=[]) for name in names
        }
    )


def _rollout_from_parts(parts: tuple[int, int, int]) -> Rollout:
    return Rollout(
        labels={
            'enabled': parts[0] / 100,
            'disabled': parts[1] / 100,
            'alternate': parts[2] / 100,
        }
    )


def test_feature_flag_api_is_experimental():
    from logfire.experimental import feature_flags

    assert set(feature_flags.__all__) == {
        'Flag',
        'FlagErrorCode',
        'FlagEvaluationDetails',
        'FlagEvaluationReason',
        'feature_context',
        'flag',
    }
    assert not hasattr(feature_flags, 'feature_flag')
    assert not hasattr(feature_flags, 'FeatureFlag')
    assert not hasattr(logfire, 'flag')
    assert not hasattr(logfire, 'feature_flag')
    assert not hasattr(logfire, 'feature_context')


@pytest.mark.parametrize('constructor', [create_flag, Flag])
def test_boolean_flag_rejects_non_boolean_defaults(constructor: Any):
    with pytest.raises(ValidationError):
        constructor('not_really_boolean', type=bool, default=1)


@pytest.mark.parametrize(
    ('result', 'config', 'attributes', 'expected_reason', 'expected_error'),
    [
        (
            ResolvedVariable(name='test_flag', value=False, reason='code_default'),
            None,
            {},
            'default',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=True, reason='context_override'),
            None,
            {},
            'context_override',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=True, reason='resolved'),
            None,
            {},
            'static',
            None,
        ),
        (
            ResolvedVariable(
                name='test_flag',
                value=False,
                label='invalid',
                version=9,
                reason='validation_error',
                exception=ValueError(),
            ),
            None,
            {},
            'error',
            'type_mismatch',
        ),
        (
            ResolvedVariable(name='test_flag', value=False, reason='other_error'),
            None,
            {},
            'error',
            'general',
        ),
        (
            ResolvedVariable(name='test_flag', value=False, reason='code_default', exception=RuntimeError()),
            None,
            {},
            'error',
            'general',
        ),
        (
            ResolvedVariable(name='test_flag', value=True, label='enabled', version=2, reason='resolved'),
            _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5})).variables['test_flag'],
            {},
            'split',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=False, reason='code_default'),
            _boolean_config(rollout=Rollout(labels={'enabled': 0.5})).variables['test_flag'],
            {},
            'split',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=False, label='disabled', version=1, reason='resolved'),
            _boolean_config(
                rollout=Rollout(labels={'enabled': 1.0}),
                overrides=[
                    RolloutOverride(
                        conditions=[ValueEquals(attribute='plan', value='free')],
                        rollout=Rollout(labels={'disabled': 1.0}),
                    )
                ],
            ).variables['test_flag'],
            {'plan': 'free'},
            'targeting_match',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=False, reason='code_default'),
            _boolean_config(
                rollout=Rollout(labels={'enabled': 1.0}),
                overrides=[
                    RolloutOverride(
                        conditions=[ValueEquals(attribute='plan', value='free')],
                        rollout=Rollout(labels={}),
                    )
                ],
            ).variables['test_flag'],
            {'plan': 'free'},
            'default',
            None,
        ),
        (
            ResolvedVariable(name='test_flag', value=True, label='enabled', version=2, reason='resolved'),
            _boolean_config(rollout=Rollout(labels={'enabled': 1.0, 'disabled': 0.0, 'alternate': 0.0})).variables[
                'test_flag'
            ],
            {},
            'static',
            None,
        ),
    ],
)
def test_feature_flag_telemetry_translation(
    result: ResolvedVariable[bool],
    config: VariableConfig | None,
    attributes: Mapping[str, object],
    expected_reason: str,
    expected_error: str | None,
):
    if config is not None:
        result = replace(result, rule_evaluation_reason=config.rule_evaluation_reason(attributes))
    telemetry = _feature_flag_telemetry_attributes(result)
    details = _feature_flag_evaluation_details(result)
    expected_variant = None if expected_error else result.label
    expected_version = None if expected_error else result.version

    assert details.value is result.value
    assert details.variant == expected_variant
    assert details.flag_metadata == (
        {'logfire.value_version': expected_version} if expected_version is not None else {}
    )
    assert details.reason == expected_reason
    assert details.error_code == expected_error
    assert telemetry['feature_flag.key'] == result.name
    assert telemetry['feature_flag.provider.name'] == 'logfire'
    assert 'feature_flag.result.value' not in telemetry
    assert telemetry['feature_flag.result.reason'] == expected_reason
    assert telemetry['logfire.feature_flag.resolution_reason'] == result.reason
    assert telemetry.get('error.type') == expected_error
    assert telemetry.get('feature_flag.error.message') == details.error_message
    assert telemetry.get('feature_flag.result.variant') == expected_variant
    assert telemetry.get('logfire.feature_flag.value_version') == expected_version
    assert 'feature_flag.version' not in telemetry
    if result.reason == 'validation_error':
        assert details.error_message == 'Configured value did not match the declared flag type.'
    elif expected_reason == 'error':
        assert details.error_message == 'Feature flag evaluation failed.'
    else:
        assert details.error_message is None


def test_feature_flag_telemetry_defaults_custom_provider_results_to_static():
    result = ResolvedVariable(name='test_flag', value=True, reason='resolved')

    details = _feature_flag_evaluation_details(result)

    assert details.value is True
    assert details.reason == 'static'


@pytest.mark.parametrize(
    ('provider_state', 'expected_reason', 'expected_error', 'expected_message'),
    [
        ('ready', 'default', None, None),
        ('stale', 'stale', None, None),
        ('not_ready', 'error', 'provider_not_ready', 'The feature flag provider has not loaded configuration yet.'),
        ('error', 'error', 'general', 'The feature flag provider could not load configuration.'),
        ('fatal', 'error', 'provider_fatal', 'The feature flag provider is no longer available.'),
    ],
)
def test_feature_flag_provider_state_translation(
    provider_state: Any,
    expected_reason: str,
    expected_error: str | None,
    expected_message: str | None,
):
    details = _feature_flag_evaluation_details(
        ResolvedVariable(name='test_flag', value=False, reason='code_default'),
        provider_state,
    )

    assert details.value is False
    assert details.reason == expected_reason
    assert details.error_code == expected_error
    assert details.error_message == expected_message


def test_feature_flag_provider_state_translation_rejects_unknown_state():
    with pytest.raises(AssertionError, match='not-a-provider-state'):
        _feature_flag_evaluation_details(
            ResolvedVariable(name='test_flag', value=False, reason='code_default'),
            cast(Any, 'not-a-provider-state'),
        )


@pytest.mark.parametrize('reason', ['validation_error', 'context_override', 'other_error'])
def test_feature_flag_existing_outcome_does_not_consult_unknown_provider_state(reason: Any):
    details = _feature_flag_evaluation_details(
        ResolvedVariable(name='test_flag', value=False, reason=reason),
        cast(Any, 'not-a-provider-state'),
    )
    assert details.reason == ('context_override' if reason == 'context_override' else 'error')


def test_rollout_warning_inspection_cannot_break_a_resolved_value():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    test_flag = create_flag('test_flag', default=False)

    with patch.object(VariableConfig, 'requires_targeting_key', side_effect=ValueError('malformed targeting metadata')):
        assert isinstance(test_flag.value(), bool)


@DETERMINISTIC_PROPERTY_SETTINGS
@given(parts=ROLLOUT_PARTS, targeting_key=st.text(min_size=0, max_size=80))
def test_rollout_resolution_is_deterministic_and_selects_only_possible_outcomes(
    parts: tuple[int, int, int], targeting_key: str
):
    config = _boolean_config(rollout=_rollout_from_parts(parts)).variables['test_flag']

    outcomes = {config.resolve_label(targeting_key) for _ in range(10)}

    assert len(outcomes) == 1
    outcome = outcomes.pop()
    if outcome is None:
        assert sum(parts) < 100
    else:
        assert parts[('enabled', 'disabled', 'alternate').index(outcome)] > 0


@DETERMINISTIC_PROPERTY_SETTINGS
@given(parts=ROLLOUT_PARTS)
def test_targeting_key_requirement_matches_the_number_of_possible_outcomes(parts: tuple[int, int, int]):
    config = _boolean_config(rollout=_rollout_from_parts(parts)).variables['test_flag']
    expected_outcome_count = sum(part > 0 for part in parts) + (sum(parts) < 100)

    assert config.requires_targeting_key() is (expected_outcome_count > 1)


def test_falsey_attribute_mapping_is_not_discarded():
    class FalseyAttributes(dict[str, object]):
        def __bool__(self) -> bool:
            return False

    variables_config = _boolean_config(
        rollout=Rollout(labels={'enabled': 1.0}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='plan', value='free')],
                rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}),
            )
        ],
    )
    config = variables_config.variables['test_flag']
    attributes = FalseyAttributes(plan='free')

    assert config.requires_targeting_key(attributes) is True
    config.overrides[0].rollout = Rollout(labels={'disabled': 1.0})
    assert config.resolve_label('account-a', attributes) == 'disabled'

    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=variables_config, instrument=False),
    )
    test_flag = create_flag('test_flag', default=False)
    assert test_flag.details(targeting_key='account-a', attributes=attributes).variant == 'disabled'
    with feature_context('account-a', attributes=attributes):
        assert test_flag.details().variant == 'disabled'


def test_deterministic_rollout_population_tracks_configured_weights():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.7, 'disabled': 0.2, 'alternate': 0.05})).variables[
        'test_flag'
    ]

    sample_size = 1_000 if MUTATION_TESTING else 10_000
    counts = Counter(config.resolve_label(f'user-{index}') for index in range(sample_size))

    tolerance = 0.04 if MUTATION_TESTING else 0.02
    rare_tolerance = 0.025 if MUTATION_TESTING else 0.01
    assert counts['enabled'] / sample_size == pytest.approx(0.7, abs=tolerance)
    assert counts['disabled'] / sample_size == pytest.approx(0.2, abs=tolerance)
    assert counts['alternate'] / sample_size == pytest.approx(0.05, abs=rare_tolerance)
    assert counts[None] / sample_size == pytest.approx(0.05, abs=rare_tolerance)


def test_feature_flag_preserves_description():
    config = _boolean_config(rollout=Rollout(labels={'disabled': 1.0}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False, description='Enable the new checkout.')

    assert isinstance(flag, Flag)
    assert flag.description == 'Enable the new checkout.'
    assert not hasattr(flag, 'get')
    details = flag.details(targeting_key='account-a')
    assert details.flag_key == 'test_flag'
    assert details.value is False
    assert details.variant == 'disabled'
    assert details.reason == 'static'
    assert details.flag_metadata == {'logfire.value_version': 1}


@pytest.mark.parametrize('default', [False, 'eu', 3])
def test_flags_expose_only_value_and_details(default: Any):
    checkout = create_flag('checkout', default=default)

    assert checkout.value() == default
    assert checkout.details().value == default
    assert not hasattr(checkout, 'evaluate')
    assert not hasattr(checkout, 'is_enabled')


def test_value_forwards_an_explicit_targeting_key():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    enabled_key = next(
        f'account-{index}'
        for index in range(100)
        if config.variables['test_flag'].resolve_label(f'account-{index}') == 'enabled'
    )
    test_flag = create_flag('test_flag', default=False)

    assert test_flag.value(targeting_key=enabled_key) is True


def test_value_forwards_the_complete_evaluation_context():
    adapter = Mock()
    adapter.name = 'region'
    adapter.evaluate_flag.return_value = FlagEvaluationDetails(flag_key='region', value='eu', reason='static')
    custom_logfire = Mock()
    custom_logfire._flag.return_value = adapter
    region = Flag('region', default='us', logfire_instance=custom_logfire)
    attributes = {'plan': 'team'}

    assert region.value(targeting_key='account-a', attributes=attributes) == 'eu'

    adapter.evaluate_flag.assert_called_once_with('account-a', attributes)


def test_feature_context_wins_over_generic_context_but_not_variable_specific_context():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    keys = {
        label: next(
            f'account-{index}'
            for index in range(100)
            if config.variables['test_flag'].resolve_label(f'account-{index}') == label
        )
        for label in ('enabled', 'disabled')
    }
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    test_flag = create_flag('test_flag', default=False)

    with feature_context(keys['enabled']):
        with targeting_context(keys['disabled']):
            assert test_flag.details().variant == 'enabled'
        with targeting_context(keys['disabled'], variables=[test_flag]):
            assert test_flag.details().variant == 'disabled'


def test_feature_flag_falls_back_to_generic_targeting_context():
    test_flag = create_flag('test_flag', default=False)
    adapter = cast(Any, test_flag._adapter)

    with targeting_context('generic-account'):
        assert adapter._get_context_targeting_key() == 'generic-account'

    assert adapter._get_context_targeting_key() is None


def test_feature_flag_uses_the_explicit_logfire_instance():
    adapter = Mock()
    custom_logfire = Mock()
    custom_logfire._flag.return_value = adapter

    create_flag('test_flag', default=False, logfire_instance=custom_logfire)

    custom_logfire._flag.assert_called_once_with('test_flag', type=bool, default=False, description=None)


class CheckoutConfig(BaseModel):
    provider: str
    retries: int


class AgentConfigV1(BaseModel):
    schema_version: Literal[1] = 1
    model: str | None = None


class AgentConfigV2(BaseModel):
    schema_version: Literal[2] = 2
    model: str | None = None
    instructions: list[str] = Field(default_factory=list)


class AgentConfig(RootModel[Annotated[AgentConfigV1 | AgentConfigV2, Field(discriminator='schema_version')]]):
    pass


class SecretConfig(BaseModel):
    api_key: str


class JsonOnlySecretConfig(BaseModel):
    payload: Annotated[
        str,
        PlainSerializer(lambda value: {'api_key': value}, return_type=dict[str, str], when_used='json'),
    ]


def test_typed_flag_validates_pydantic_models_and_overrides():
    config = VariablesConfig(
        variables={
            'checkout': VariableConfig(
                name='checkout',
                labels={
                    'fast': LabeledValue(
                        version=1,
                        serialized_value='{"provider":"stripe","retries":3}',
                    )
                },
                rollout=Rollout(labels={'fast': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    checkout = create_flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))

    assert checkout.value() == CheckoutConfig(provider='stripe', retries=3)
    assert checkout.details().variant == 'fast'
    with checkout.override(CheckoutConfig(provider='test', retries=0)):
        assert checkout.value() == CheckoutConfig(provider='test', retries=0)


@pytest.mark.parametrize('state', ['ready', 'not_ready', 'stale', 'error', 'fatal'])
def test_feature_flag_default_is_normalized_once(state: str):
    calls: list[int] = []

    def normalize(value: int) -> int:
        calls.append(value)
        return value + 1

    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    setting = create_flag('normalized', type=cast(Any, Annotated[int, AfterValidator(normalize)]), default=1)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()

    with patch.object(provider, 'get_evaluation_state', return_value=state):
        assert setting.value() == 2
        assert setting.details().value == 2
    assert calls == [1]


@pytest.mark.parametrize('invalid', [False, True])
def test_feature_flag_remote_value_is_normalized_once(invalid: bool):
    calls: list[int] = []

    def normalize(value: int) -> int:
        calls.append(value)
        return value + 1

    config = VariablesConfig(
        variables={
            'normalized': VariableConfig(
                name='normalized',
                labels={'live': LabeledValue(version=1, serialized_value='"invalid"' if invalid else '5')},
                rollout=Rollout(labels={'live': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    setting = create_flag('normalized', type=cast(Any, Annotated[int, AfterValidator(normalize)]), default=1)
    if invalid:
        with pytest.warns(RuntimeWarning, match='value failed validation'):
            details = setting.details()
        assert details.value == 2
        assert details.error_code == 'type_mismatch'
        assert calls == [1]
    else:
        details = setting.details()
        assert details.value == 6
        assert details.error_code is None
        assert calls == [1, 5]


@pytest.mark.parametrize('compatibility_api', [False, True])
def test_feature_flag_override_is_normalized_once_and_restored(compatibility_api: bool):
    calls: list[int] = []

    def normalize(value: int) -> int:
        calls.append(value)
        return value + 1

    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    setting = create_flag('normalized', type=cast(Any, Annotated[int, AfterValidator(normalize)]), default=0)
    manager = logfire.variables_get()[0].override(1) if compatibility_api else setting.override(1)
    # Both override APIs validate the value when the override is created.
    assert calls == [0, 1]
    assert setting.value() == 1
    with manager:
        assert setting.value() == 2
        assert setting.details().value == 2
        with setting.override(10):
            assert setting.value() == 11
        assert setting.value() == 2
        with pytest.raises(RuntimeError, match='cancelled'):
            with setting.override(20):
                assert setting.value() == 21
                raise RuntimeError('cancelled')
        assert setting.value() == 2
    assert setting.value() == 1
    assert calls == [0, 1, 10, 20]


@pytest.mark.parametrize('other_override', [False, True])
def test_feature_flag_provider_override_is_validated_without_a_local_override(other_override: bool):
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    setting = create_flag(
        'normalized', type=cast(Any, Annotated[int, AfterValidator(lambda value: value + 1)]), default=0
    )
    other = create_flag('other', default=False)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()
    with (
        ExitStack() as stack,
        patch.object(
            provider,
            'get_serialized_value',
            return_value=ResolvedVariable(name='normalized', value='5', reason='context_override'),
        ),
    ):
        if other_override:
            stack.enter_context(other.override(True))
        assert setting.value() == 6


def test_feature_flag_overrides_are_isolated_from_other_instances_and_legacy_variables():
    options = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False)
    left = logfire.configure(local=True, send_to_logfire=False, console=False, variables=options)
    right = logfire.configure(local=True, send_to_logfire=False, console=False, variables=options)
    legacy = logfire.configure(local=True, send_to_logfire=False, console=False, variables=options)
    try:
        left_flag = create_flag('shared_key', default=False, logfire_instance=left)
        right_flag = create_flag('shared_key', default=False, logfire_instance=right)
        legacy_variable = legacy.var('shared_key', default=False)
        composed = left.var('message', default='flag=@{shared_key}@')

        with left_flag.override(True):
            assert left_flag.value() is True
            assert right_flag.value() is False
            assert legacy_variable.get().value is False
            assert composed.get().value == 'flag=true'
            with right_flag.override(False):
                assert left_flag.value() is True
                assert right_flag.value() is False
        with legacy_variable.override(True):
            assert legacy_variable.get().value is True
            assert left_flag.value() is False
            assert right_flag.value() is False
        assert left_flag.value() is False
        assert right_flag.value() is False
        assert legacy_variable.get().value is False
    finally:
        left.shutdown()
        right.shutdown()
        legacy.shutdown()


def test_feature_flag_defaults_and_overrides_still_compose():
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    logfire.var('region', default='eu')
    setting = create_flag('message', default='Hello @{region}@')
    assert setting.value() == 'Hello eu'
    with setting.override('Goodbye @{region}@'):
        assert setting.value() == 'Goodbye eu'
    assert setting.value() == 'Hello eu'


def test_typed_flag_supports_versioned_discriminated_models():
    fallback = AgentConfig(AgentConfigV1(model='fallback'))
    config = VariablesConfig(
        variables={
            'agent_config': VariableConfig(
                name='agent_config',
                labels={
                    'latest': LabeledValue(
                        version=2,
                        serialized_value=(
                            '{"schema_version":2,"model":"openai:gpt-5.6","instructions":["Be concise."]}'
                        ),
                    )
                },
                rollout=Rollout(labels={'latest': 1.0}),
                overrides=[],
            ),
            'unsupported_agent_config': VariableConfig(
                name='unsupported_agent_config',
                labels={
                    'latest': LabeledValue(
                        version=3,
                        serialized_value='{"schema_version":3,"model":"openai:gpt-6"}',
                    )
                },
                rollout=Rollout(labels={'latest': 1.0}),
                overrides=[],
            ),
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    agent_config = create_flag('agent_config', default=fallback)
    unsupported = create_flag('unsupported_agent_config', default=fallback)

    schema = agent_config._adapter.type_adapter.json_schema()
    assert schema['discriminator'] == {
        'mapping': {'1': '#/$defs/AgentConfigV1', '2': '#/$defs/AgentConfigV2'},
        'propertyName': 'schema_version',
    }

    details = agent_config.details()
    assert details.value == AgentConfig(
        AgentConfigV2(
            model='openai:gpt-5.6',
            instructions=['Be concise.'],
        )
    )
    assert details.variant == 'latest'
    assert details.flag_metadata == {'logfire.value_version': 2}

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        unsupported_details = unsupported.details()
    assert unsupported_details.value == fallback
    assert unsupported_details.variant is None
    assert unsupported_details.reason == 'error'
    assert unsupported_details.error_code == 'type_mismatch'
    assert unsupported_details.flag_metadata == {}


def test_feature_flag_validates_test_overrides_before_installing_them():
    enabled = create_flag('enabled', default=False)

    with pytest.raises(ValidationError, match='bool_type'):
        enabled.override(cast(Any, object()))
    with pytest.raises(ValidationError, match='bool_type'):
        enabled._adapter.override(cast(Any, object()))

    assert enabled.value() is False


@pytest.mark.parametrize(
    ('value_type', 'default', 'configured_value'),
    [
        (bool, False, '1'),
        (int, 0, 'true'),
        (float, 0.0, 'true'),
    ],
)
def test_typed_flags_do_not_coerce_remote_json_scalar_types(value_type: type[Any], default: Any, configured_value: str):
    config = VariablesConfig(
        variables={
            'typed_flag': VariableConfig(
                name='typed_flag',
                labels={'configured': LabeledValue(version=1, serialized_value=configured_value)},
                rollout=Rollout(labels={'configured': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    typed_flag = create_flag('typed_flag', type=value_type, default=default)

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = typed_flag.details()

    assert details.value == default
    assert type(details.value) is type(default)
    assert details.reason == 'error'
    assert details.error_code == 'type_mismatch'


@pytest.mark.parametrize(('value_type', 'invalid_value'), [(bool, 1), (int, True), (float, True)])
def test_typed_flags_do_not_coerce_defaults_or_test_overrides(value_type: type[Any], invalid_value: Any):
    with pytest.raises(ValidationError):
        create_flag('invalid_default', type=value_type, default=invalid_value)

    typed_flag = create_flag('typed_flag', type=value_type, default=value_type())
    with pytest.raises(ValidationError):
        typed_flag.override(invalid_value)


def test_float_flags_follow_pydantic_strict_numeric_widening():
    """Pydantic strict mode accepts integers as exact numeric inputs for float fields."""
    config = VariablesConfig(
        variables={
            'sample_rate': VariableConfig(
                name='sample_rate',
                labels={'configured': LabeledValue(version=1, serialized_value='1')},
                rollout=Rollout(labels={'configured': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )

    sample_rate = create_flag('sample_rate', type=float, default=cast(Any, 0))

    assert sample_rate.value() == 1.0
    assert type(sample_rate.value()) is float


def test_parameterized_flag_requires_an_explicit_type():
    with pytest.raises(TypeError, match=r'Pass type=\.\.\.'):
        create_flag('ambiguous', default=[])  # pyright: ignore[reportArgumentType]

    values = create_flag('values', type=list[str], default=[])
    assert values.value() == []


def test_duplicate_flag_name_is_validated_before_type_inference():
    create_flag('duplicate', default=False)

    with pytest.raises(ValueError, match="variable with name 'duplicate' has already been registered"):
        create_flag('duplicate', default=[])  # pyright: ignore[reportArgumentType]


def test_typed_flag_validates_its_code_default_during_construction():
    with pytest.raises(ValidationError, match='valid integer'):
        create_flag('invalid_default', type=int, default=cast(Any, 'not-an-int'))

    assert logfire.variables_get() == []


def test_typed_flag_rejects_callable_defaults():
    def dynamic_default(targeting_key: str | None, attributes: Mapping[str, Any] | None) -> bool:
        return bool(targeting_key or attributes)

    with pytest.raises(TypeError, match='static values'):
        create_flag('dynamic', type=bool, default=cast(Any, dynamic_default))

    assert logfire.variables_get() == []


def test_typed_flag_rejects_zero_argument_callable_defaults():
    with pytest.raises(TypeError, match='static values'):
        create_flag('dynamic', type=object, default=cast(Any, lambda: True))

    assert logfire.variables_get() == []


_OPENFEATURE_JSON_VALUES: st.SearchStrategy[Any] = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(min_value=-(10**10), max_value=10**10)
    | st.floats(min_value=-1e10, max_value=1e10, allow_nan=False, allow_infinity=False)
    | st.text(alphabet='abcXYZ012 _-.é用户🙂', max_size=20),
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text(alphabet='abcXYZ012_', max_size=8), children, max_size=5)
    ),
    max_leaves=15,
)


def test_remote_provider_health_is_reflected_in_flag_details():
    request_mocker = requests_mock_module.Mocker()
    request_mocker.get(
        'http://localhost:8000/v1/variables/',
        [
            {
                'json': {
                    'variables': {
                        'remote_checkout': {
                            'name': 'remote_checkout',
                            'labels': {'enabled': {'version': 2, 'serialized_value': 'true'}},
                            'rollout': {'labels': {'enabled': 1.0}},
                            'overrides': [],
                        }
                    }
                },
                'status_code': 200,
            },
            {'status_code': 500},
            {'status_code': 304},
        ],
    )
    remote_provider = LogfireRemoteVariableProvider(
        base_url='http://localhost:8000/',
        token='pylf_v1_us_test_token',
        options=VariablesOptions(
            block_before_first_resolve=False,
            polling_interval=timedelta(seconds=60),
            instrument=False,
        ),
    )
    custom_logfire = logfire.configure(local=True, send_to_logfire=False, console=False)
    custom_logfire.config._variable_provider = remote_provider
    checkout = create_flag('remote_checkout', default=False, logfire_instance=custom_logfire)

    not_ready = checkout.details()
    assert not_ready.value is False
    assert not_ready.reason == 'error'
    assert not_ready.error_code == 'provider_not_ready'

    with request_mocker:
        remote_provider.refresh(force=True)
        ready = checkout.details()
        assert ready.value is True
        assert ready.reason == 'static'
        assert ready.flag_metadata == {'logfire.value_version': 2}

        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            remote_provider.refresh(force=True)

        stale = checkout.details()
        assert stale.value is True
        assert stale.reason == 'stale'
        assert stale.flag_metadata == {
            'logfire.value_version': 2,
            'logfire.provider_state': 'stale',
        }

        remote_provider.refresh(force=True)
        recovered = checkout.details()
        assert recovered.value is True
        assert recovered.reason == 'static'
        assert recovered.flag_metadata == {'logfire.value_version': 2}

    remote_provider.shutdown()
    stopped = checkout.details()
    assert stopped.value is False
    assert stopped.reason == 'error'
    assert stopped.error_code == 'provider_not_ready'
    custom_logfire.shutdown()


def test_typed_flag_telemetry_serializes_structured_values(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    checkout = create_flag('checkout', default=CheckoutConfig(provider='stripe', retries=2))
    exporter.clear()

    checkout.value()

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    assert (evaluation_span.attributes or {})['feature_flag.result.value'] == '{"provider":"stripe","retries":2}'


def test_feature_flag_telemetry_does_not_treat_unchanged_nan_as_scrubbed():
    threshold = create_flag('threshold', default=float('nan'))
    adapter = cast(Any, threshold._adapter)

    telemetry = adapter._resolution_telemetry_attributes(
        ResolvedVariable(name='threshold', value=float('nan'), reason='code_default'),
        serialized_value='NaN',
        targeting_key=None,
        attributes={},
        requested_label=None,
    )

    assert math.isnan(telemetry['feature_flag.result.value'])
    assert 'logfire.feature_flag.result.value_status' not in telemetry


@pytest.mark.parametrize('error', [ValueError, TypeError, RuntimeError])
@pytest.mark.parametrize('structured', [False, True])
def test_feature_flag_telemetry_handles_json_serialization_failure(error: type[Exception], structured: bool):
    value = {'region': 'us'} if structured else 'us'
    adapter = cast(Any, create_flag('region', type=dict[str, str] if structured else str, default=value)._adapter)
    with patch.object(adapter.type_adapter, 'dump_json', side_effect=error('broken serializer')):
        telemetry = adapter._resolution_telemetry_attributes(
            ResolvedVariable(name='region', value=value, reason='code_default'),
            serialized_value='us',
            targeting_key=None,
            attributes={},
            requested_label=None,
        )
    assert telemetry['feature_flag.result.value'] == ('<unavailable>' if structured else 'us')
    assert telemetry['feature_flag.result.reason'] == 'default'


def test_failed_registration_does_not_leave_a_phantom_flag():
    class Inputs(BaseModel):
        name: str

    logfire.template_var('greeting', inputs_type=Inputs, default='Hello {{name}}')
    with pytest.raises(RuntimeWarning, match='has no inputs_type'):
        create_flag('message', default='@{greeting}@')
    assert 'message' not in logfire.variables_get()


def test_split_flag_testing_override_does_not_warn_about_targeting():
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(
            config=_boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5})), instrument=False
        ),
    )
    checkout = create_flag('test_flag', default=False)
    with checkout.override(True):
        assert checkout.value() is True


def test_feature_flag_telemetry_does_not_treat_nested_unchanged_nan_as_scrubbed():
    payload = create_flag('payload', type=dict[str, list[float]], default={'values': [float('nan')]})
    adapter = cast(Any, payload._adapter)

    telemetry = adapter._resolution_telemetry_attributes(
        ResolvedVariable(name='payload', value={'values': [float('nan')]}, reason='code_default'),
        serialized_value='{"values":[null]}',
        targeting_key=None,
        attributes={},
        requested_label=None,
    )

    assert telemetry['feature_flag.result.value'] == '{"values":[null]}'
    assert 'logfire.feature_flag.result.value_status' not in telemetry


def test_returned_value_and_telemetry_share_one_provider_state_snapshot(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config = VariablesConfig(
        variables={
            'region': VariableConfig(
                name='region',
                labels={'remote': LabeledValue(version=1, serialized_value='"eu"')},
                rollout=Rollout(labels={'remote': 1.0}),
                overrides=[],
            )
        }
    )
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=True)
    logfire.configure(**config_kwargs)
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    exporter.clear()

    with patch.object(adapter, '_get_provider_evaluation_state', side_effect=['ready', 'fatal']) as state:
        details = region.details()

    assert state.call_count == 1
    assert details.value == 'eu'
    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    assert (evaluation_span.attributes or {})['feature_flag.result.value'] == 'eu'


def test_feature_flag_finalization_preserves_resolution_details():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    exception = RuntimeError('provider warning')
    composed_from = [cast(Any, object())]
    resolved = ResolvedVariable(
        name='region',
        value='eu',
        label='remote',
        version=7,
        exception=exception,
        composed_from=composed_from,
        reason='resolved',
        rule_evaluation_reason='targeting_match',
    )

    with patch.object(adapter, '_get_provider_evaluation_state', return_value='ready'):
        finalized = adapter._finalize_resolution_result(resolved)

    assert finalized.name == 'region'
    assert finalized.value == 'eu'
    assert finalized.label == 'remote'
    assert finalized.version == 7
    assert finalized.exception is exception
    assert finalized.composed_from is composed_from
    assert finalized.reason == 'resolved'
    assert finalized.rule_evaluation_reason == 'targeting_match'
    assert finalized.provider_state == 'ready'


@pytest.mark.parametrize('provider_state', ['not_ready', 'ready', 'stale', 'error', 'fatal'])
def test_feature_flag_reads_each_provider_state(provider_state: Any):
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with patch.object(provider, 'get_evaluation_state', return_value=provider_state):
        assert adapter._get_provider_evaluation_state() == provider_state


@pytest.mark.parametrize('provider_state', ['not_ready', 'error', 'fatal'])
def test_unavailable_provider_result_uses_named_code_default(provider_state: Any):
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)

    result = adapter._result_for_provider_state(
        ResolvedVariable(name='region', value='eu', reason='resolved'),
        provider_state,
    )

    assert result.name == 'region'
    assert result.value == 'us'
    assert result.reason == 'code_default'


def test_unavailable_provider_telemetry_records_the_structured_code_default():
    checkout = create_flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))
    adapter = cast(Any, checkout._adapter)

    with patch.object(adapter, '_get_provider_evaluation_state', return_value='fatal'):
        telemetry = adapter._resolution_telemetry_attributes(
            ResolvedVariable(
                name='checkout',
                value=CheckoutConfig(provider='remote', retries=9),
                reason='resolved',
            ),
            serialized_value='{"provider":"remote","retries":9}',
            targeting_key=None,
            attributes={},
            requested_label=None,
        )

    assert telemetry['feature_flag.result.value'] == '{"provider":"fallback","retries":1}'
    assert telemetry['feature_flag.result.reason'] == 'error'
    assert telemetry['error.type'] == 'provider_fatal'


@pytest.mark.parametrize('provider_state', ['stale', 'fatal'])
def test_testing_override_does_not_depend_on_provider_availability(
    provider_state: Any, config_kwargs: dict[str, Any], exporter: TestExporter
):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    checkout = create_flag('checkout', default=False)
    adapter = cast(Any, checkout._adapter)
    exporter.clear()

    with patch.object(adapter, '_get_provider_evaluation_state', return_value=provider_state):
        with checkout.override(True):
            details = checkout.details()

    assert details.value is True
    assert details.reason == 'context_override'
    assert details.error_code is None
    assert details.flag_metadata == {}
    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    assert (evaluation_span.attributes or {})['feature_flag.result.value'] is True
    assert (evaluation_span.attributes or {})['feature_flag.result.reason'] == 'context_override'


def _evaluation_span_attributes(exporter: TestExporter) -> dict[str, Any]:
    evaluation_span = next(
        span
        for span in reversed(exporter.exported_spans)
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    return dict(evaluation_span.attributes or {})


def test_feature_flag_telemetry_records_targeting_key_but_not_attributes(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config_kwargs['variables'] = LocalVariablesOptions(config=_code_default_config('region'), instrument=True)
    logfire.configure(**config_kwargs)
    region = create_flag('region', default='us')
    exporter.clear()

    region.value(targeting_key='account-123', attributes={'account_plan': 'confidential-plan'})
    attributes = _evaluation_span_attributes(exporter)
    assert attributes['feature_flag.context.id'] == 'account-123'
    assert 'targeting_key' not in attributes
    assert 'attributes' not in attributes
    assert 'confidential-plan' not in repr(attributes)

    with feature_context('account-456', attributes={'account_plan': 'confidential-plan'}):
        region.value()
    attributes = _evaluation_span_attributes(exporter)
    assert attributes['feature_flag.context.id'] == 'account-456'
    assert 'confidential-plan' not in repr(attributes)

    # A fallback key that Logfire chose identifies nobody, so it is not recorded.
    with logfire.span('request'):
        region.value()
    assert 'feature_flag.context.id' not in _evaluation_span_attributes(exporter)


def test_scrubbing_can_redact_the_targeting_key(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=_code_default_config('region'), instrument=True)
    config_kwargs['scrubbing'] = logfire.ScrubbingOptions(extra_patterns=[r'context\.id'])
    logfire.configure(**config_kwargs)
    region = create_flag('region', default='us')
    exporter.clear()

    region.value(targeting_key='account-123')
    attributes = _evaluation_span_attributes(exporter)
    assert attributes['feature_flag.context.id'] == "[Scrubbed due to 'context.id']"
    assert 'account-123' not in repr(attributes)


def test_typed_flag_telemetry_omits_scrubbed_structured_values(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    secret = create_flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value:
        secret.value()

    assert (
        ('attributes',),
        {'logfire.feature_flag.result.checkout_settings': {'api_key': 'super-secret'}},
    ) in [call.args for call in scrub_value.call_args_list]

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'scrubbed'
    assert 'super-secret' not in repr(attributes)


def test_typed_flag_telemetry_scrubs_json_only_serializers(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    secret = create_flag('json_settings', default=JsonOnlySecretConfig(payload='opaque-value'))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value:
        secret.value()

    assert (
        ('attributes',),
        {'logfire.feature_flag.result.json_settings': {'payload': {'api_key': 'opaque-value'}}},
    ) in [call.args for call in scrub_value.call_args_list]
    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'scrubbed'
    assert 'opaque-value' not in repr(attributes)


@pytest.mark.parametrize(
    ('value_type', 'original', 'serialized'),
    [(str, 'opaque-928413', '[redacted]'), (bool, True, False), (int, 42, 0), (float, 4.2, 0.0)],
)
def test_flag_telemetry_honors_scalar_json_serializers(
    config_kwargs: dict[str, Any],
    exporter: TestExporter,
    value_type: type[Any],
    original: Any,
    serialized: Any,
):
    config_kwargs['variables'] = LocalVariablesOptions(config=_code_default_config('routing_hint'), instrument=True)
    logfire.configure(**config_kwargs)
    annotated = Annotated[value_type, PlainSerializer(lambda _: serialized, return_type=value_type, when_used='json')]
    setting = create_flag('routing_hint', type=cast(Any, annotated), default=original)
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value:
        assert setting.value() == original

    assert (
        ('attributes',),
        {'logfire.feature_flag.result.routing_hint': serialized},
    ) in [call.args for call in scrub_value.call_args_list]
    attributes = dict(_finished_flag_spans(exporter)[0].attributes or {})
    assert attributes['feature_flag.result.value'] == serialized
    assert type(attributes['feature_flag.result.value']) is value_type
    assert 'logfire.feature_flag.result.value_status' not in attributes
    if value_type is str:
        assert original not in repr(exporter.exported_spans)


def test_typed_flag_telemetry_omits_serialized_value_when_dumping_fails(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    checkout = create_flag('checkout', default=SecretConfig(api_key='nested-secret'))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with (
        patch.object(checkout._adapter.type_adapter, 'dump_python', side_effect=RuntimeError('broken serializer')),
        patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value,
    ):
        checkout.value()

    assert all('logfire.feature_flag.result.checkout' not in call.args[1] for call in scrub_value.call_args_list)
    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'serialization_error'
    assert 'nested-secret' not in repr(evaluation_span)


def test_typed_flag_telemetry_never_falls_back_to_repr(config_kwargs: dict[str, Any], exporter: TestExporter):
    class PrivateReprConfig(BaseModel):
        region: str

        def __repr__(self) -> str:
            return 'opaque-928413'

    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    settings = create_flag('settings', default=PrivateReprConfig(region='us'))
    exporter.clear()
    with patch.object(settings._adapter.type_adapter, 'dump_json', side_effect=ValueError('unavailable')):
        assert settings.value().region == 'us'
    attributes = dict(_finished_flag_spans(exporter)[0].attributes or {})
    assert attributes['feature_flag.result.value'] == '<unavailable>'
    assert 'opaque-928413' not in repr(attributes)


def test_typed_flag_telemetry_honors_callback_replacements_without_notes(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    def replace_secret(match: logfire.ScrubMatch):
        if match.path[-1] == 'api_key':
            return '[replaced by callback]'
        return match.value

    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=replace_secret), **config_kwargs)
    secret = create_flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
    exporter.clear()

    secret.value()

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'scrubbed'
    assert 'super-secret' not in repr(attributes)


def test_typed_flag_telemetry_honors_scrub_notes_without_replacements():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    scrub_key = 'logfire.feature_flag.result.region'

    with patch.object(
        logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber,
        'scrub_value',
        return_value=({scrub_key: 'us'}, [Mock()]),
    ):
        telemetry = adapter._resolution_telemetry_attributes(
            ResolvedVariable(name='region', value='us', reason='code_default'),
            serialized_value='us',
            targeting_key=None,
            attributes={},
            requested_label=None,
        )

    assert 'feature_flag.result.value' not in telemetry
    assert telemetry['logfire.feature_flag.result.value_status'] == 'scrubbed'


def test_provider_metadata_failure_cannot_break_feature_flag_telemetry():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')):
        telemetry = adapter._resolution_telemetry_attributes(
            ResolvedVariable(name='region', value='us', reason='resolved'),
            serialized_value='us',
            targeting_key=None,
            attributes={},
            requested_label=None,
        )

    assert telemetry['feature_flag.result.value'] == 'us'
    assert telemetry['feature_flag.result.reason'] == 'static'


def test_provider_metadata_failure_cannot_break_flag_evaluation():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(adapter, 'get', return_value=ResolvedVariable(name='region', value='eu', reason='resolved')),
        patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')),
    ):
        details = adapter.evaluate_flag(targeting_key='account-a')

    assert details.value == 'eu'
    assert details.reason == 'static'


def test_provider_health_failure_falls_back_without_breaking_flag_evaluation():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(adapter, 'get', return_value=ResolvedVariable(name='region', value='eu', reason='resolved')),
        patch.object(provider, 'get_evaluation_state', side_effect=RuntimeError('broken provider')),
    ):
        details = adapter.evaluate_flag()

    assert details.value == 'us'
    assert details.reason == 'error'
    assert details.error_code == 'general'


def test_invalid_provider_health_falls_back_without_breaking_flag_evaluation():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(adapter, 'get', return_value=ResolvedVariable(name='region', value='eu', reason='resolved')),
        patch.object(provider, 'get_evaluation_state', return_value='not-a-provider-state'),
    ):
        details = adapter.evaluate_flag()

    assert details.value == 'us'
    assert details.reason == 'error'
    assert details.error_code == 'general'


def test_flag_evaluation_details_use_the_resolved_config_snapshot():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    test_flag = create_flag('test_flag', default=False)
    adapter = cast(Any, test_flag._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()
    original_get = provider.get_serialized_value

    def resolve_then_replace_config(*args: Any, **kwargs: Any):
        result = original_get(*args, **kwargs)
        static_config = _boolean_config(rollout=Rollout(labels={'enabled': 1.0})).variables['test_flag']
        provider.update_variable('test_flag', static_config)
        return result

    with patch.object(provider, 'get_serialized_value', side_effect=resolve_then_replace_config):
        details = adapter.evaluate_flag(targeting_key='account-a')

    assert details.reason == 'split'
    current_config = provider.get_variable_config('test_flag')
    assert current_config is not None
    assert current_config.rule_evaluation_reason({}) == 'static'


def test_split_reason_is_preserved_when_rollout_selects_the_code_default():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5}))
    variable_config = config.variables['test_flag']
    targeting_key = next(
        candidate
        for candidate in (f'account-{i}' for i in range(100))
        if variable_config.resolve_label(candidate) is None
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )

    details = create_flag('test_flag', default=False).details(targeting_key=targeting_key)

    assert details.value is False
    assert details.reason == 'split'


def test_provider_metadata_failure_cannot_break_rollout_warning():
    region = create_flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(
            _FlagEvaluationCore,
            'get',
            return_value=ResolvedVariable(name='region', value='eu', reason='resolved'),
        ),
        patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')),
    ):
        assert adapter.get().value == 'eu'


def test_provider_exception_text_is_not_recorded_for_feature_flags(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    region = create_flag('region', default='us')
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()
    exporter.clear()

    with patch.object(
        provider,
        'get_serialized_value',
        side_effect=RuntimeError('provider failed for victim@example.com'),
    ):
        assert region.value() == 'us'

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert attributes['error.type'] == 'general'
    assert attributes['feature_flag.error.message'] == 'Feature flag evaluation failed.'
    assert evaluation_span.events == ()
    assert 'victim@example.com' not in repr(evaluation_span)


def test_scrubbing_callback_failure_cannot_break_flag_evaluation(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    secret = create_flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
    exporter.clear()

    with patch.object(
        logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber,
        'scrub_value',
        side_effect=RuntimeError('broken callback'),
    ):
        assert secret.value() == SecretConfig(api_key='super-secret')

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'scrubbed'
    assert 'super-secret' not in repr(attributes)


def test_feature_flag_telemetry_uses_placeholder_when_no_serialized_value_exists():
    assert _feature_flag_telemetry_value(object(), None) == '<unavailable>'


def test_rollout_warning_truth_table():
    config = _boolean_config(
        rollout=Rollout(labels={'enabled': 1.0}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='plan', value='free')],
                rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}),
            )
        ],
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        flag.details(attributes={'plan': 'team'})
        flag.details(targeting_key='account-a', attributes={'plan': 'free'})
        with feature_context('account-a', attributes={'plan': 'free'}):
            flag.details()
        with targeting_context('account-a', variables=[flag]):
            flag.details(attributes={'plan': 'free'})
    assert caught == []

    with pytest.warns(RuntimeWarning, match='no stable targeting key') as caught:
        flag.details(attributes={'plan': 'free'})
    assert len(caught) == 1


def test_feature_flags_use_a_random_key_per_local_trace_without_a_targeting_key():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()

    with (
        patch.object(provider, 'get_serialized_value', wraps=provider.get_serialized_value) as get_serialized_value,
        warnings.catch_warnings(),
    ):
        warnings.simplefilter('ignore', RuntimeWarning)
        with logfire.span('request') as span:
            first = flag.details()
            second = flag.details()
        with logfire.span('other request'):
            flag.details()

    keys = [call.args[1] for call in get_serialized_value.call_args_list]
    trace_id = f'{span.get_span_context().trace_id:032x}'  # type: ignore[union-attr]
    # A caller controls the inbound trace ID, so the key must not be derived from it.
    assert all(key.startswith('trace:') and trace_id not in key for key in keys)
    # Every evaluation in one trace gets the same key, so the trace sees one variant.
    assert keys[0] == keys[1]
    assert first.variant == second.variant
    assert keys[2] != keys[0]
    assert first.reason == 'split'
    assert first.flag_metadata['logfire.targeting_key_source'] == 'trace'


def test_feature_flags_without_a_trace_keep_one_key_for_the_context():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)

    def evaluate_repeatedly() -> list[str | None]:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            return [flag.details().variant for _ in range(20)]

    # Each fresh context draws its own key, but every evaluation in one context agrees.
    variants = [contextvars.Context().run(evaluate_repeatedly) for _ in range(20)]
    assert all(len(set(run)) == 1 for run in variants)
    assert {run[0] for run in variants} == {'enabled', 'disabled'}
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        details = contextvars.Context().run(flag.details)
    assert details.flag_metadata['logfire.targeting_key_source'] == 'ephemeral'


def test_resource_attributes_target_feature_flags_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv('OTEL_RESOURCE_ATTRIBUTES', 'plan=free')
    config = _boolean_config(
        rollout=Rollout(labels={'enabled': 1.0}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='plan', value='free')],
                rollout=Rollout(labels={'disabled': 1.0}),
            )
        ],
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(
            config=config,
            instrument=False,
            include_resource_attributes_in_context=True,
        ),
    )
    flag = create_flag('test_flag', default=False)

    assert flag.details(targeting_key='account-a').variant == 'disabled'


class FeatureFlagStateMachine(RuleBasedStateMachine):
    KEYS = ('account-a', 'account-b', 'account-c', '')

    def __init__(self):
        super().__init__()
        config = _boolean_config(
            rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}),
            overrides=[
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='team')],
                    rollout=Rollout(labels={'enabled': 1.0}),
                ),
                RolloutOverride(
                    conditions=[ValueEquals(attribute='plan', value='guest')],
                    rollout=Rollout(labels={'disabled': 1.0}),
                ),
            ],
        )
        self.logfire = logfire.configure(
            send_to_logfire=False,
            console=False,
            variables=LocalVariablesOptions(
                config=config,
                instrument=False,
                include_resource_attributes_in_context=False,
            ),
        )
        self.logfire.variables_clear()
        self.flag = create_flag('test_flag', default=False, logfire_instance=self.logfire)
        self.contexts: list[tuple[AbstractContextManager[None], str, dict[str, str]]] = []
        self.overrides: list[tuple[AbstractContextManager[None], bool]] = []
        self.base_results = {key: self.flag.details(targeting_key=key) for key in self.KEYS}

    @rule(
        targeting_key=st.sampled_from([key for key in KEYS if key]),
        plan=st.sampled_from(('none', 'team', 'guest')),
        region=st.sampled_from(('us', 'eu', 'apac')),
    )
    def enter_feature_context(self, targeting_key: str, plan: str, region: str):
        attributes = {'region': region}
        if plan != 'none':
            attributes['plan'] = plan
        manager = feature_context(targeting_key, attributes=attributes)
        manager.__enter__()
        self.contexts.append((manager, targeting_key, attributes))

    @precondition(lambda self: bool(self.contexts))
    @rule()
    def leave_feature_context(self):
        manager, _, _ = self.contexts.pop()
        manager.__exit__(None, None, None)

    @rule(value=st.booleans())
    def enter_override(self, value: bool):
        manager = self.flag.override(value)
        manager.__enter__()
        self.overrides.append((manager, value))

    @precondition(lambda self: bool(self.overrides))
    @rule()
    def leave_override(self):
        manager, _ = self.overrides.pop()
        manager.__exit__(None, None, None)

    @rule(
        explicit_key=st.one_of(st.none(), st.sampled_from(KEYS)),
        explicit_plan=st.sampled_from(('none', 'team', 'guest')),
    )
    def evaluate(self, explicit_key: str | None, explicit_plan: str):
        targeting_key = explicit_key
        if targeting_key is None and not self.contexts:
            targeting_key = 'account-a'
        attributes = None if explicit_plan == 'none' else {'plan': explicit_plan}

        details = self.flag.details(targeting_key=targeting_key, attributes=attributes)

        expected_attributes: dict[str, str] = {}
        for _, _, context_attributes in self.contexts:
            expected_attributes.update(context_attributes)
        if attributes:
            expected_attributes.update(attributes)

        if self.overrides:
            expected_value = self.overrides[-1][1]
            expected_variant = None
            expected_reason = 'context_override'
        elif expected_attributes.get('plan') == 'team':
            expected_value = True
            expected_variant = 'enabled'
            expected_reason = 'targeting_match'
        elif expected_attributes.get('plan') == 'guest':
            expected_value = False
            expected_variant = 'disabled'
            expected_reason = 'targeting_match'
        else:
            effective_key = targeting_key if targeting_key is not None else self.contexts[-1][1]
            baseline = self.base_results[effective_key]
            expected_value = baseline.value
            expected_variant = baseline.variant
            expected_reason = baseline.reason

        assert details.value is expected_value
        assert details.variant == expected_variant
        assert details.reason == expected_reason
        assert self.flag.value(targeting_key=targeting_key, attributes=attributes) is expected_value

    @invariant()
    def evaluations_always_return_booleans(self):
        assert isinstance(self.flag.value(targeting_key='account-a'), bool)

    def teardown(self):
        while self.overrides:
            self.leave_override()
        while self.contexts:
            self.leave_feature_context()
        self.logfire.variables_clear()


def test_feature_flag_context_and_override_state_machine():
    run_state_machine_as_test(
        FeatureFlagStateMachine,
        settings=settings(
            max_examples=20 if MUTATION_TESTING else 75,
            stateful_step_count=20 if MUTATION_TESTING else 40,
            derandomize=True,
            deadline=None,
        ),
    )


def test_feature_context_isolated_across_threads():
    config = _boolean_config(
        rollout=Rollout(labels={'disabled': 1.0}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='plan', value='team')],
                rollout=Rollout(labels={'enabled': 1.0}),
            )
        ],
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)
    barrier = threading.Barrier(4, timeout=2)

    def evaluate(name: str, plan: str) -> tuple[str, bool]:
        with feature_context(name, attributes={'plan': plan}):
            barrier.wait()
            return name, flag.value()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(evaluate, f'user-{index}', 'team' if index % 2 else 'guest') for index in range(4)]
        results = dict(future.result(timeout=5) for future in futures)

    assert results == {'user-0': False, 'user-1': True, 'user-2': False, 'user-3': True}


def test_feature_context_copies_attributes_and_restores_after_an_exception():
    config = _boolean_config(
        rollout=Rollout(labels={'disabled': 1.0}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='plan', value='team')],
                rollout=Rollout(labels={'enabled': 1.0}),
            )
        ],
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)
    attributes = {'plan': 'team'}

    with pytest.raises(RuntimeError, match='stop setup'):
        with feature_context('account-a', attributes=attributes):
            attributes['plan'] = 'guest'
            assert flag.value() is True
            raise RuntimeError('stop setup')

    assert flag.value(targeting_key='account-a') is False


def test_feature_context_reuses_managed_variable_targeting_context():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = create_flag('test_flag', default=False)

    def regular_default(targeting_key: str | None, _attributes: Mapping[str, object] | None) -> str:
        return targeting_key or 'no-targeting-key'

    regular_variable = logfire.var('regular_variable', type=str, default=regular_default)

    with targeting_context('regular-variable-key'):
        with feature_context('feature-flag-key', attributes={'plan': 'team'}):
            assert regular_variable.get().value == 'feature-flag-key'
            assert flag.details().variant == config.variables['test_flag'].resolve_label('feature-flag-key')

    for feature_context_is_outer in (False, True):
        with ExitStack() as stack:
            stack.enter_context(targeting_context('regular-variable-key'))
            if feature_context_is_outer:
                stack.enter_context(feature_context('feature-flag-key'))
                stack.enter_context(targeting_context('specific-feature-flag-key', variables=[flag]))
            else:
                stack.enter_context(targeting_context('specific-feature-flag-key', variables=[flag]))
                stack.enter_context(feature_context('feature-flag-key'))

            assert regular_variable.get().value == 'feature-flag-key'
            assert flag.details().variant == config.variables['test_flag'].resolve_label('specific-feature-flag-key')


@pytest.mark.anyio
async def test_cancelled_feature_scope_restores_parent_without_leaking_to_sibling(config_kwargs: dict[str, Any]):
    """Child task cancellation unwinds keys, attributes, and overrides without changing siblings."""
    import anyio

    config_kwargs['variables'] = LocalVariablesOptions(
        config=VariablesConfig(variables={}), instrument=False, include_resource_attributes_in_context=False
    )
    logfire.configure(**config_kwargs)
    gate = create_flag('cancelled_scope', default=False)
    adapter = gate._adapter
    entered, sibling_checked, cleaned = anyio.Event(), anyio.Event(), anyio.Event()

    def check_parent() -> None:
        assert gate.value() is False
        assert adapter._get_context_targeting_key() == 'parent'
        assert adapter._get_merged_attributes() == {'scope': 'parent'}

    async def cancelled_child() -> None:
        try:
            with feature_context('child', attributes={'scope': 'child'}), gate.override(True):
                assert gate.value() is True
                entered.set()
                await anyio.sleep_forever()
        finally:
            check_parent()
            cleaned.set()

    async def sibling() -> None:
        await entered.wait()
        check_parent()
        sibling_checked.set()

    with feature_context('parent', attributes={'scope': 'parent'}), gate.override(False):
        with anyio.fail_after(5):
            async with anyio.create_task_group() as group:
                group.start_soon(cancelled_child)
                group.start_soon(sibling)
                await sibling_checked.wait()
                check_parent()
                group.cancel_scope.cancel()
        assert cleaned.is_set()
        check_parent()
    assert adapter._get_context_targeting_key() is None
    assert adapter._get_merged_attributes() == {}
    assert gate.value() is False


def test_details_context_manager_sets_variant_baggage(config_kwargs: dict[str, Any], exporter: TestExporter):
    config = _boolean_config(rollout=Rollout(labels={'enabled': 1.0}))
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=False)
    # The test fixture turns this off. Logfire enables it by default.
    config_kwargs['add_baggage_to_attributes'] = True
    logfire.configure(**config_kwargs)
    flag = create_flag('test_flag', default=False)

    details = flag.details('account-123')
    # Without `with`, evaluation does not touch baggage.
    assert logfire.get_baggage() == {}
    with details as entered:
        assert entered is details
        assert logfire.get_baggage() == {
            'logfire.variables.test_flag': 'enabled',
            'logfire.variables.test_flag.version': '2',
        }
        logfire.info('downstream')
    assert logfire.get_baggage() == {}

    log = next(span for span in exporter.exported_spans if span.name == 'downstream')
    assert (log.attributes or {})['logfire.variables.test_flag'] == 'enabled'


def test_details_context_manager_marks_defaults_and_overrides(config_kwargs: dict[str, Any]):
    config_kwargs['variables'] = LocalVariablesOptions(config=_code_default_config('checkout'), instrument=False)
    logfire.configure(**config_kwargs)
    checkout = create_flag('checkout', default=False)

    with checkout.details():
        assert logfire.get_baggage() == {'logfire.variables.checkout': '<code_default>'}
    with checkout.override(True), checkout.details():
        assert logfire.get_baggage() == {'logfire.variables.checkout': '<context_override>'}


def test_details_context_manager_nests_and_can_be_reentered(config_kwargs: dict[str, Any]):
    config = _boolean_config(rollout=Rollout(labels={'enabled': 1.0}))
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=False)
    logfire.configure(**config_kwargs)
    flag = create_flag('test_flag', default=False)
    details = flag.details('account-123')

    with logfire.set_baggage(outer='kept'):
        with details:
            with details:
                assert logfire.get_baggage()['logfire.variables.test_flag'] == 'enabled'
            # Leaving the inner block keeps the outer block's entry.
            assert logfire.get_baggage()['logfire.variables.test_flag'] == 'enabled'
        assert logfire.get_baggage() == {'outer': 'kept'}
        # The same details can be entered again after leaving.
        with details:
            assert logfire.get_baggage()['logfire.variables.test_flag'] == 'enabled'
        assert logfire.get_baggage() == {'outer': 'kept'}


def test_details_context_manager_does_not_affect_equality_or_repr(config_kwargs: dict[str, Any]):
    logfire.configure(**config_kwargs)
    details = FlagEvaluationDetails(flag_key='checkout', value=True, variant='on', reason='static')
    with details:
        assert details == FlagEvaluationDetails(flag_key='checkout', value=True, variant='on', reason='static')
    assert '_baggage_scopes' not in repr(details)


def test_missing_flag_reports_flag_not_found_only_when_a_provider_is_configured(config_kwargs: dict[str, Any]):
    logfire.configure(**config_kwargs)
    unconfigured = create_flag('typo_flag', default=False)
    # Without a configured provider, for example without an API key, the code default is not an error.
    details = unconfigured.details()
    assert (details.value, details.reason, details.error_code) == (False, 'default', None)

    logfire.configure(variables=LocalVariablesOptions(config=_code_default_config('present')), **config_kwargs)
    present = create_flag('present', default=False)
    missing = create_flag('missing', default=True)
    # A configured flag whose rollout selects the code default is not missing.
    assert present.details().error_code is None
    missing_details = missing.details()
    assert missing_details.value is True
    assert (missing_details.reason, missing_details.error_code) == ('error', 'flag_not_found')
    assert missing_details.variant is None


def test_malformed_json_reports_parse_error(config_kwargs: dict[str, Any]):
    config = _boolean_config(rollout=Rollout(labels={'enabled': 1.0}))
    config.variables['test_flag'].labels['enabled'] = LabeledValue(version=2, serialized_value='{not json')
    logfire.configure(variables=LocalVariablesOptions(config=config, instrument=False), **config_kwargs)
    flag = create_flag('test_flag', default=False)

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = flag.details('account-123')
    assert (details.value, details.reason, details.error_code) == (False, 'error', 'parse_error')
    assert details.error_message == 'Configured value is not valid JSON.'


def test_type_mismatch_message_names_fields_without_values(config_kwargs: dict[str, Any]):
    class Limits(BaseModel):
        retries: int
        timeout: float
        region: str
        tier: int

    config = VariablesConfig(
        variables={
            'limits': VariableConfig(
                name='limits',
                labels={
                    'bad': LabeledValue(
                        version=1,
                        serialized_value='{"retries": "opaque-1", "timeout": "opaque-2", "region": 3, "tier": "opaque-4"}',
                    )
                },
                rollout=Rollout(labels={'bad': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(variables=LocalVariablesOptions(config=config, instrument=False), **config_kwargs)
    limits = create_flag('limits', default=Limits(retries=1, timeout=1.0, region='us', tier=1))

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = limits.details('account-123')
    assert details.error_code == 'type_mismatch'
    assert details.error_message == (
        'Configured value did not match the declared flag type: '
        'retries (int_type), timeout (float_type), region (string_type), and 1 more.'
    )
    assert 'opaque' not in (details.error_message or '')


def test_feature_context_rejects_an_empty_targeting_key():
    with pytest.raises(ValueError, match='non-empty targeting key'):
        with feature_context(''):
            pass  # pragma: no cover


@pytest.mark.parametrize('entry_point', ['flag', 'feature_context'])
def test_missing_dependencies_name_the_feature_flags_extra(entry_point: str):
    with patch.dict('sys.modules', {'pydantic_handlebars': None}):
        with pytest.raises(ImportError, match=r"pip install 'logfire\[feature-flags\]'"):
            if entry_point == 'flag':
                create_flag('needs_extra', default=False)
            else:
                feature_context('account-123')


def test_flag_evaluation_records_composed_references_without_values(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config = VariablesConfig(
        variables={
            'greeting': VariableConfig(
                name='greeting',
                labels={'v': LabeledValue(version=3, serialized_value='"Hello @{name}@"')},
                rollout=Rollout(labels={'v': 1.0}),
                overrides=[],
            ),
            'name': VariableConfig(
                name='name',
                labels={'b': LabeledValue(version=7, serialized_value='"opaque-928413"')},
                rollout=Rollout(labels={'b': 1.0}),
                overrides=[],
            ),
        }
    )
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=True)
    logfire.configure(**config_kwargs)
    greeting = create_flag('greeting', default='hi')
    exporter.clear()

    assert greeting.value('account-123') == 'Hello opaque-928413'
    attributes = _evaluation_span_attributes(exporter)
    # A change to a composed variable changes the served value without changing the flag's own
    # version, so the composed labels and versions must be visible for variant analysis.
    assert json.loads(attributes['composed_from']) == [
        {'name': 'name', 'version': 7, 'label': 'b', 'reason': 'resolved', 'error': None}
    ]
    assert 'opaque-928413' not in attributes['composed_from']


def test_targeting_key_precedence(config_kwargs: dict[str, Any]):
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=False)
    logfire.configure(**config_kwargs)
    flag = create_flag('test_flag', default=False)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()

    def key_used(**kwargs: Any) -> str:
        with patch.object(provider, 'get_serialized_value', wraps=provider.get_serialized_value) as lookup:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                flag.details(**kwargs)
        return lookup.call_args.args[1]

    def scenario() -> None:
        # Outside a trace, the first unkeyed evaluation sets a random key for this context.
        ephemeral = key_used()
        assert ephemeral.startswith('ephemeral:')
        assert key_used() == ephemeral
        with logfire.span('request'):
            # A trace takes precedence over the random key set earlier in the root context.
            trace_key = key_used()
            assert trace_key.startswith('trace:')
            with feature_context('account-context'):
                assert key_used() == 'account-context'
                assert key_used(targeting_key='account-explicit') == 'account-explicit'
        assert key_used() == ephemeral

    contextvars.Context().run(scenario)


def test_flag_not_found_check_does_not_break_evaluation(config_kwargs: dict[str, Any]):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False)
    logfire.configure(**config_kwargs)
    checkout = create_flag('checkout', default=True)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()

    with patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')):
        details = checkout.details('account-123')
    assert (details.value, details.reason, details.error_code) == (True, 'default', None)


def test_remote_provider_does_not_fetch_after_shutdown():
    remote = LogfireRemoteVariableProvider(
        base_url='http://localhost:8000/', token='fake', options=VariablesOptions(block_before_first_resolve=False)
    )
    remote.shutdown()
    with requests_mock_module.Mocker() as mocker:
        remote.refresh(force=True)
        assert not mocker.called


def test_type_mismatch_telemetry_omits_value_derived_locations(config_kwargs: dict[str, Any], exporter: TestExporter):
    config = VariablesConfig(
        variables={
            'limits': VariableConfig(
                name='limits',
                labels={'bad': LabeledValue(version=1, serialized_value='{"customer-private-key": "not a number"}')},
                rollout=Rollout(labels={'bad': 1.0}),
                overrides=[],
            )
        }
    )
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=True)
    logfire.configure(**config_kwargs)
    limits = create_flag('limits', type=dict[str, int], default={})
    exporter.clear()

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = limits.details('account-123')
    # The in-process details name the failing key so a developer can find it.
    assert details.error_message == (
        'Configured value did not match the declared flag type: customer-private-key (int_type).'
    )
    # Telemetry leaves the process, so it only records the error types.
    attributes = _evaluation_span_attributes(exporter)
    assert (
        attributes['feature_flag.error.message'] == 'Configured value did not match the declared flag type: int_type.'
    )
    assert 'customer-private-key' not in repr(attributes)


def _fallback_key_recorder(flag: Flag[bool]) -> Callable[..., str]:
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()
    original = provider.get_serialized_value
    keys: list[str] = []

    def record(name: str, targeting_key: str | None, attributes: Mapping[str, Any] | None = None) -> Any:
        keys.append(cast(str, targeting_key))
        return original(name, targeting_key, attributes)

    provider.get_serialized_value = record  # type: ignore[method-assign]

    def key(targeting_key: str | None = None) -> str:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            flag.value(targeting_key)
        return keys[-1]

    return key


def _split_flag(config_kwargs: dict[str, Any]) -> Flag[bool]:
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    config_kwargs['variables'] = LocalVariablesOptions(config=config, instrument=False)
    logfire.configure(**config_kwargs)
    return create_flag('test_flag', default=False)


def test_requests_with_the_same_trace_id_get_independent_fallback_keys(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))
    carrier = {'traceparent': '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01'}

    def request() -> str:
        with logfire.attach_context(carrier), logfire.span('request'):
            return key()

    # A caller who resends a trace ID gets a new key, so it cannot keep a variant it found.
    keys = {contextvars.Context().run(request) for _ in range(5)}
    assert len(keys) == 5


def test_sequential_requests_in_one_context_get_new_fallback_keys(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))

    def requests() -> list[str]:
        # A sync worker thread keeps one context across the requests that it handles.
        keys: list[str] = []
        for _ in range(3):
            with logfire.span('request'):
                keys.append(key())
                assert key() == keys[-1]
        # Once the request ends, an evaluation outside any span no longer uses its key.
        assert key().startswith('ephemeral:')
        return keys

    assert len(set(contextvars.Context().run(requests))) == 3


def test_tasks_and_thread_pools_share_the_request_fallback_key(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))

    async def request() -> set[str]:
        with logfire.span('request'):
            loop = asyncio.get_running_loop()
            # Siblings started before any evaluation share one key.
            gathered = await asyncio.gather(asyncio.to_thread(key), asyncio.to_thread(key))
            with ThreadPoolExecutor() as executor:
                pooled = executor.submit(key).result()
            in_executor = await loop.run_in_executor(None, key)
            return {*gathered, pooled, in_executor, key()}

    assert len(asyncio.run(request())) == 1


def test_thread_pools_inherit_overrides_and_targeting_context(config_kwargs: dict[str, Any]):
    flag = _split_flag(config_kwargs)
    variable = logfire.var('pooled_variable', type=str, default='code')

    async def evaluate() -> None:
        loop = asyncio.get_running_loop()
        with flag.override(True), variable.override('overridden'):
            assert await loop.run_in_executor(None, flag.value) is True
            with ThreadPoolExecutor() as executor:
                assert executor.submit(lambda: variable.get().value).result() == 'overridden'
        with feature_context('account-123', attributes={'plan': 'team'}):
            details = await loop.run_in_executor(None, flag.details)
            assert details.flag_metadata.get('logfire.targeting_key_source') is None
        # The values are restored in the worker thread after each task.
        with ThreadPoolExecutor(max_workers=1) as executor:
            with flag.override(True):
                executor.submit(flag.value).result()
            assert executor.submit(lambda: _VARIABLE_OVERRIDES.get()).result() is None

    asyncio.run(evaluate())


def test_overlapping_requests_with_the_same_trace_id_share_a_fallback_key(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))
    tracer = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_tracer_provider().get_tracer('test')
    carrier = {'traceparent': '00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01'}

    with logfire.attach_context(carrier):
        first = tracer.start_span('first request')
        second = tracer.start_span('second request')
    with trace.use_span(first):
        first_key = key()
    with trace.use_span(second):
        assert key() == first_key
    # The trace's key outlives the first request while the second is still open.
    first.end()
    with trace.use_span(second):
        assert key() == first_key
    second.end()
    with logfire.attach_context(carrier), logfire.span('later request'):
        assert key() != first_key


def test_root_spans_that_never_become_current_or_end_elsewhere_do_not_leak_keys(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))
    tracer = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_tracer_provider().get_tracer('test')

    root = tracer.start_span('started but never current')
    # Starting a span without making it current does not change evaluations outside it.
    outside = key()
    assert outside.startswith('ephemeral:')
    with trace.use_span(root):
        request_key = key()
    ender = threading.Thread(target=root.end)
    ender.start()
    ender.join()
    # After the span ended in another thread, a new request in this thread gets a new key.
    with logfire.span('next request'):
        assert key() not in {request_key, outside}
    assert key() == outside


def test_trace_scope_discards_the_oldest_trace_past_the_limit(config_kwargs: dict[str, Any]):
    logfire.configure(**config_kwargs)
    tracer = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_tracer_provider().get_tracer('test')
    with patch('logfire._internal.trace_scope._MAX_OPEN_TRACES', 1):
        never_ends = tracer.start_span('never ends')
        with tracer.start_as_current_span('second'):
            assert list(trace_scope._states) == [trace.get_current_span().get_span_context().trace_id]
        never_ends.end()
    assert trace_scope._states == {}


def test_resolution_warnings_point_at_the_callers_code(config_kwargs: dict[str, Any]):
    flag = _split_flag(config_kwargs)
    for evaluate in (flag.value, flag.details):
        with pytest.warns(RuntimeWarning, match='no stable targeting key') as caught:
            evaluate()
        assert caught[0].filename == __file__


def test_an_empty_targeting_key_counts_as_no_key(config_kwargs: dict[str, Any]):
    key = _fallback_key_recorder(_split_flag(config_kwargs))
    with logfire.span('request'):
        fallback = key()
        assert key('') == fallback
        with feature_context('account-123'):
            assert key('') == 'account-123'


def test_spans_from_other_tracer_providers_use_the_context_fallback_key(config_kwargs: dict[str, Any]):
    from opentelemetry.sdk.trace import TracerProvider

    key = _fallback_key_recorder(_split_flag(config_kwargs))
    outside = key()
    # Logfire's span processor never saw this span, so its trace has no tracked key.
    with TracerProvider().get_tracer('other').start_as_current_span('untracked'):
        assert key() == outside
