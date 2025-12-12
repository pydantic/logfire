from __future__ import annotations as _annotations

import random
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

from pydantic import Discriminator, TypeAdapter, ValidationError, field_validator, model_validator
from typing_extensions import TypeAliasType

from logfire.variables.variable import Variable


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
    """A specific variant of a managed variable with its serialized value."""

    key: VariantKey
    """Unique identifier for this variant."""
    serialized_value: str
    """The JSON-serialized value for this variant."""
    # format: Literal['json', 'yaml']  # TODO: Consider supporting yaml, and not just JSON; allows comments and better formatting
    description: str | None = None
    """Optional human-readable description of this variant."""
    version: str | None = None  # TODO: should this be required?
    """Optional version identifier for this variant."""


@dataclass(kw_only=True)
class RolloutOverride:
    """An override of the default rollout when specific conditions are met."""

    conditions: list[Condition]
    """List of conditions that must all match for this override to apply."""
    rollout: Rollout
    """The rollout configuration to use when all conditions match."""


@dataclass(kw_only=True)
class RolloutStage:
    """A single stage in a scheduled rollout sequence.

    Rollout schedules progress through stages sequentially, with each stage having its own
    duration, rollout configuration, and optional conditional overrides. This allows for
    gradual rollouts where traffic percentages can increase over time.

    Example: A three-stage rollout might have:
    - Stage 1: 5% of traffic for 1 hour (canary)
    - Stage 2: 25% of traffic for 4 hours (early adopters)
    - Stage 3: 100% of traffic (full rollout)
    """

    duration: timedelta
    """Duration to remain in this stage before progressing to the next.

    Once a stage's duration has elapsed, the schedule automatically advances to the
    next stage. If this is the final stage and its duration has elapsed, the schedule
    is considered complete.

    Note: Automated rollback based on error rates is only supported server-side and should
    be performed before the final stage completes. After completion, the variable config
    should be updated to make the final stage's rollout the new default.
    """

    rollout: Rollout
    """The rollout configuration used during this stage.

    Defines the probability weights for selecting each variant during this stage.
    For example, an early stage might have `{'new_variant': 0.05}` (5% rollout)
    while the final stage might have `{'new_variant': 1.0}` (100% rollout).
    """
    overrides: list[RolloutOverride]
    """Conditional overrides that take precedence over the stage's default rollout.

    Evaluated in order; the first matching override's rollout is used instead of
    this stage's default rollout. This allows for stage-specific targeting rules.
    """


@dataclass(kw_only=True)
class RolloutSchedule:
    """A time-based progression through multiple rollout stages.

    Rollout schedules enable gradual rollouts where the variant selection weights
    change over time. Starting from `start_at`, the schedule progresses through
    each stage sequentially, with each stage lasting for its specified duration.

    Use cases:
    - Canary deployments: Start with 1% traffic, increase to 10%, then 100%
    - Time-limited experiments: Run an A/B test for a specific duration
    - Phased feature launches: Gradually expose new features to more users

    The schedule is considered active when `start_at` is set and is in the past.
    Once all stages have completed (i.e., current time exceeds start_at plus the
    sum of all stage durations), the base rollout and overrides from the parent
    VariableConfig are used.
    """

    start_at: datetime | None
    """The datetime when this schedule becomes active.

    If None, the schedule is inactive and the base rollout is used.
    If set to a time in the future, the base rollout is used until that time.
    If set to a time in the past, the appropriate stage is determined based
    on elapsed time since start_at.

    Note: Datetimes should be timezone-aware for consistent behavior across
    different deployment environments.
    """
    stages: list[RolloutStage]
    """The sequence of rollout stages to progress through.

    Stages are processed in order. The active stage is determined by comparing
    the current time against start_at and the cumulative durations of previous stages.
    """
    # TODO: Need to add rollback condition support (possibly only in backend?)
    #   Note: we could add this client side using the logfire query client if the token has read capability.
    #   However, this should maybe be discouraged if it's viable to run health check queries server-side.
    #   We could expose a `health_check` field that contains one (or more?) SQL queries, which would either be
    #   evaluated client side or server side. However, I don't love the

    def get_active_stage(self, now: datetime | None = None) -> RolloutStage | None:
        """Determine the currently active stage based on the current time.

        Args:
            now: The current datetime. If None, uses datetime.now() with the same
                timezone as start_at (or naive if start_at is naive).

        Returns:
            The currently active RolloutStage, or None if:
            - The schedule is not active (start_at is None)
            - The schedule hasn't started yet (start_at is in the future)
            - The schedule has completed (all stage durations have elapsed)
        """
        if self.start_at is None:
            return None

        if now is None:
            # Use the same timezone as start_at for consistency
            if self.start_at.tzinfo is not None:
                now = datetime.now(self.start_at.tzinfo)
            else:
                # Treat naive datetimes as UTC
                now = datetime.now(tz=timezone.utc)

        if now < self.start_at:
            # Schedule hasn't started yet
            return None

        elapsed = now - self.start_at
        cumulative_duration = timedelta()

        for stage in self.stages:
            cumulative_duration += stage.duration
            if elapsed < cumulative_duration:
                return stage

        # All stages have completed
        return None


@dataclass(kw_only=True)
class VariableConfig:
    """Configuration for a single managed variable including variants and rollout rules."""

    name: VariableName
    """Unique name identifying this variable."""
    variants: dict[VariantKey, Variant]
    """Mapping of variant keys to their configurations."""
    rollout: Rollout
    """Default rollout configuration for variant selection."""
    overrides: list[RolloutOverride]
    """Conditional overrides evaluated in order; first match takes precedence."""
    json_schema: dict[str, Any] | None = None
    """JSON schema describing the expected type of this variable's values."""
    schedule: RolloutSchedule | None = None
    # TODO: Consider adding server-side management of targeting_key, rather than requiring it in the API call
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
        if self.schedule is not None:
            for stage_idx, stage in enumerate(self.schedule.stages):
                for k, v in stage.rollout.variants.items():
                    if k not in self.variants:
                        raise ValueError(
                            f'Variant {k!r} present in `schedule.stages[{stage_idx}].rollout` is not present in `variants`.'
                        )
                for override_idx, override in enumerate(stage.overrides):
                    for k, v in override.rollout.variants.items():
                        if k not in self.variants:
                            raise ValueError(
                                f'Variant {k!r} present in `schedule.stages[{stage_idx}].overrides[{override_idx}].rollout` '
                                f'is not present in `variants`.'
                            )

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

        if self.schedule is not None:
            active_stage = self.schedule.get_active_stage()
            if active_stage is not None:
                base_rollout = active_stage.rollout
                base_overrides = active_stage.overrides

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
                config = self.variables.get(variable.name)
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
