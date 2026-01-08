from __future__ import annotations as _annotations

import json
import os
import random
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal, Union

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import TypeAliasType

from logfire._internal.config import RemoteVariablesConfig as RemoteVariablesConfig
from logfire.variables.abstract import ResolvedVariable
from logfire.variables.variable import Variable

VariablesConfigFormat = Literal['json', 'yaml']

try:
    from pydantic import Discriminator
except ImportError:
    # This is only used in an annotation, so if you have Pydantic < 2.5, just treat it as a no-op
    def Discriminator(*args: Any, **kwargs: Any) -> Any:
        pass


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
    'VariablesConfigFormat',
)

if not TYPE_CHECKING:  # pragma: no branch
    if sys.version_info < (3, 10):
        _dataclass = dataclass

        # Note: When we drop support for python 3.9, drop this
        # Prevent errors when using kw_only with dataclasses in Python<3.10
        def dataclass(*args, **kwargs):
            kwargs.pop('kw_only', None)
            return _dataclass(*args, **kwargs)


# TODO: Convert these all to BaseModel
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
        Union[
            ValueEquals,
            ValueDoesNotEqual,
            ValueIsIn,
            ValueIsNotIn,
            ValueMatchesRegex,
            ValueDoesNotMatchRegex,
            KeyIsPresent,
            KeyIsNotPresent,
        ],
        Discriminator('kind'),
    ],
)


