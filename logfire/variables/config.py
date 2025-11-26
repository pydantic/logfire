from __future__ import annotations as _annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Discriminator, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import TypeAliasType

from logfire.variables.variable import Variable


@dataclass(kw_only=True)
class ValueEquals:
    attribute: str
    value: Any
    kind: Literal['value-equals'] = 'value-equals'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        return attributes.get(self.attribute, object()) == self.value


@dataclass(kw_only=True)
class ValueDoesNotEqual:
    attribute: str
    value: Any
    kind: Literal['value-does-not-equal'] = 'value-does-not-equal'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        return attributes.get(self.attribute, object()) != self.value


@dataclass(kw_only=True)
class ValueIsIn:
    attribute: str
    values: Sequence[Any]
    kind: Literal['value-is-in'] = 'value-is-in'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        value = attributes.get(self.attribute, object())
        return value in self.values


@dataclass(kw_only=True)
class ValueIsNotIn:
    attribute: str
    values: Sequence[Any]
    kind: Literal['value-is-not-in'] = 'value-is-not-in'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        value = attributes.get(self.attribute, object())
        return value not in self.values


@dataclass(kw_only=True)
class ValueMatchesRegex:
    attribute: str
    pattern: str | re.Pattern[str]
    kind: Literal['value-matches-regex'] = 'value-matches-regex'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        value = attributes.get(self.attribute)
        if not isinstance(value, str):
            return False
        return bool(re.search(self.pattern, value))


@dataclass(kw_only=True)
class ValueDoesNotMatchRegex:
    attribute: str
    pattern: str | re.Pattern[str]
    kind: Literal['value-does-not-match-regex'] = 'value-does-not-match-regex'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        value = attributes.get(self.attribute)
        if not isinstance(value, str):
            return False
        return bool(re.search(self.pattern, value))


@dataclass(kw_only=True)
class KeyIsPresent:
    attribute: str
    kind: Literal['key-is-present'] = 'key-is-present'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        return self.attribute in attributes


@dataclass(kw_only=True)
class KeyIsNotPresent:
    attribute: str
    kind: Literal['key-is-not-present'] = 'key-is-not-present'

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        return self.attribute not in attributes


Condition = TypeAliasType(
    'Condition',
    Annotated[
        ValueEquals
        | ValueDoesNotEqual
        | ValueIsIn
        | ValueIsNotIn
        | ValueMatchesRegex
        | ValueDoesNotMatchRegex
        | KeyIsPresent
        | KeyIsNotPresent,
        Discriminator('kind'),
    ],
)


VariantKey = str
VariableName = str

# TODO: Do we need to make the following dataclasses into pydantic dataclasses or BaseModels so the validators run when
#  initializing (and not just when deserializing with a TypeAdapter)?


@dataclass(kw_only=True)
class Rollout:
    variants: dict[VariantKey, float]

    @field_validator('variants')
    @classmethod
    def _validate_variant_proportions(cls, v: dict[VariantKey, float]):
        # Note: if the values sum to _less_ than 1, the remaining proportion corresponds to the probability of using
        # the code default.
        if sum(v.values()) > 1:
            raise ValueError('Variant proportions must not sum to more than 1.')
        return v

    def select_variant(self, seed: str | None) -> VariantKey | None:
        rand = random.Random(seed)

        population: list[VariantKey | None] = []
        weights: list[float] = []
        for k, v in self.variants.items():
            population.append(k)
            weights.append(v)

        p_code_default = 1 - sum(weights)
        if p_code_default > 0:
            population.append(None)
            weights.append(p_code_default)

        return rand.choices(population, weights)[0]


@dataclass(kw_only=True)
class Variant:
    key: VariantKey
    serialized_value: str
    # format: Literal['json', 'yaml']  # TODO: Consider supporting yaml, and not just JSON; allows comments and better formatting
    description: str | None = None
    version: str | None = None  # TODO: should this be required?


@dataclass(kw_only=True)
class RolloutOverride:
    conditions: list[Condition]
    rollout: Rollout


@dataclass(kw_only=True)
class VariableConfig:
    name: VariableName
    variants: dict[VariantKey, Variant]
    rollout: Rollout
    overrides: list[RolloutOverride]  # first match takes precedence
    json_schema: dict[str, Any]
    # TODO: Should we add a validator that all variants match the provided JSON schema?

    @model_validator(mode='after')
    def _validate_variants(self):
        # Validate lookup keys on variants dict
        for k, v in self.variants.items():
            if v.key != k:
                raise ValueError(f'`variants` has invalid lookup key {k!r} for value with key {v.key!r}.')

        # Validate rollout variant references
        for k, v in self.rollout.variants.items():
            if k not in self.variants:
                raise ValueError(f'Variant {k!r} present in `rollout.variants` is not present in `variants`.')

        # Validate rollout override variant references
        for i, override in enumerate(self.overrides):
            for k, v in override.rollout.variants.items():
                if k not in self.variants:
                    raise ValueError(f'Variant {k!r} present in `overrides[{i}].rollout` is not present in `variants`.')

        return self

    def resolve_variant(
        self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> Variant | None:
        """Evaluate a managed variable configuration and return the serialized value.

        Args:
            targeting_key: A string identifying the subject of evaluation (e.g., user ID)
            attributes: Additional attributes for condition matching

        Returns:
            The serialized value of the selected variant, or None if no variant is selected
        """
        if attributes is None:
            attributes = {}

        # Step 1: Find the first matching override, or use the base rollout
        selected_rollout = self.rollout
        for override in self.overrides:
            if _matches_all_conditions(override.conditions, attributes):
                selected_rollout = override.rollout
                break  # First match takes precedence

        seed = None if targeting_key is None else f'{self.name!r}:{targeting_key!r}'
        selected_variant_key = selected_rollout.select_variant(seed)

        if selected_variant_key is None:
            return None

        return self.variants[selected_variant_key]


@dataclass(kw_only=True)
class VariablesConfig:
    variables: dict[VariableName, VariableConfig]

    @model_validator(mode='after')
    def _validate_variables(self):
        # Validate lookup keys on variants dict
        for k, v in self.variables.items():
            if v.name != k:
                raise ValueError(f'`variables` has invalid lookup key {k!r} for value with name {v.name!r}.')
        return self

    def get_validation_errors(self, variables: list[Variable[Any]]) -> dict[str, dict[str | None, Exception]]:
        errors: dict[str, dict[str | None, Exception]] = {}
        for variable in variables:
            try:
                config = self.variables.get(variable.name)
                if config is None:
                    raise ValueError(f'No config for variable with name {variable.name!r}')
                for k, v in config.variants.items():
                    try:
                        variable.type_adapter.validate_json(v.serialized_value)
                    except ValidationError as e:
                        errors[variable.name][k] = e
            except Exception as e:
                errors[variable.name][None] = e
        return errors

    @staticmethod
    def validate_python(data: Any) -> VariablesConfig:
        return _VariablesConfigAdapter.validate_python(data)


_VariablesConfigAdapter = TypeAdapter(VariablesConfig)


def _matches_all_conditions(conditions: list[Condition], attributes: Mapping[str, Any]) -> bool:
    """Check if all conditions match the provided attributes."""
    for condition in conditions:
        if not condition.matches(attributes):
            return False
    return True
