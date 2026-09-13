from __future__ import annotations

# pyright: reportPrivateUsage=false
import os
import threading
import warnings
from collections import Counter
from collections.abc import Mapping
from contextlib import AbstractContextManager, ExitStack
from dataclasses import replace
from enum import Enum, IntEnum
from typing import Annotated, Any, Literal, cast
from unittest.mock import Mock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from hypothesis.stateful import (
    RuleBasedStateMachine,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,  # pyright: ignore[reportUnknownVariableType]
)
from openfeature import api as openfeature_api
from openfeature.evaluation_context import EvaluationContext
from openfeature.exception import ErrorCode
from openfeature.flag_evaluation import FlagResolutionDetails, Reason
from pydantic import BaseModel, Field, PlainSerializer, ValidationError

import logfire
from logfire._internal.config import LocalVariablesOptions
from logfire.experimental.feature_flags import (
    FeatureFlag,
    Flag,
    LogfireProvider,
    _is_exclusively_openfeature_scalar_schema,
    _matches_openfeature_scalar_type,
    feature_context,
    feature_flag,
    flag,
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
from logfire.variables.variable import (
    Variable,
    _feature_flag_evaluation_details,
    _feature_flag_telemetry_attributes,
    _feature_flag_telemetry_value,
)

MUTATION_TESTING = 'MUTANT_UNDER_TEST' in os.environ
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


def _rollout_from_parts(parts: tuple[int, int, int]) -> Rollout:
    return Rollout(
        labels={
            'enabled': parts[0] / 100,
            'disabled': parts[1] / 100,
            'alternate': parts[2] / 100,
        }
    )


def test_feature_flag_api_is_experimental():
    assert not hasattr(logfire, 'feature_flag')
    assert not hasattr(logfire, 'feature_context')


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
            'static',
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
            ResolvedVariable(name='test_flag', value=False, reason='validation_error', exception=ValueError()),
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

    assert details.value is result.value
    assert details.variant == result.label
    assert details.reason == expected_reason.upper()
    assert details.error_code == (expected_error.upper() if expected_error else None)
    assert telemetry['feature_flag.key'] == result.name
    assert telemetry['feature_flag.provider.name'] == 'logfire'
    assert telemetry['feature_flag.result.value'] is result.value
    assert telemetry['feature_flag.result.reason'] == expected_reason
    assert telemetry['logfire.feature_flag.resolution_reason'] == result.reason
    assert telemetry.get('error.type') == expected_error
    assert telemetry.get('feature_flag.result.variant') == result.label
    assert telemetry.get('logfire.feature_flag.value_version') == result.version
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
    assert details.reason == Reason.STATIC


def test_rollout_warning_inspection_cannot_break_a_resolved_value():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    test_flag = feature_flag('test_flag', default=False)

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
    test_flag = feature_flag('test_flag', default=False)
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
    flag = FeatureFlag('test_flag', default=False, description='Enable the new checkout.')

    assert isinstance(flag, FeatureFlag)
    assert flag.description == 'Enable the new checkout.'
    assert not hasattr(flag, 'get')
    details = flag.evaluate(targeting_key='account-a')
    assert details.flag_key == 'test_flag'
    assert details.value is False
    assert details.variant == 'disabled'
    assert details.reason == Reason.STATIC
    assert details.flag_metadata == {'logfire.value_version': 1}


def test_is_enabled_forwards_an_explicit_targeting_key():
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
    test_flag = feature_flag('test_flag', default=False)

    assert test_flag.is_enabled(targeting_key=enabled_key) is True


def test_is_enabled_forwards_the_complete_evaluation_context():
    test_flag = feature_flag('test_flag', default=False)
    attributes = {'plan': 'team'}

    with patch.object(FeatureFlag, 'value', return_value=True) as value:
        assert test_flag.is_enabled(targeting_key='account-a', attributes=attributes) is True

    value.assert_called_once_with('account-a', attributes)


def test_value_forwards_the_complete_evaluation_context():
    adapter = Mock()
    adapter.name = 'region'
    adapter.evaluate_flag.return_value = FlagResolutionDetails(value='eu', reason=Reason.STATIC)
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
    test_flag = feature_flag('test_flag', default=False)

    with feature_context(keys['enabled']):
        with targeting_context(keys['disabled']):
            assert test_flag.details().variant == 'enabled'
        with targeting_context(keys['disabled'], variables=[test_flag]):
            assert test_flag.details().variant == 'disabled'


def test_feature_flag_uses_the_explicit_logfire_instance():
    adapter = Mock()
    custom_logfire = Mock()
    custom_logfire._flag.return_value = adapter

    FeatureFlag('test_flag', default=False, logfire_instance=custom_logfire)

    custom_logfire._flag.assert_called_once_with('test_flag', type=bool, default=False, description=None)


class CheckoutConfig(BaseModel):
    provider: str
    retries: int


class RegionFlag(str, Enum):
    US = 'us'


class RetriesFlag(IntEnum):
    THREE = 3


class ObjectFlag(Enum):
    VALUE = ('not', 'a', 'scalar')


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
    checkout = flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))

    assert checkout.value() == CheckoutConfig(provider='stripe', retries=3)
    assert checkout.details().variant == 'fast'
    with checkout.override_for_testing(CheckoutConfig(provider='test', retries=0)):
        assert checkout.value() == CheckoutConfig(provider='test', retries=0)


