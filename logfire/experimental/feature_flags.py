"""Experimental code-first feature flags backed by Logfire managed variables.

This API may change while its evaluation context and telemetry contracts are refined.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from logfire.variables import ensure_variables_dependencies

if TYPE_CHECKING:
    from logfire import Logfire

__all__ = 'FeatureFlag', 'FlagEvaluationDetails', 'FlagEvaluationReason', 'feature_context', 'feature_flag'


FlagEvaluationReason = Literal['default', 'static', 'split', 'targeting_match', 'error']
"""Why a feature-flag evaluation returned its value."""


@dataclass(frozen=True, slots=True)
class FlagEvaluationDetails:
    """The result of evaluating a feature flag."""

    flag_key: str
    value: bool
    variant: str | None = None
    reason: FlagEvaluationReason = 'default'
    error_code: str | None = None


class _FeatureFlagAdapter(Protocol):
    """Private compatibility boundary implemented by the current variables engine."""

    name: str
    description: str | None

    def evaluate_flag(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails: ...

    def override_for_testing(self, value: bool) -> AbstractContextManager[None]: ...


class FeatureFlag:
    """A boolean feature flag with a safe code default."""

    __slots__ = ('_adapter',)

    def __init__(
        self,
        name: str,
        *,
        default: bool,
        description: str | None = None,
        logfire_instance: Logfire | None = None,
    ):
        """Define a feature flag backed by the configured Logfire provider."""
        ensure_variables_dependencies()
        if logfire_instance is None:
            from logfire import DEFAULT_LOGFIRE_INSTANCE

            logfire_instance = DEFAULT_LOGFIRE_INSTANCE
        self._adapter: _FeatureFlagAdapter = logfire_instance._feature_flag(  # pyright: ignore[reportPrivateUsage]
            name, default=default, description=description
        )

    @property
    def name(self) -> str:
        """The stable key used to identify the flag."""
        return self._adapter.name

    @property
    def description(self) -> str | None:
        """The optional human-readable description supplied when defining the flag."""
        return self._adapter.description

    def is_enabled(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return whether the feature is enabled for the evaluation context."""
        return self.evaluate(targeting_key, attributes).value

    def evaluate(
        self,
        targeting_key: str | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> FlagEvaluationDetails:
        """Evaluate the flag and return feature-flag-specific resolution details."""
        return self._adapter.evaluate_flag(targeting_key, attributes)

    def override_for_testing(self, value: bool) -> AbstractContextManager[None]:
        """Temporarily replace the flag value in the current context."""
        return self._adapter.override_for_testing(value)


def feature_flag(
    name: str,
    *,
    default: bool,
    description: str | None = None,
    logfire_instance: Logfire | None = None,
) -> FeatureFlag:
    """Define a boolean feature flag with a safe code default.

    Args:
        name: Unique identifier for the flag. Must match the name configured in Logfire.
        default: Value used before the flag is configured or when configuration is unavailable.
        description: Optional human-readable description of what the flag controls.
        logfire_instance: Optional configured Logfire instance. The default global instance is used
            when this is omitted.
    """
    return FeatureFlag(name, default=default, description=description, logfire_instance=logfire_instance)


def feature_context(
    targeting_key: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> AbstractContextManager[None]:
    """Set request-local identity and attributes for managed-variable evaluations."""
    ensure_variables_dependencies()
    from logfire.variables.variable import feature_context as _feature_context

    return _feature_context(targeting_key, attributes=attributes)