VariantKey = Annotated[str, Field(pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$')]
"""The identifier of a variant value for a variable.

At least for now, must be a valid Python identifier."""
VariableName = Annotated[str, Field(pattern=r'^[a-zA-Z_][a-zA-Z0-9_]*$')]
"""The name of a variable.

At least for now, must be a valid Python identifier."""

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

    def to_dict(self) -> dict[str, Any]:
        """Convert this rollout to a dictionary representation."""
        return {'variants': self.variants}


@dataclass(kw_only=True)
class Variant:
    """A specific variant of a managed variable with its serialized value."""

    key: VariantKey
    """Unique identifier for this variant."""
    serialized_value: str
    """The JSON-serialized value for this variant."""
    description: str | None = None
    """Optional human-readable description of this variant."""
    version: int | None = None  # TODO: should this be required? should this be `str`?
    """Optional version identifier for this variant."""

    def to_dict(self) -> dict[str, Any]:
        """Convert this variant to a dictionary representation."""
        result: dict[str, Any] = {
            'key': self.key,
            'serialized_value': self.serialized_value,
        }
        if self.description is not None:
            result['description'] = self.description
        if self.version is not None:
            result['version'] = self.version
        return result


@dataclass(kw_only=True)
class RolloutOverride:
    """An override of the default rollout when specific conditions are met."""

    conditions: list[Condition]
    """List of conditions that must all match for this override to apply."""
    rollout: Rollout
    """The rollout configuration to use when all conditions match."""

    def to_dict(self) -> dict[str, Any]:
        """Convert this rollout override to a dictionary representation."""
        return {
            'conditions': [_condition_to_dict(c) for c in self.conditions],
            'rollout': self.rollout.to_dict(),
        }


def _condition_to_dict(condition: Condition) -> dict[str, Any]:
    """Convert a condition to a dictionary representation."""
    result: dict[str, Any] = {'kind': condition.kind, 'attribute': condition.attribute}

    # Handle conditions with 'value' field
    if isinstance(condition, (ValueEquals, ValueDoesNotEqual)):
        result['value'] = condition.value
    # Handle conditions with 'values' field
    elif isinstance(condition, (ValueIsIn, ValueIsNotIn)):
        result['values'] = list(condition.values)
    # Handle conditions with 'pattern' field
    elif isinstance(condition, (ValueMatchesRegex, ValueDoesNotMatchRegex)):
        pattern = condition.pattern
        result['pattern'] = pattern.pattern if isinstance(pattern, re.Pattern) else pattern
    # KeyIsPresent and KeyIsNotPresent only have 'attribute' and 'kind'

    return result


@dataclass(kw_only=True)
class VariableConfig:
    """Configuration for a single managed variable including variants and rollout rules."""

    # A note on migrations:
    # * To migrate value types, copy the variable using a new name, update the values, and use the new variable name in updated code
    # * To migrate variable names, update the "aliases" field on the VariableConfig
    name: VariableName  # TODO: What restrictions should we add on allowed characters?
    """Unique name identifying this variable."""
    variants: dict[VariantKey, Variant]
    """Mapping of variant keys to their configurations."""
    rollout: Rollout
    """Default rollout configuration for variant selection."""
    overrides: list[RolloutOverride]
    """Conditional overrides evaluated in order; first match takes precedence."""
    description: str | None = (
        None  # Note: When we drop support for python 3.9, move this field immediately after `name`
    )
    """Description of the variable."""
    json_schema: dict[str, Any] | None = None
    """JSON schema describing the expected type of this variable's values."""
    aliases: list[VariableName] | None = None
    """Alternative names that resolve to this variable; useful for name migrations."""
    example: str | None = None
    """JSON-serialized example value from code; used as a template when creating new variants in the UI."""
    # TODO: Consider adding config-based management of targeting_key, rather than requiring the value at the call-site

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
        for i, override in enumerate(self.overrides):  # pragma: no branch
            for k, v in override.rollout.variants.items():  # pragma: no branch
                if k not in self.variants:  # pragma: no branch
                    raise ValueError(f'Variant {k!r} present in `overrides[{i}].rollout` is not present in `variants`.')

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

    def to_dict(self) -> dict[str, Any]:
        """Convert this variable config to a dictionary representation.

        This can be used to serialize the config to JSON or YAML.
        """
        result: dict[str, Any] = {
            'name': self.name,
            'variants': {k: v.to_dict() for k, v in self.variants.items()},
            'rollout': self.rollout.to_dict(),
            'overrides': [o.to_dict() for o in self.overrides],
        }
        if self.description is not None:
            result['description'] = self.description
        if self.json_schema is not None:
            result['json_schema'] = self.json_schema
        if self.aliases is not None:
            result['aliases'] = self.aliases
        if self.example is not None:
            result['example'] = self.example
        return result


_VariableConfigAdapter = TypeAdapter(VariableConfig)


@dataclass(kw_only=True)
class VariablesConfig:
    """Container for all managed variable configurations."""

    variables: dict[VariableName, VariableConfig]
    """Mapping of variable names to their configurations."""

    @model_validator(mode='after')
    def _validate_variables(self):
        # Validate lookup keys on variants dict
        for k, v in self.variables.items():
            if v.name != k:
                raise ValueError(f'`variables` has invalid lookup key {k!r} for value with name {v.name!r}.')
        return self

    def __post_init__(self):
        # Build alias lookup map for efficient lookups
        self._alias_map: dict[VariableName, VariableName] = {}
        for var_config in self.variables.values():
            if var_config.aliases:
                for alias in var_config.aliases:
                    self._alias_map[alias] = var_config.name

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
        # First try direct lookup
        config = self.variables.get(name)
        if config is not None:
            return config

        # Fall back to alias lookup (aliases are stored on each VariableConfig)
        if hasattr(self, '_alias_map') and name in self._alias_map:
            return self.variables.get(self._alias_map[name])

        return None

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

    def to_dict(self) -> dict[str, Any]:
        """Convert this variables config to a dictionary representation.

        Returns:
            A dict with the variables configuration.
        """
        return {'variables': {k: v.to_dict() for k, v in self.variables.items()}}

    def to_json(self, *, indent: int | None = 2) -> str:
        """Convert this variables config to a JSON string.

        Args:
            indent: Indentation level for pretty printing. Default is 2.

        Returns:
            A JSON string representation of the config.
        """
        return json.dumps(self.to_dict(), indent=indent)

    def to_yaml(self) -> str:
        """Convert this variables config to a YAML string.

        Returns:
            A YAML string representation of the config.

        Raises:
            ImportError: If PyYAML is not installed.
        """
        try:
            import yaml
        except ImportError as e:
            raise ImportError('PyYAML is required for YAML support. Install with: pip install pyyaml') from e

        return yaml.safe_dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    @staticmethod
    def from_json(data: str) -> VariablesConfig:
        """Parse a VariablesConfig from a JSON string.

        Args:
            data: A JSON string to parse.

        Returns:
            A validated VariablesConfig instance.
        """
        return VariablesConfig.validate_python(json.loads(data))

    @staticmethod
    def from_yaml(data: str) -> VariablesConfig:
        """Parse a VariablesConfig from a YAML string.

        Args:
            data: A YAML string to parse.

        Returns:
            A validated VariablesConfig instance.

        Raises:
            ImportError: If PyYAML is not installed.
        """
        try:
            import yaml
        except ImportError as e:
            raise ImportError('PyYAML is required for YAML support. Install with: pip install pyyaml') from e

        return VariablesConfig.validate_python(yaml.safe_load(data))

    def write(self, path: str | os.PathLike[str], format: VariablesConfigFormat | None = None) -> None:
        """Write the variables config to a file.

        Args:
            path: Path to write the config to.
            format: The format to use ('json' or 'yaml'). If not specified, inferred from the file extension.

        Raises:
            ValueError: If the format cannot be determined.
        """
        path = Path(path)
        if format is None:
            suffix = path.suffix.lower()
            if suffix in ('.yaml', '.yml'):
                format = 'yaml'
            elif suffix == '.json':
                format = 'json'
            else:
                raise ValueError(
                    f"Cannot determine format from extension '{suffix}'. Use format='json' or format='yaml'."
                )

        if format == 'yaml':
            content = self.to_yaml()
        else:
            content = self.to_json()

        path.write_text(content)

    @staticmethod
    def read(path: str | os.PathLike[str], format: VariablesConfigFormat | None = None) -> VariablesConfig:
        """Read a variables config from a file.

        Args:
            path: Path to the config file.
            format: The format of the file ('json' or 'yaml'). If not specified, inferred from the file extension.

        Returns:
            A validated VariablesConfig instance.

        Raises:
            ValueError: If the format cannot be determined.
        """
        path = Path(path)
        if format is None:
            suffix = path.suffix.lower()
            if suffix in ('.yaml', '.yml'):
                format = 'yaml'
            elif suffix == '.json':
                format = 'json'
            else:
                raise ValueError(
                    f"Cannot determine format from extension '{suffix}'. Use format='json' or format='yaml'."
                )

        content = path.read_text()
        if format == 'yaml':
            return VariablesConfig.from_yaml(content)
        else:
            return VariablesConfig.from_json(content)

    @staticmethod
    def from_variables(variables: list[Variable[Any]]) -> VariablesConfig:
        """Create a VariablesConfig from a list of Variable instances.

        This creates a minimal config with just the name, schema, and example for each variable.
        No variants are created - use this to generate a template config that can be edited.

        Args:
            variables: List of Variable instances to create configs from.

        Returns:
            A VariablesConfig with minimal configs for each variable.
        """
        from logfire.variables.variable import is_resolve_function

        variable_configs: dict[VariableName, VariableConfig] = {}
        for variable in variables:
            # Get JSON schema from the type adapter
            json_schema = variable.type_adapter.json_schema()

            # Get the serialized default value as an example (if not a function)
            example: str | None = None
            if not is_resolve_function(variable.default):
                example = variable.type_adapter.dump_json(variable.default).decode('utf-8')

            config = VariableConfig(
                name=variable.name,
                description=variable.description,
                variants={},
                rollout=Rollout(variants={}),
                overrides=[],
                json_schema=json_schema,
                example=example,
            )
            variable_configs[variable.name] = config

        return VariablesConfig(variables=variable_configs)

    def merge(self, other: VariablesConfig) -> VariablesConfig:
        """Merge another VariablesConfig into this one.

        Variables in `other` will override variables with the same name in this config.

        Args:
            other: Another VariablesConfig to merge.

        Returns:
            A new VariablesConfig with variables from both configs.
        """
        merged_variables = dict(self.variables)
        merged_variables.update(other.variables)
        return VariablesConfig(variables=merged_variables)


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