def test_feature_flag_validates_test_overrides_before_installing_them():
    enabled = feature_flag('enabled', default=False)

    with pytest.raises(ValidationError, match='bool_type'):
        enabled.override_for_testing(cast(Any, object()))
    with pytest.raises(ValidationError, match='bool_type'):
        enabled._adapter.override_for_testing(cast(Any, object()))

    assert enabled.is_enabled() is False


def test_parameterized_flag_requires_an_explicit_type():
    with pytest.raises(TypeError, match=r'Pass type=\.\.\.'):
        flag('ambiguous', default=[])  # pyright: ignore[reportArgumentType]

    values = flag('values', type=list[str], default=[])
    assert values.value() == []


def test_duplicate_flag_name_is_validated_before_type_inference():
    feature_flag('duplicate', default=False)

    with pytest.raises(ValueError, match="variable with name 'duplicate' has already been registered"):
        flag('duplicate', default=[])  # pyright: ignore[reportArgumentType]


def test_typed_flag_validates_its_code_default_during_construction():
    with pytest.raises(ValidationError, match='int_parsing'):
        flag('invalid_default', type=int, default=cast(Any, 'not-an-int'))

    assert logfire.variables_get() == []


def test_openfeature_provider_uses_declared_flags_and_evaluation_context():
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
    feature_flag('test_flag', default=False)
    openfeature_api.set_provider(LogfireProvider(), domain='logfire-test')
    try:
        client = openfeature_api.get_client(domain='logfire-test')
        details = client.get_boolean_details(
            'test_flag',
            False,
            EvaluationContext(targeting_key='account-a', attributes={'plan': 'team'}),
        )
        assert details.value is True
        assert details.variant == 'enabled'
        assert details.reason == Reason.TARGETING_MATCH

        mismatch = client.get_string_details('test_flag', 'fallback')
        assert mismatch.value == 'fallback'
        assert mismatch.reason == Reason.ERROR
        assert mismatch.error_code == ErrorCode.TYPE_MISMATCH

        missing = client.get_boolean_details('missing', True)
        assert missing.value is True
        assert missing.error_code == ErrorCode.FLAG_NOT_FOUND
    finally:
        openfeature_api.clear_providers()


