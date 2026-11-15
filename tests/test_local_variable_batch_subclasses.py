import pytest

from logfire.variables.abstract import VariableNotFoundError
from logfire.variables.config import Rollout, RolloutOverride, ValueEquals, VariableConfig, VariablesConfig
from logfire.variables.local import LocalVariableProvider


def test_subclass_batch_writes_use_overrides_and_remain_atomic() -> None:
    class CustomLocalProvider(LocalVariableProvider):
        def __init__(self, config: VariablesConfig):
            super().__init__(config)
            self.operations: list[tuple[str, str]] = []

        def create_variable(self, config: VariableConfig) -> VariableConfig:
            self.operations.append(('create', config.name))
            return super().create_variable(config)

        def update_variable(self, name: str, config: VariableConfig) -> VariableConfig:
            self.operations.append(('update', name))
            return super().update_variable(name, config)

        def delete_variable(self, name: str) -> None:
            self.operations.append(('delete', name))
            super().delete_variable(name)

    existing = VariableConfig(name='existing', rollout=Rollout(labels={}), overrides=[])
    obsolete = VariableConfig(name='obsolete', rollout=Rollout(labels={}), overrides=[])
    updated = existing.model_copy(update={'description': 'updated'})
    created = VariableConfig(name='created', rollout=Rollout(labels={}), overrides=[])
    config = VariablesConfig(variables={'existing': existing, 'obsolete': obsolete})
    provider = CustomLocalProvider(config)

    provider.batch_update({'existing': updated, 'created': created, 'obsolete': None})
    assert provider.operations == [('update', 'existing'), ('create', 'created'), ('delete', 'obsolete')]
    assert config.variables == {'existing': updated, 'created': created}
    assert provider.get_variable_config('created') == created

    before = provider.get_all_variables_config()
    with pytest.raises(VariableNotFoundError, match="Variable 'missing' not found"):
        provider.batch_update({'created': None, 'missing': None})

    assert provider.operations[-2:] == [('delete', 'created'), ('delete', 'missing')]
    assert provider.get_all_variables_config() == before
    assert config == before


def test_subclass_in_place_mutation_is_rolled_back() -> None:
    class InPlaceMutatingLocalProvider(LocalVariableProvider):
        def update_variable(self, name: str, config: VariableConfig) -> VariableConfig:
            self._config.variables[name].description = 'mutated in place'
            return super().update_variable(name, config)

    existing = VariableConfig(name='existing', description='original', rollout=Rollout(labels={}), overrides=[])
    config = VariablesConfig(variables={'existing': existing})
    provider = InPlaceMutatingLocalProvider(config)
    before = provider.get_all_variables_config()
    replacement = existing.model_copy(update={'description': 'replacement'})

    with pytest.raises(VariableNotFoundError, match="Variable 'missing' not found"):
        provider.batch_update({'existing': replacement, 'missing': None})

    assert config == before
    assert config.variables['existing'] is existing
    assert existing.description == 'original'


def test_batch_keeps_untouched_variable_identity() -> None:
    existing = VariableConfig(name='existing', rollout=Rollout(labels={}), overrides=[])
    config = VariablesConfig(variables={'existing': existing})
    provider = LocalVariableProvider(config)
    held = provider.get_variable_config('existing')
    assert held is existing
    assert held is not None

    provider.batch_update({})
    assert provider.get_variable_config('existing') is held

    created = VariableConfig(name='created', rollout=Rollout(labels={}), overrides=[])
    provider.batch_update({'created': created})
    assert provider.get_variable_config('existing') is held
    held.description = 'still live'
    assert held.description == 'still live'


def test_batch_does_not_copy_opaque_values() -> None:
    class IdentitySensitive:
        def __deepcopy__(self, memo: object) -> None:
            raise AssertionError('must not copy an opaque condition or schema value')

    opaque = IdentitySensitive()
    existing = VariableConfig(
        name='existing',
        rollout=Rollout(labels={}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='key', value=opaque)],
                rollout=Rollout(labels={}),
            )
        ],
        json_schema={'metadata': {'opaque': opaque}},
    )
    provider = LocalVariableProvider(VariablesConfig(variables={'existing': existing}))

    provider.batch_update({'created': VariableConfig(name='created', rollout=Rollout(labels={}), overrides=[])})
    assert provider.get_variable_config('existing') is existing
    condition = existing.overrides[0].conditions[0]
    assert isinstance(condition, ValueEquals)
    assert condition.value is opaque
    assert existing.json_schema is not None
    assert existing.json_schema['metadata']['opaque'] is opaque



def test_batch_preserves_any_value_identity_inside_subclass_hook() -> None:
    opaque_mapping = {'identity': object()}
    existing = VariableConfig(
        name='existing',
        rollout=Rollout(labels={}),
        overrides=[
            RolloutOverride(
                conditions=[ValueEquals(attribute='key', value=opaque_mapping)],
                rollout=Rollout(labels={}),
            )
        ],
    )

    class IdentityCheckingProvider(LocalVariableProvider):
        def create_variable(self, config: VariableConfig) -> VariableConfig:
            condition = self._config.variables['existing'].overrides[0].conditions[0]
            assert isinstance(condition, ValueEquals)
            assert condition.value is opaque_mapping
            return super().create_variable(config)

    provider = IdentityCheckingProvider(VariablesConfig(variables={'existing': existing}))
    provider.batch_update({'created': VariableConfig(name='created', rollout=Rollout(labels={}), overrides=[])})
    assert provider.get_variable_config('existing') is existing
