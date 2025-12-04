import re
from _typeshed import Incomplete
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from logfire.variables.variable import Variable as Variable
from typing import Any, Literal

@dataclass(kw_only=True)
class ValueEquals:
    """Condition that matches when an attribute equals a specific value."""
    attribute: str
    value: Any
    kind: Literal['value-equals'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute equals the expected value."""

@dataclass(kw_only=True)
class ValueDoesNotEqual:
    """Condition that matches when an attribute does not equal a specific value."""
    attribute: str
    value: Any
    kind: Literal['value-does-not-equal'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute does not equal the specified value."""

@dataclass(kw_only=True)
class ValueIsIn:
    """Condition that matches when an attribute value is in a set of values."""
    attribute: str
    values: Sequence[Any]
    kind: Literal['value-is-in'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value is in the allowed set."""

@dataclass(kw_only=True)
class ValueIsNotIn:
    """Condition that matches when an attribute value is not in a set of values."""
    attribute: str
    values: Sequence[Any]
    kind: Literal['value-is-not-in'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value is not in the excluded set."""

@dataclass(kw_only=True)
class ValueMatchesRegex:
    """Condition that matches when an attribute value matches a regex pattern."""
    attribute: str
    pattern: str | re.Pattern[str]
    kind: Literal['value-matches-regex'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value matches the regex pattern."""

@dataclass(kw_only=True)
class ValueDoesNotMatchRegex:
    """Condition that matches when an attribute value does not match a regex pattern."""
    attribute: str
    pattern: str | re.Pattern[str]
    kind: Literal['value-does-not-match-regex'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute value does not match the regex pattern."""

@dataclass(kw_only=True)
class KeyIsPresent:
    """Condition that matches when an attribute key is present."""
    attribute: str
    kind: Literal['key-is-present'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute key exists in the attributes."""

@dataclass(kw_only=True)
class KeyIsNotPresent:
    """Condition that matches when an attribute key is not present."""
    attribute: str
    kind: Literal['key-is-not-present'] = ...
    def matches(self, attributes: Mapping[str, Any]) -> bool:
        """Check if the attribute key does not exist in the attributes."""

Condition: Incomplete
VariantKey = str
VariableName = str

@dataclass(kw_only=True)
class Rollout:
    """Configuration for variant selection with weighted probabilities."""
    variants: dict[VariantKey, float]
    def select_variant(self, seed: str | None) -> VariantKey | None:
        """Select a variant based on configured weights using optional seeded randomness.

        Args:
            seed: Optional seed for deterministic variant selection. If provided, the same seed
                will always select the same variant.

        Returns:
            The key of the selected variant, or None if no variant is selected (when weights sum to less than 1.0).
        """

@dataclass(kw_only=True)
class Variant:
    """A specific variant of a managed variable with its serialized value."""
    key: VariantKey
    serialized_value: str
    description: str | None = ...
    version: str | None = ...

@dataclass(kw_only=True)
class RolloutOverride:
    """An override of the default rollout when specific conditions are met."""
    conditions: list[Condition]
    rollout: Rollout

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
    rollout: Rollout
    overrides: list[RolloutOverride]

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
    stages: list[RolloutStage]
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

@dataclass(kw_only=True)
class VariableConfig:
    """Configuration for a single managed variable including variants and rollout rules."""
    name: VariableName
    variants: dict[VariantKey, Variant]
    rollout: Rollout
    overrides: list[RolloutOverride]
    json_schema: dict[str, Any] | None = ...
    schedule: RolloutSchedule | None = ...
    def resolve_variant(self, targeting_key: str | None = None, attributes: Mapping[str, Any] | None = None) -> Variant | None:
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

@dataclass(kw_only=True)
class VariablesConfig:
    """Container for all managed variable configurations."""
    variables: dict[VariableName, VariableConfig]
    def get_validation_errors(self, variables: list[Variable[Any]]) -> dict[str, dict[str | None, Exception]]:
        """Validate that all variable variants can be deserialized to their expected types.

        Args:
            variables: List of Variable instances to validate against this configuration.

        Returns:
            A dict mapping variable names to dicts of variant keys (or None for general errors) to exceptions.
        """
    @staticmethod
    def validate_python(data: Any) -> VariablesConfig:
        """Parse and validate a VariablesConfig from a Python object.

        Args:
            data: A Python object (typically a dict) to validate as a VariablesConfig.

        Returns:
            A validated VariablesConfig instance.
        """