def test_openfeature_provider_uses_the_caller_default_on_resolution_error():
    config = VariablesConfig(
        variables={
            'test_flag': VariableConfig(
                name='test_flag',
                labels={'invalid': LabeledValue(version=1, serialized_value='"not-a-boolean"')},
                rollout=Rollout(labels={'invalid': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    feature_flag('test_flag', default=True)

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = LogfireProvider().resolve_boolean_details('test_flag', False)

    assert details.value is False
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.TYPE_MISMATCH


def test_openfeature_provider_accepts_pydantic_constrained_scalar_flags():
    flag('positive_retries', type=cast(Any, Annotated[int, Field(gt=0)]), default=3)
    flag('positive_ratio', type=cast(Any, Annotated[float, Field(gt=0)]), default=0.5)
    flag('nonempty_region', type=cast(Any, Annotated[str, Field(min_length=1)]), default='us')
    provider = LogfireProvider()

    assert provider.resolve_integer_details('positive_retries', 1).value == 3
    assert provider.resolve_float_details('positive_ratio', 0.1).value == 0.5
    assert provider.resolve_string_details('nonempty_region', 'fallback').value == 'us'


def test_openfeature_provider_accepts_literal_scalar_flags():
    flag('literal_region', type=cast(Any, Literal['us', 'eu']), default='us')
    flag('literal_retries', type=cast(Any, Literal[1, 3]), default=1)
    flag('mixed_literal', type=cast(Any, Literal['us', 1]), default='us')
    provider = LogfireProvider()

    assert provider.resolve_string_details('literal_region', 'fallback').value == 'us'
    assert provider.resolve_integer_details('literal_retries', 0).value == 1
    mismatch = provider.resolve_string_details('mixed_literal', 'fallback')
    assert mismatch.value == 'fallback'
    assert mismatch.error_code == ErrorCode.TYPE_MISMATCH


@pytest.mark.skipif(
    MUTATION_TESTING, reason='mutmut loads transformed flag and test modules under different identities'
)
def test_openfeature_provider_accepts_enum_scalar_flags():
    flag('enum_region', default=RegionFlag.US)
    flag('enum_retries', default=RetriesFlag.THREE)
    provider = LogfireProvider()

    assert provider.resolve_string_details('enum_region', 'fallback').value == 'us'
    assert provider.resolve_integer_details('enum_retries', 0).value == 3


def test_openfeature_scalar_type_matches_enum_member_values():
    adapter = Mock()
    adapter.type_adapter.core_schema = {'type': 'enum', 'members': [Mock(value='GET'), Mock(value='POST')]}

    assert _matches_openfeature_scalar_type(adapter, str) is True
    assert _matches_openfeature_scalar_type(adapter, int) is False

    adapter.type_adapter.core_schema = {
        'type': 'lax-or-strict',
        'strict_schema': {'python_schema': {'cls': RegionFlag}},
    }
    assert _matches_openfeature_scalar_type(adapter, str) is True
    assert _matches_openfeature_scalar_type(adapter, int) is False

    adapter.type_adapter.core_schema = {'type': 'lax-or-strict', 'strict_schema': {}}
    assert _matches_openfeature_scalar_type(adapter, str) is False

    for invalid_enum_type in (None, str):
        adapter.type_adapter.core_schema = {
            'type': 'lax-or-strict',
            'strict_schema': {'python_schema': {'cls': invalid_enum_type}},
        }
        assert _matches_openfeature_scalar_type(adapter, str) is False


def test_openfeature_object_schema_classification_handles_pydantic_24_enums():
    def lax_schema(enum_type: Any) -> dict[str, Any]:
        return {'type': 'lax-or-strict', 'strict_schema': {'python_schema': {'cls': enum_type}}}

    assert _is_exclusively_openfeature_scalar_schema(lax_schema(RegionFlag)) is True
    assert _is_exclusively_openfeature_scalar_schema(lax_schema(ObjectFlag)) is False
    assert _is_exclusively_openfeature_scalar_schema(lax_schema(str)) is False


def test_openfeature_provider_uses_an_explicit_logfire_instance():
    custom_logfire = Mock()

    assert LogfireProvider(custom_logfire)._logfire is custom_logfire


def test_openfeature_provider_returns_object_defaults_for_missing_flags():
    details = LogfireProvider().resolve_object_details('missing', {'fallback': True})

    assert details.value == {'fallback': True}
    assert details.error_code == ErrorCode.FLAG_NOT_FOUND


def test_openfeature_provider_reports_object_serialization_errors():
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    checkout = flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))

    with patch.object(checkout._adapter.type_adapter, 'dump_python', side_effect=RuntimeError('broken serializer')):
        details = LogfireProvider().resolve_object_details('checkout', {})

    assert details.value == {}
    assert details.error_code == ErrorCode.GENERAL
    assert details.error_message == 'Feature flag result serialization failed.'

    with patch.object(checkout._adapter.type_adapter, 'dump_python', return_value='not-an-object'):
        mismatch = LogfireProvider().resolve_object_details('checkout', {})

    assert mismatch.value == {}
    assert mismatch.error_code == ErrorCode.TYPE_MISMATCH


def test_openfeature_provider_reports_scalar_serialization_errors():
    region = flag('region', default='us')
    provider = LogfireProvider()

    with patch.object(region._adapter.type_adapter, 'dump_python', side_effect=RuntimeError('broken serializer')):
        failed = provider.resolve_string_details('region', 'fallback')

    assert failed.value == 'fallback'
    assert failed.error_code == ErrorCode.GENERAL
    assert failed.error_message == 'Feature flag result serialization failed.'

    with patch.object(region._adapter.type_adapter, 'dump_python', return_value=1):
        mismatch = provider.resolve_string_details('region', 'fallback')

    assert mismatch.value == 'fallback'
    assert mismatch.error_code == ErrorCode.TYPE_MISMATCH


def test_openfeature_provider_rejects_scalar_flags_as_objects():
    region = flag('region', default='us')

    with patch.object(region._adapter, 'evaluate_flag') as evaluate_flag:
        details = LogfireProvider().resolve_object_details('region', {})

    evaluate_flag.assert_not_called()
    assert details.value == {}
    assert details.error_code == ErrorCode.TYPE_MISMATCH


@pytest.mark.parametrize('flag_type, default', [(str | None, None), (int | str, 1)])
def test_openfeature_provider_rejects_wrapped_scalar_flags_as_objects_without_evaluating(flag_type: Any, default: Any):
    wrapped_scalar = flag('wrapped_scalar', type=flag_type, default=default)

    with patch.object(wrapped_scalar._adapter, 'evaluate_flag') as evaluate_flag:
        details = LogfireProvider().resolve_object_details('wrapped_scalar', {})

    evaluate_flag.assert_not_called()
    assert details.value == {}
    assert details.error_code == ErrorCode.TYPE_MISMATCH


def test_openfeature_object_schema_classification_allows_nullable_objects():
    adapter = flag('nullable_object', type=cast(Any, list[str] | None), default=cast(list[str] | None, None))._adapter

    assert _is_exclusively_openfeature_scalar_schema(adapter.type_adapter.core_schema) is False


def test_openfeature_provider_rejects_object_flags_as_scalars_without_evaluating():
    checkout = flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))

    with patch.object(checkout._adapter, 'evaluate_flag') as evaluate_flag:
        details = LogfireProvider().resolve_string_details('checkout', 'fallback')

    evaluate_flag.assert_not_called()
    assert details.value == 'fallback'
    assert details.error_code == ErrorCode.TYPE_MISMATCH


def test_openfeature_provider_serializes_typed_objects():
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=False),
    )
    flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))
    provider = LogfireProvider()

    details = provider.resolve_object_details('checkout', {})

    assert details.value == {'provider': 'fallback', 'retries': 1}
    assert details.reason == Reason.DEFAULT


