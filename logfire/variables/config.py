from __future__ import annotations as _annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import Discriminator, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import TypeAliasType

from logfire._internal.config import RemoteVariablesConfig as RemoteVariablesConfig
from logfire.variables.abstract import ResolvedVariable
from logfire.variables.variable import Variable

__all__ = (
    'KeyIsNotPresent',
    'KeyIsPresent',
    'RemoteVariablesConfig',
    'Rollout',
    'RolloutOverride',
    'ValueDoesNotEqual',
    'ValueDoesNotMatchRegex',
    'ValueEquals',
    'ValueIsIn',
    'ValueIsNotIn',
    'ValueMatchesRegex',
    'VariableConfig',
    'VariablesConfig',
    'Variant',
)


@dataclass(kw_only=True)
class ValueEquals:
    """Condition that matches when an attribute equals a specific value."""

    attribute: str
    """The name of the attribute to check."""
    value: Any
    """The value the attribute must equal."""
    kind: Literal['value-equals'] = 'value-equals'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute equals the expected value."""
        return attributes.get(self.attribute, object()) == self.value


@dataclass(kw_only=True)
class ValueDoesNotEqual:
    """Condition that matches when an attribute does not equal a specific value."""

    attribute: str
    """The name of the attribute to check."""
    value: Any
    """The value the attribute must not equal."""
    kind: Literal['value-does-not-equal'] = 'value-does-not-equal'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute does not equal the specified value."""
        return attributes.get(self.attribute, object()) != self.value


@dataclass(kw_only=True)
class ValueIsIn:
    """Condition that matches when an attribute value is in a set of values."""

    attribute: str
    """The name of the attribute to check."""
    values: Sequence[Any]
    """The set of values the attribute must be in."""
    kind: Literal['value-is-in'] = 'value-is-in'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value is in the allowed set."""
        value = attributes.get(self.attribute, object())
        return value in self.values


@dataclass(kw_only=True)
class ValueIsNotIn:
    """Condition that matches when an attribute value is not in a set of values."""

    attribute: str
    """The name of the attribute to check."""
    values: Sequence[Any]
    """The set of values the attribute must not be in."""
    kind: Literal['value-is-not-in'] = 'value-is-not-in'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value is not in the excluded set."""
        value = attributes.get(self.attribute, object())
        return value not in self.values


@dataclass(kw_only=True)
class ValueMatchesRegex:
    """Condition that matches when an attribute value matches a regex pattern."""

    attribute: str
    """The name of the attribute to check."""
    pattern: str | re.Pattern[str]
    """The regex pattern the attribute value must match."""
    kind: Literal['value-matches-regex'] = 'value-matches-regex'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value matches the regex pattern."""
        value = attributes.get(self.attribute)
        if not isinstance(value, str):
            return False
        return bool(re.search(self.pattern, value))


@dataclass(kw_only=True)
class ValueDoesNotMatchRegex:
    """Condition that matches when an attribute value does not match a regex pattern."""

    attribute: str
    """The name of the attribute to check."""
    pattern: str | re.Pattern[str]
    """The regex pattern the attribute value must not match."""
    kind: Literal['value-does-not-match-regex'] = 'value-does-not-match-regex'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value does not match the regex pattern."""
        value = attributes.get(self.attribute)
        if not isinstance(value, str):
            return False
        return not re.search(self.pattern, value)


@dataclass(kw_only=True)
class KeyIsPresent:
    """Condition that matches when an attribute key is present."""

    attribute: str
    """The name of the attribute key that must be present."""
    kind: Literal['key-is-present'] = 'key-is-present'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute key exists in the attributes."""
        return self.attribute in attributes


@dataclass(kw_only=True)
class KeyIsNotPresent:
    """Condition that matches when an attribute key is not present."""

    attribute: str
    """The name of the attribute key that must not be present."""
    kind: Literal['key-is-not-present'] = 'key-is-not-present'
    """Discriminator field for condition type."""

    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute key does not exist in the attributes."""
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
    """Configuration for variant selection with weighted probabilities."""

    variants: dict[VariantKey, float]
    """Mapping of variant keys to their selection weights (must sum to at most 1.0)."""

    def __post_init__(self):
        # pre-compute the population and weights.
        # Note that this means that the `variants` field should be treated as immutable
        population: list[VariantKey | None] = []
        weights: list[float] = []
        for k, v in self.variants.items():
            population.append(k)
            weights.append(v)

        p_code_default = 1 - sum(weights)
        if p_code_default > 0:
            population.append(None)
            weights.append(p_code_default)

        self._population = population
        self._weights = weights

    @field_validator('variants')
    @classmethod
    def _validate_variant_proportions(cls, v: dict[VariantKey, float]):
        # Note: if the values sum to _less_ than 1, the remaining proportion corresponds to the probability of using
        # the code default.
        if sum(v.values()) > 1:
            raise ValueError('Variant proportions must not sum to more than 1.')
        return v

    def select_variant(self, seed: str | None) -> VariantKey | None:
        """Select a variant based on configured weights using optional seeded randomness.

        Args:
            seed: Optional seed for deterministic variant selection. If provided, the same seed
                will always select the same variant.

        Returns:
            The key of the selected variant, or None if no variant is selected (when weights sum to less than 1.0).
        """
        rand = random.Random(seed)
        return rand.choices(self._population, self._weights)[0]