def test_openfeature_provider_serializes_caller_default_after_validation_error():
    config = VariablesConfig(
        variables={
            'checkout': VariableConfig(
                name='checkout',
                labels={'invalid': LabeledValue(version=1, serialized_value='{"provider":7}')},
                rollout=Rollout(labels={'invalid': 1.0}),
                overrides=[],
            )
        }
    )
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag('checkout', default=CheckoutConfig(provider='fallback', retries=1))

    with pytest.warns(RuntimeWarning, match='value failed validation'):
        details = LogfireProvider().resolve_object_details('checkout', {})

    assert details.value == {}
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.TYPE_MISMATCH


def test_typed_flag_telemetry_serializes_structured_values(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    checkout = flag('checkout', default=CheckoutConfig(provider='stripe', retries=2))
    exporter.clear()

    checkout.value()

    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    assert (evaluation_span.attributes or {})['feature_flag.result.value'] == '{"provider":"stripe","retries":2}'


def test_typed_flag_telemetry_omits_scrubbed_structured_values(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    secret = flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value:
        secret.value()

    assert scrub_value.call_args_list[0].args == (
        ('attributes',),
        {'logfire.feature_flag.result.checkout_settings': {'api_key': 'super-secret'}},
    )

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
    secret = flag('json_settings', default=JsonOnlySecretConfig(payload='opaque-value'))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value:
        secret.value()

    assert scrub_value.call_args_list[0].args == (
        ('attributes',),
        {'logfire.feature_flag.result.json_settings': {'payload': {'api_key': 'opaque-value'}}},
    )
    evaluation_span = next(
        span
        for span in exporter.exported_spans
        if span.name == 'feature_flag.evaluation' and (span.attributes or {}).get('logfire.span_type') != 'pending_span'
    )
    attributes = dict(evaluation_span.attributes or {})
    assert 'feature_flag.result.value' not in attributes
    assert attributes['logfire.feature_flag.result.value_status'] == 'scrubbed'
    assert 'opaque-value' not in repr(attributes)


def test_typed_flag_telemetry_uses_serialized_value_when_dumping_fails(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    checkout = flag('checkout', default=CheckoutConfig(provider='stripe', retries=2))
    exporter.clear()
    scrubber = logfire.DEFAULT_LOGFIRE_INSTANCE.config.scrubber

    with (
        patch.object(checkout._adapter.type_adapter, 'dump_python', side_effect=RuntimeError('broken serializer')),
        patch.object(scrubber, 'scrub_value', wraps=scrubber.scrub_value) as scrub_value,
    ):
        checkout.value()

    assert scrub_value.call_args_list[0].args == (
        ('attributes',),
        {'logfire.feature_flag.result.checkout': '{"provider":"stripe","retries":2}'},
    )


def test_typed_flag_telemetry_honors_callback_replacements_without_notes(
    config_kwargs: dict[str, Any], exporter: TestExporter
):
    def replace_secret(match: logfire.ScrubMatch):
        if match.path[-1] == 'api_key':
            return '[replaced by callback]'
        return match.value

    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(scrubbing=logfire.ScrubbingOptions(callback=replace_secret), **config_kwargs)
    secret = flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
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
    region = flag('region', default='us')
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
    region = flag('region', default='us')
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
    region = flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(adapter, 'get', return_value=ResolvedVariable(name='region', value='eu', reason='resolved')),
        patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')),
    ):
        details = adapter.evaluate_flag(targeting_key='account-a')

    assert details.value == 'eu'
    assert details.reason == Reason.STATIC


def test_flag_evaluation_details_use_the_resolved_config_snapshot():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    test_flag = feature_flag('test_flag', default=False)
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

    assert details.reason == Reason.SPLIT
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

    details = feature_flag('test_flag', default=False).details(targeting_key=targeting_key)

    assert details.value is False
    assert details.reason == Reason.SPLIT


def test_provider_metadata_failure_cannot_break_rollout_warning():
    region = flag('region', default='us')
    adapter = cast(Any, region._adapter)
    provider = adapter.logfire_instance.config.get_variable_provider()

    with (
        patch.object(Variable, 'get', return_value=ResolvedVariable(name='region', value='eu', reason='resolved')),
        patch.object(provider, 'get_variable_config', side_effect=RuntimeError('broken provider')),
    ):
        assert adapter.get().value == 'eu'


def test_openfeature_provider_returns_default_when_evaluation_raises():
    enabled = feature_flag('enabled', default=False)

    with patch.object(enabled._adapter, 'evaluate_flag', side_effect=RuntimeError('sensitive provider failure')):
        details = LogfireProvider().resolve_boolean_details('enabled', True)

    assert details.value is True
    assert details.reason == Reason.ERROR
    assert details.error_code == ErrorCode.GENERAL
    assert details.error_message == 'Feature flag evaluation failed.'


def test_scrubbing_callback_failure_cannot_break_flag_evaluation(config_kwargs: dict[str, Any], exporter: TestExporter):
    config_kwargs['variables'] = LocalVariablesOptions(config=VariablesConfig(variables={}), instrument=True)
    logfire.configure(**config_kwargs)
    secret = flag('checkout_settings', default=SecretConfig(api_key='super-secret'))
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


def test_flag_construction_does_not_replace_the_global_openfeature_provider():
    class MarkerProvider(LogfireProvider):
        def get_metadata(self):
            return type(super().get_metadata())(name='marker')

    marker = MarkerProvider()
    openfeature_api.set_provider(marker)
    try:
        Flag('unrelated', default='fallback')
        assert openfeature_api.get_provider_metadata().name == marker.get_metadata().name
    finally:
        openfeature_api.clear_providers()


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
    flag = feature_flag('test_flag', default=False)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        flag.evaluate(attributes={'plan': 'team'})
        flag.evaluate(targeting_key='account-a', attributes={'plan': 'free'})
        with feature_context('account-a', attributes={'plan': 'free'}):
            flag.evaluate()
        with targeting_context('account-a', variables=[flag]):
            flag.evaluate(attributes={'plan': 'free'})
    assert caught == []

    with pytest.warns(RuntimeWarning, match='no stable targeting key') as caught:
        flag.evaluate(attributes={'plan': 'free'})
    assert len(caught) == 1


def test_feature_flags_do_not_use_inbound_trace_ids_for_targeting():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = feature_flag('test_flag', default=False)
    provider = logfire.DEFAULT_LOGFIRE_INSTANCE.config.get_variable_provider()

    with (
        patch.object(provider, 'get_serialized_value', wraps=provider.get_serialized_value) as get_serialized_value,
        logfire.span('request'),
        pytest.warns(RuntimeWarning, match='no stable targeting key'),
    ):
        flag.evaluate()

    assert get_serialized_value.call_args.args[1] is None


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
    flag = feature_flag('test_flag', default=False)

    assert flag.evaluate(targeting_key='account-a').variant == 'disabled'


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
        self.flag = feature_flag('test_flag', default=False, logfire_instance=self.logfire)
        self.contexts: list[tuple[AbstractContextManager[None], str, dict[str, str]]] = []
        self.overrides: list[tuple[AbstractContextManager[None], bool]] = []
        self.base_results = {key: self.flag.evaluate(targeting_key=key) for key in self.KEYS}

    @rule(
        targeting_key=st.sampled_from(KEYS),
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
        manager = self.flag.override_for_testing(value)
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

        details = self.flag.evaluate(targeting_key=targeting_key, attributes=attributes)

        expected_attributes: dict[str, str] = {}
        for _, _, context_attributes in self.contexts:
            expected_attributes.update(context_attributes)
        if attributes:
            expected_attributes.update(attributes)

        if self.overrides:
            expected_value = self.overrides[-1][1]
            expected_variant = None
            expected_reason = Reason.STATIC
        elif expected_attributes.get('plan') == 'team':
            expected_value = True
            expected_variant = 'enabled'
            expected_reason = Reason.TARGETING_MATCH
        elif expected_attributes.get('plan') == 'guest':
            expected_value = False
            expected_variant = 'disabled'
            expected_reason = Reason.TARGETING_MATCH
        else:
            effective_key = targeting_key if targeting_key is not None else self.contexts[-1][1]
            baseline = self.base_results[effective_key]
            expected_value = baseline.value
            expected_variant = baseline.variant
            expected_reason = baseline.reason

        assert details.value is expected_value
        assert details.variant == expected_variant
        assert details.reason == expected_reason
        assert self.flag.is_enabled(targeting_key=targeting_key, attributes=attributes) is expected_value

    @invariant()
    def evaluations_always_return_booleans(self):
        assert isinstance(self.flag.is_enabled(targeting_key='account-a'), bool)

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
    flag = feature_flag('test_flag', default=False)
    barrier = threading.Barrier(4)
    results: dict[str, bool] = {}
    results_lock = threading.Lock()

    def evaluate(name: str, plan: str):
        with feature_context(name, attributes={'plan': plan}):
            barrier.wait()
            value = flag.is_enabled()
            with results_lock:
                results[name] = value

    threads = [
        threading.Thread(target=evaluate, args=(f'user-{index}', 'team' if index % 2 else 'guest'))
        for index in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
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
    flag = feature_flag('test_flag', default=False)
    attributes = {'plan': 'team'}

    with pytest.raises(RuntimeError, match='stop setup'):
        with feature_context('account-a', attributes=attributes):
            attributes['plan'] = 'guest'
            assert flag.is_enabled() is True
            raise RuntimeError('stop setup')

    assert flag.is_enabled(targeting_key='account-a') is False


def test_feature_context_reuses_managed_variable_targeting_context():
    config = _boolean_config(rollout=Rollout(labels={'enabled': 0.5, 'disabled': 0.5}))
    logfire.configure(
        send_to_logfire=False,
        console=False,
        variables=LocalVariablesOptions(config=config, instrument=False),
    )
    flag = feature_flag('test_flag', default=False)

    def regular_default(targeting_key: str | None, _attributes: Mapping[str, object] | None) -> str:
        return targeting_key or 'no-targeting-key'

    regular_variable = logfire.var('regular_variable', type=str, default=regular_default)

    with targeting_context('regular-variable-key'):
        with feature_context('feature-flag-key', attributes={'plan': 'team'}):
            assert regular_variable.get().value == 'feature-flag-key'
            assert flag.evaluate().variant == config.variables['test_flag'].resolve_label('feature-flag-key')

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
            assert flag.evaluate().variant == config.variables['test_flag'].resolve_label('specific-feature-flag-key')