@dataclass(kw_only=True)
class Variant:
    """A specific variant of a managed variable with its serialized value."""

    key: VariantKey
    """Unique identifier for this variant."""
    serialized_value: str
    """The JSON-serialized value for this variant."""
    # format: Literal['json', 'yaml']  # TODO: Consider supporting yaml, and not just JSON; allows comments and better formatting
    description: str | None = None
    """Optional human-readable description of this variant."""
    version: int | None = None  # TODO: should this be required? should this be `str`?
    """Optional version identifier for this variant."""


@dataclass(kw_only=True)
class RolloutOverride:
    """An override of the default rollout when specific conditions are met."""

    conditions: list[Condition]
    """List of conditions that must all match for this override to apply."""
    rollout: Rollout
    """The rollout configuration to use when all conditions match."""


@dataclass(kw_only=True)
class VariableConfig:
    """Configuration for a single managed variable including variants and rollout rules."""

    # A note on migrations:
    # * To migrate value types, copy the variable using a new name, update the values, and use the new variable name in updated code
    # * To migrate variable names, update the "aliases" field of the outer `VariablesConfig`
    name: VariableName  # TODO: What restrictions should we add on allowed characters?
    """Unique name identifying this variable."""
    description: str | None = None
    """Description of the variable."""
    variants: dict[VariantKey, Variant]
    """Mapping of variant keys to their configurations."""
    rollout: Rollout
    """Default rollout configuration for variant selection."""
    overrides: list[RolloutOverride]
    """Conditional overrides evaluated in order; first match takes precedence."""
    json_schema: dict[str, Any] | None = None
    """JSON schema describing the expected type of this variable's values."""
    # TODO: Consider adding config-based management of targeting_key, rather than requiring the value at the call-site
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

        # Validate schedule stage variant references
        # if self.schedule is not None:
        #     for stage_idx, stage in enumerate(self.schedule.stages):
        #         for k, v in stage.rollout.variants.items():
        #             if k not in self.variants:
        #                 raise ValueError(
        #                     f'Variant {k!r} present in `schedule.stages[{stage_idx}].rollout` is not present in `variants`.'
        #                 )
        #         for override_idx, override in enumerate(stage.overrides):
        #             for k, v in override.rollout.variants.items():
        #                 if k not in self.variants:
        #                     raise ValueError(
        #                         f'Variant {k!r} present in `schedule.stages[{stage_idx}].overrides[{override_idx}].rollout` '
        #                         f'is not present in `variants`.'
        #                     )

        return self

    def resolve_variant(
        self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> Variant | None:
        """Evaluate a managed variable configuration and return the selected variant.

        The resolution process:
        1. Check if there's an active rollout schedule with a current stage
        2. If a schedule stage is active, use that stage's rollout and overrides
        3. Otherwise, use the base rollout and overrides from this config
        4. Evaluate overrides in order; the first match takes precedence
        5. Select a variant based on the rollout weights (deterministic if targeting_key is provided)

        Args:
            targeting_key: A string identifying the subject of evaluation (e.g., user ID).
                When provided, ensures deterministic variant selection for the same key.
            attributes: Additional attributes for condition matching in override rules.

        Returns:
            The selected Variant, or None if no variant is selected (can happen when
            rollout weights sum to less than 1.0).
        """
        if attributes is None:
            attributes = {}

        # Step 1: Determine the rollout and overrides to use (from schedule or base config)
        base_rollout = self.rollout
        base_overrides = self.overrides

        # if self.schedule is not None:
        #     active_stage = self.schedule.get_active_stage()
        #     if active_stage is not None:
        #         base_rollout = active_stage.rollout
        #         base_overrides = active_stage.overrides

        # Step 2: Find the first matching override, or use the base rollout
        selected_rollout = base_rollout
        for override in base_overrides:
            if _matches_all_conditions(override.conditions, attributes):
                selected_rollout = override.rollout
                break  # First match takes precedence

        seed = None if targeting_key is None else f'{self.name!r}:{targeting_key!r}'
        selected_variant_key = selected_rollout.select_variant(seed)

        if selected_variant_key is None:
            return None

        return self.variants[selected_variant_key]

    @staticmethod
    def validate_python(data: Any) -> VariableConfig:
        """Parse and validate a VariablesConfig from a Python object.

        Args:
            data: A Python object (typically a dict) to validate as a VariablesConfig.

        Returns:
            A validated VariablesConfig instance.
        """
        return _VariableConfigAdapter.validate_python(data)


_VariableConfigAdapter = TypeAdapter(VariableConfig)


@dataclass(kw_only=True)
class VariablesConfig:
    """Container for all managed variable configurations."""

    variables: dict[VariableName, VariableConfig]
    """Mapping of variable names to their configurations."""

    aliases: dict[VariableName, VariableName] | None = None
    """Variable name aliases; useful for name migrations.

    If you attempt to retrieve a variable that is not a member of the `variables` mapping, the lookup will fall back to
    looking for the name as a key of this mapping. If present, the corresponding value will be used to look in the
    variables mapping.
    """

    @model_validator(mode='after')
    def _validate_variables(self):
        # Validate lookup keys on variants dict
        for k, v in self.variables.items():
            if v.name != k:
                raise ValueError(f'`variables` has invalid lookup key {k!r} for value with name {v.name!r}.')
        return self

    def resolve_serialized_value(
        self, name: VariableName, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None
    ) -> ResolvedVariable[str | None]:
        """Evaluate a managed variable configuration and resolve the selected variant's serialized value."""
        variable_config = self._get_variable_config(name)
        if variable_config is None:
            return ResolvedVariable(name=name, value=None, _reason='unrecognized_variable')

        variant = variable_config.resolve_variant(targeting_key, attributes)
        if variant is None:
            return ResolvedVariable(name=variable_config.name, value=None, _reason='resolved')
        else:
            return ResolvedVariable(
                name=variable_config.name, value=variant.serialized_value, variant=variant.key, _reason='resolved'
            )

    def _get_variable_config(self, name: VariableName) -> VariableConfig | None:
        working_name: VariableName | None = name
        config = self.variables.get(working_name)

        if aliases := self.aliases:
            visited = {working_name}
            while config is None:
                working_name = aliases.get(working_name)
                if working_name is None:
                    return None
                if working_name in visited:
                    return None  # alias cycle
                visited.add(working_name)
                config = self.variables.get(working_name)

        return config

    def get_validation_errors(self, variables: list[Variable[Any]]) -> dict[str, dict[str | None, Exception]]:
        """Validate that all variable variants can be deserialized to their expected types.

        Args:
            variables: List of Variable instances to validate against this configuration.

        Returns:
            A dict mapping variable names to dicts of variant keys (or None for general errors) to exceptions.
        """
        errors: dict[str, dict[str | None, Exception]] = {}
        for variable in variables:
            try:
                config = self._get_variable_config(variable.name)
                if config is None:
                    raise ValueError(f'No config for variable with name {variable.name!r}')
                for k, v in config.variants.items():
                    try:
                        variable.type_adapter.validate_json(v.serialized_value)
                    except ValidationError as e:
                        errors.setdefault(variable.name, {})[k] = e
            except Exception as e:
                errors.setdefault(variable.name, {})[None] = e
        return errors

    @staticmethod
    def validate_python(data: Any) -> VariablesConfig:
        """Parse and validate a VariablesConfig from a Python object.

        Args:
            data: A Python object (typically a dict) to validate as a VariablesConfig.

        Returns:
            A validated VariablesConfig instance.
        """
        return _VariablesConfigAdapter.validate_python(data)


_VariablesConfigAdapter = TypeAdapter(VariablesConfig)


def _matches_all_conditions(conditions: list[Condition], attributes: Mapping[str, Any]) -> bool:
    """Check if all conditions match the provided attributes.

    Args:
        conditions: List of conditions to evaluate.
        attributes: Attributes to match against.

    Returns:
        True if all conditions match, False otherwise.
    """
    for condition in conditions:
        if not condition.matches(attributes):
            return False
    return True
